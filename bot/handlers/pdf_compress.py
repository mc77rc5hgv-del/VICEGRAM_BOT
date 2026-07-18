import logging
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, Message

from bot.config import MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB
from bot.services.pdf_compressor import (
    PdfCompressionError,
    PdfEncryptedError,
    compress_pdf_lossless,
)

logger = logging.getLogger(__name__)

router = Router(name="pdf_compress")


def _is_pdf(file_name: str | None, mime_type: str | None) -> bool:
    if mime_type == "application/pdf":
        return True
    return bool(file_name) and file_name.lower().endswith(".pdf")


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f} МБ"
    return f"{num_bytes / 1024:.1f} КБ"


@router.message(F.document)
async def handle_document(message: Message, bot: Bot) -> None:
    document = message.document
    assert document is not None

    if not _is_pdf(document.file_name, document.mime_type):
        await message.reply(
            "Я умею сжимать только PDF-файлы. Отправьте документ с "
            "расширением .pdf."
        )
        return

    if document.file_size and document.file_size > MAX_FILE_SIZE_BYTES:
        await message.reply(
            f"Файл слишком большой ({_format_size(document.file_size)}). "
            f"Максимум — {MAX_FILE_SIZE_MB} МБ."
        )
        return

    status_message = await message.reply("⏳ Сжимаю PDF без потери качества…")

    with tempfile.TemporaryDirectory(prefix="pdfcompress_") as tmp_dir:
        input_path = Path(tmp_dir) / "input.pdf"
        output_path = Path(tmp_dir) / "output.pdf"

        try:
            file = await bot.get_file(document.file_id)
            await bot.download_file(file.file_path, destination=input_path)
        except Exception:
            logger.exception("Failed to download PDF from Telegram")
            await status_message.edit_text(
                "Не удалось скачать файл. Попробуйте отправить его ещё раз."
            )
            return

        try:
            result = compress_pdf_lossless(input_path, output_path)
        except PdfEncryptedError:
            await status_message.edit_text(
                "🔒 Файл защищён паролем — сжать его не получится."
            )
            return
        except PdfCompressionError:
            logger.exception("Failed to compress PDF")
            await status_message.edit_text(
                "Не удалось обработать файл. Возможно, он повреждён или "
                "имеет нестандартный формат."
            )
            return
        except Exception:
            logger.exception("Unexpected error while compressing PDF")
            await status_message.edit_text(
                "Произошла непредвиденная ошибка при обработке файла."
            )
            return

        if not result.improved:
            await status_message.edit_text(
                "✅ Файл уже оптимален — сжать без потери качества больше "
                f"некуда ({_format_size(result.original_size)})."
            )
            return

        source_name = document.file_name or "document.pdf"
        stem = Path(source_name).stem
        output_name = f"{stem}_compressed.pdf"

        caption = (
            "✅ Готово!\n"
            f"Было: {_format_size(result.original_size)}\n"
            f"Стало: {_format_size(result.compressed_size)}\n"
            f"Экономия: {result.saved_percent:.1f}%"
        )

        await message.reply_document(
            BufferedInputFile(output_path.read_bytes(), filename=output_name),
            caption=caption,
        )
        await status_message.delete()
