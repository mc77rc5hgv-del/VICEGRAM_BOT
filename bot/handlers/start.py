from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.config import MAX_FILE_SIZE_MB

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Я умею работать с PDF-файлами:\n"
        "🗜 сжимать без потери качества\n"
        "✂️ собирать новый файл только из нужных страниц\n\n"
        "Просто отправь мне PDF-документ (как файл, не как фото) — "
        "дальше предложу, что с ним сделать.\n\n"
        "Подробнее — команда /help."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📄 <b>Что я умею</b>\n"
        "Отправьте PDF-файл — я предложу два варианта:\n\n"
        "🗜 <b>Сжать без потери качества</b>\n"
        "Пересжимаю внутренние потоки данных PDF, убираю дубли и "
        "неиспользуемые объекты. Страницы не рендерятся заново и "
        "картинки не пережимаются — визуально файл остаётся точно таким "
        "же. Если PDF уже оптимизирован, заметно сжать его не получится.\n\n"
        "✂️ <b>Выбрать страницы</b>\n"
        "Пришлите номера страниц, которые нужно оставить, например "
        "<code>1-135</code> или <code>1,3,5-10</code> — верну новый файл "
        "только с ними.\n\n"
        "⚠️ <b>Особенности</b>\n"
        "• Файлы, защищённые паролем, обработать нельзя.\n"
        f"• Максимальный размер файла: {MAX_FILE_SIZE_MB} МБ "
        "(ограничение Telegram Bot API).\n"
        "• /cancel — отменить текущее действие.",
        parse_mode="HTML",
    )
