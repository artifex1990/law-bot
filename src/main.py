"""Точка входа приложения"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from src.config.logging_config import setup_logging
from src.config.settings import settings
from src.database.base import init_db
from src.services.backup_service import BackupService


async def run_messenger(messenger):
    """Запуск одного мессенджера с корректной остановкой"""
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
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")

    try:
        await init_db()
        logger.info("Database initialized")
    except (SQLAlchemyError, OSError) as e:
        logger.error(f"Database init failed: {e}")
        sys.exit(1)

    # Бэкапы
    backup = BackupService()
    await backup.start()

    # Мессенджеры
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
            "No bot tokens configured. Set TELEGRAM_BOT_TOKEN in .env or .env.local"
        )
        sys.exit(1)

    try:
        if len(messengers) == 1:
            await run_messenger(messengers[0])
        else:
            tasks = [asyncio.create_task(run_messenger(m)) for m in messengers]
            done, pending = await asyncio.wait(
                tasks,
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
            for task in done:
                if task.exception():
                    logger.error(f"Messenger crashed: {task.exception()}")
    finally:
        await backup.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
