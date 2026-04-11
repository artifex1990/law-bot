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
from src.services.followup_service import FollowupService


async def run_messenger(messenger):
    """Запуск мессенджера с корректной остановкой."""
    try:
        await messenger.start()
    except Exception as e:
        mtype = messenger.messenger_type
        logger.error(f"Bot error ({mtype}): {e}")
        raise
    finally:
        await messenger.stop()


async def main():
    """Главная функция запуска."""
    setup_logging(settings.LOG_LEVEL)
    name = settings.PROJECT_NAME
    ver = settings.VERSION
    logger.info(f"Starting {name} v{ver}")

    try:
        await init_db()
        logger.info("Database initialized")
    except (SQLAlchemyError, OSError) as e:
        logger.error(f"Database init failed: {e}")
        sys.exit(1)

    backup = BackupService()
    await backup.start()

    messengers = []
    followup_services: list[FollowupService] = []

    if settings.TELEGRAM_BOT_TOKEN:
        from src.messengers.telegram import (
            TelegramMessenger,
        )

        tg = TelegramMessenger()
        messengers.append(tg)
        followup_services.append(FollowupService(tg))
        mode = "webhook" if settings.TELEGRAM_USE_WEBHOOK else "long polling"
        logger.info(f"Telegram bot enabled ({mode})")

    if settings.MAX_BOT_TOKEN:
        from src.messengers.max import MaxMessenger

        mx = MaxMessenger()
        messengers.append(mx)
        followup_services.append(FollowupService(mx))
        mx_mode = "webhook" if settings.MAX_USE_WEBHOOK else "long polling"
        logger.info(f"MAX bot enabled ({mx_mode})")

    if not messengers and not settings.API_ENABLED:
        logger.error(
            "No bot tokens configured. Set TELEGRAM_BOT_TOKEN in .env "
            "or enable API_ENABLED=true for HTTP-only mode.",
        )
        sys.exit(1)

    for fs in followup_services:
        await fs.start()

    async def run_api_server():
        import uvicorn

        from src.api.app import app

        config = uvicorn.Config(
            app,
            host=settings.API_HOST,
            port=settings.API_PORT,
            log_level=settings.LOG_LEVEL.lower(),
        )
        server = uvicorn.Server(config)
        await server.serve()

    tasks: list[asyncio.Task] = []
    if settings.API_ENABLED:
        if not settings.INTEGRATION_API_TOKEN.strip():
            logger.warning(
                "INTEGRATION_API_TOKEN is empty: integration API accepts "
                "requests without auth. Set a strong token before exposing "
                "the API beyond localhost.",
            )
        docs = (
            "/docs"
            if settings.API_DOCS_ENABLED
            else "(disabled; set API_DOCS_ENABLED=True)"
        )
        logger.info(
            f"Integration API http://{settings.API_HOST}:{settings.API_PORT} "
            f"OpenAPI {docs}",
        )
        tasks.append(asyncio.create_task(run_api_server()))

    if messengers:
        if len(messengers) == 1:
            tasks.append(asyncio.create_task(run_messenger(messengers[0])))
        else:
            for m in messengers:
                tasks.append(asyncio.create_task(run_messenger(m)))

    try:
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc:
                logger.error(f"Background task crashed: {exc}")
    finally:
        for fs in followup_services:
            await fs.stop()
        await backup.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
