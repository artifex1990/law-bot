"""Точка входа приложения"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from src.config.settings import settings
from src.config.logging_config import setup_logging
from src.database.base import init_db


async def run_messenger(messenger):
    """Запуск одного мессенджера"""
    try:
        await messenger.start()
    except Exception as e:
        logger.error(f"Bot error ({messenger.messenger_type}): {e}")
        raise
    finally:
        await messenger.stop()


async def main():
    """Главная функция запуска"""
    setup_logging(settings.LOG_LEVEL)
    logger.info(
        f"Starting {settings.PROJECT_NAME} v{settings.VERSION}"
    )

    # Инициализация БД
    try:
        await init_db()
        logger.info("Database initialized")
    except (SQLAlchemyError, OSError) as e:
        logger.error(f"Database init failed: {e}")
        sys.exit(1)

    # Собираем мессенджеры по наличию токенов
    messengers = []

    if settings.TELEGRAM_BOT_TOKEN:
        from src.messengers.telegram import TelegramMessenger
        messengers.append(TelegramMessenger())
        logger.info("Telegram bot enabled")

    if settings.MAX_BOT_TOKEN:
        from src.messengers.max import MaxMessenger
        messengers.append(MaxMessenger())
        logger.info("MAX bot enabled")

    if not messengers:
        logger.error(
            "No bot tokens set! "
            "Add TELEGRAM_BOT_TOKEN or MAX_BOT_TOKEN to .env"
        )
        sys.exit(1)

    # Запуск всех мессенджеров параллельно
    if len(messengers) == 1:
        await run_messenger(messengers[0])
    else:
        tasks = [
            asyncio.create_task(run_messenger(m))
            for m in messengers
        ]
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
