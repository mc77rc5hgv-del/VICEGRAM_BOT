from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import MAX_FILE_SIZE_MB

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я сжимаю PDF-файлы без потери качества.\n\n"
        "Просто отправь мне PDF-документ (как файл, не как фото), "
        "и я верну сжатую версию.\n\n"
        "Подробнее — команда /help."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📄 <b>Как это работает</b>\n"
        "Я использую lossless-сжатие: пересжимаю внутренние потоки данных "
        "PDF, убираю дубли и неиспользуемые объекты. Страницы не "
        "рендерятся заново и картинки не пережимаются — визуально файл "
        "остаётся точно таким же.\n\n"
        "⚠️ <b>Особенности</b>\n"
        "• Если PDF уже оптимизирован (например, экспортирован из "
        "современного редактора), заметно сжать его не получится.\n"
        "• Файлы, защищённые паролем, сжать нельзя.\n"
        f"• Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ "
        "(ограничение Telegram Bot API).\n\n"
        "Чтобы сжать посильнее (с потерей качества картинок), "
        "напишите — можно добавить отдельный режим.",
        parse_mode="HTML",
    )
