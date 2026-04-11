"""Запуск только HTTP API (без Telegram/MAX)."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError

from src.api.app import app
from src.config.logging_config import setup_logging
from src.config.settings import settings
from src.database.base import init_db


async def main() -> None:
    setup_logging(settings.LOG_LEVEL)
    if not settings.INTEGRATION_API_TOKEN.strip():
        logger.warning(
            "INTEGRATION_API_TOKEN is empty: API accepts requests without auth. "
            "Set a strong token before exposing the service.",
        )
    logger.info(
        f"Starting Integration API on "
        f"http://{settings.API_HOST}:{settings.API_PORT}",
    )
    try:
        await init_db()
        logger.info("Database initialized")
    except (SQLAlchemyError, OSError) as e:
        logger.error(f"Database init failed: {e}")
        sys.exit(1)

    config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down API...")
