import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

from bot.config import BOT_TOKEN
from bot.handlers import pdf_compress, start


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not BOT_TOKEN:
        logging.getLogger(__name__).error(
            "BOT_TOKEN не задан. Создайте .env на основе .env.example "
            "и укажите токен, полученный у @BotFather."
        )
        sys.exit(1)

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(pdf_compress.router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
