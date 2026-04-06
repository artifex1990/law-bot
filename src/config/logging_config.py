"""Настройка логирования"""

import sys
from pathlib import Path

from loguru import logger

from src.config.settings import settings


def setup_logging(level: str = "INFO") -> None:
    """Настройка логирования с loguru"""
    logger.remove()

    # Консольный вывод
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
    )

    # Файловый вывод
    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        settings.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}",
        level=level,
        rotation="10 MB",
        retention="7 days",
    )
