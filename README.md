# VICEGRAM Bot — сжатие PDF без потери качества

Telegram-бот на [aiogram](https://docs.aiogram.dev/), который принимает PDF-файл
и возвращает его сжатую копию.

## Как это работает

Сжатие **lossless**: используется [pikepdf](https://pikepdf.readthedocs.io/)
(обёртка над `qpdf`), которая:

- пересжимает внутренние потоки данных PDF (deflate/zlib с максимальным уровнем);
- убирает неиспользуемые и дублирующиеся объекты;
- упаковывает объекты в object streams.

Страницы при этом не рендерятся заново, изображения не пережимаются —
итоговый файл выглядит идентично исходному. Реальная экономия зависит от
того, насколько PDF уже оптимизирован: свежесгенерированные из
LaTeX/Word/Google Docs файлы иногда почти не сжимаются, а старые/несжатые
файлы могут уменьшиться на 20–40%.

Если после сжатия размер не уменьшился, бот сообщает об этом и не
присылает файл повторно.

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Впишите в `.env` токен бота, полученный у [@BotFather](https://t.me/BotFather):

```
BOT_TOKEN=123456:ABC-DEF...
MAX_FILE_SIZE_MB=20
```

## Запуск

```bash
python -m bot.main
```

## Ограничения

- Максимальный размер файла по умолчанию — 20 МБ (лимит стандартного
  Telegram Bot API на скачивание файлов ботом). Чтобы работать с большими
  файлами, нужен собственный [Local Bot API Server](https://github.com/tdlib/telegram-bot-api).
- PDF, защищённые паролем, бот сжимать не умеет.

## Структура проекта

```
bot/
  main.py                 — точка входа, запуск polling
  config.py                — чтение переменных окружения
  handlers/
    start.py               — /start, /help
    pdf_compress.py        — приём PDF и ответ сжатым файлом
  services/
    pdf_compressor.py      — логика lossless-сжатия (pikepdf)
requirements.txt
.env.example
```
