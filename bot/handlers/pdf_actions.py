import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.config import MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB
from bot.services.pdf_compressor import compress_pdf_lossless
from bot.services.pdf_errors import PdfCompressionError, PdfEncryptedError
from bot.services.pdf_splitter import (
    PageRangeError,
    extract_pages,
    format_pages_label,
    get_page_count,
    parse_page_spec,
)

logger = logging.getLogger(__name__)

router = Router(name="pdf_actions")


class PdfStates(StatesGroup):
    waiting_for_pages = State()


def _is_pdf(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type == "application/pdf":
        return True
    return bool(file_name) and file_name.lower().endswith(".pdf")


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} МБ"
    return f"{num_bytes / 1024:.1f} КБ"


def _cleanup(data: dict[str, Any]) -> None:
    temp_dir = data.get("temp_dir")
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    _cleanup(data)
    await state.clear()
    await message.reply("Отменено.")


@router.message(F.document)
async def handle_document(message: Message, bot: Bot, state: FSMContext) -> None:
    document = message.document
    assert document is not None

    _cleanup(await state.get_data())
    await state.clear()

    if not _is_pdf(document.file_name, document.mime_type):
        await message.reply(
            "Я умею работать только с PDF-файлами. Отправьте документ с "
            "расширением .pdf."
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await message.reply(
            f"Файл слишком большой ({_format_size(document.file_size)}). "
            f"Максимум — {MAX_FILE_SIZE_MB} МБ."
        )
        return

    status_message = await message.reply("⏳ Загружаю файл…")

    temp_dir = Path(tempfile.mkdtemp(prefix="pdfbot_"))
    input_path = temp_dir / "input.pdf"

    try:
        file = await bot.get_file(document.file_id)
        await bot.download_file(file.file_path, destination=input_path)
    except Exception:
        logger.exception("Failed to download PDF from Telegram")
        shutil.rmtree(temp_dir, ignore_errors=True)
        await status_message.edit_text(
            "Не удалось скачать файл. Попробуйте отправить его ещё раз."
        )
        return

    try:
        total_pages = get_page_count(input_path)
    except PdfEncryptedError:
        shutil.rmtree(temp_dir, ignore_errors=True)
        await status_message.edit_text(
            "🔒 Файл защищён паролем — обработать его не получится."
        )
        return
    except PdfCompressionError:
        logger.exception("Failed to read PDF")
        shutil.rmtree(temp_dir, ignore_errors=True)
        await status_message.edit_text(
            "Не удалось прочитать файл. Возможно, он повреждён."
        )
        return

    await state.update_data(
        temp_dir=str(temp_dir),
        input_path=str(input_path),
        file_name=document.file_name or "document.pdf",
        total_pages=total_pages,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗜 Сжать без потери качества",
                    callback_data="pdf_action:compress",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✂️ Выбрать страницы", callback_data="pdf_action:split"
                )
            ],
        ]
    )
    file_label = document.file_name or "document.pdf"
    await status_message.edit_text(
        f"Файл получен: {file_label} ({total_pages} стр.).\nЧто сделать?",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "pdf_action:compress")
async def handle_compress_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    input_path = data.get("input_path")
    if not input_path or not Path(input_path).exists():
        await callback.answer("Сессия истекла, отправьте файл заново.", show_alert=True)
        return

    await callback.answer()
    message = callback.message
    await message.edit_text("⏳ Сжимаю PDF без потери качества…")

    temp_dir = Path(data["temp_dir"])
    output_path = temp_dir / "compressed.pdf"

    try:
        result = compress_pdf_lossless(Path(input_path), output_path)
    except PdfCompressionError:
        logger.exception("Failed to compress PDF")
        await message.edit_text("Не удалось обработать файл.")
        _cleanup(data)
        await state.clear()
        return

    if not result.improved:
        await message.edit_text(
            "✅ Файл уже оптимален — сжать без потери качества больше "
            f"некуда ({_format_size(result.original_size)})."
        )
    else:
        source_name = data.get("file_name", "document.pdf")
        stem = Path(source_name).stem
        output_name = f"{stem}_compressed.pdf"
        caption = (
            "✅ Готово!\n"
            f"Было: {_format_size(result.original_size)}\n"
            f"Стало: {_format_size(result.compressed_size)}\n"
            f"Экономия: {result.saved_percent:.1f}%"
        )
        await message.answer_document(
            BufferedInputFile(output_path.read_bytes(), filename=output_name),
            caption=caption,
        )
        await message.delete()

    _cleanup(data)
    await state.clear()


@router.callback_query(F.data == "pdf_action:split")
async def handle_split_choice(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    input_path = data.get("input_path")
    if not input_path or not Path(input_path).exists():
        await callback.answer("Сессия истекла, отправьте файл заново.", show_alert=True)
        return

    await callback.answer()
    total_pages = data.get("total_pages")
    await callback.message.edit_text(
        f"В файле {total_pages} стр.\n\n"
        "Напишите, какие страницы оставить в новом файле. Например:\n"
        "• <code>1-135</code>\n"
        "• <code>1,3,5-10</code>\n\n"
        "Для отмены — /cancel",
        parse_mode="HTML",
    )
    await state.set_state(PdfStates.waiting_for_pages)


@router.message(PdfStates.waiting_for_pages, F.text)
async def handle_page_spec(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    input_path = data.get("input_path")
    if not input_path or not Path(input_path).exists():
        await message.reply("Сессия истекла, отправьте файл заново.")
        await state.clear()
        return

    total_pages = data["total_pages"]
    try:
        page_numbers = parse_page_spec(message.text, total_pages)
    except PageRangeError as exc:
        await message.reply(f"{exc}\nПопробуйте ещё раз, например: 1-135. Для отмены — /cancel")
        return

    status_message = await message.reply("⏳ Собираю файл с выбранными страницами…")

    temp_dir = Path(data["temp_dir"])
    output_path = temp_dir / "split.pdf"

    try:
        extract_pages(Path(input_path), output_path, page_numbers)
    except PdfCompressionError:
        logger.exception("Failed to extract pages")
        await status_message.edit_text("Не удалось собрать файл с указанными страницами.")
        _cleanup(data)
        await state.clear()
        return

    source_name = data.get("file_name", "document.pdf")
    stem = Path(source_name).stem
    pages_label = format_pages_label(page_numbers)
    output_name = f"{stem}_p{pages_label}.pdf"

    await message.reply_document(
        BufferedInputFile(output_path.read_bytes(), filename=output_name),
        caption=(
            f"✅ Готово! Страницы: {pages_label} "
            f"({len(page_numbers)} из {total_pages})."
        ),
    )
    await status_message.delete()

    _cleanup(data)
    await state.clear()
