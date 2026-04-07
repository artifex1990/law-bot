"""Настройка логирования"""

import sys
from pathlib import Path

from loguru import logger

from src.config.settings import settings

CONSOLE_FMT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
    "<level>{message}</level>"
)

FILE_FMT = (
    "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function} - {message}"
)


def setup_logging(level: str = "INFO") -> None:
    """Настройка логирования с loguru"""
    logger.remove()

    logger.add(
        sys.stderr,
        format=CONSOLE_FMT,
        level=level,
        colorize=True,
    )

    log_dir = Path(settings.LOG_FILE).parent
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        settings.LOG_FILE,
        format=FILE_FMT,
        level=level,
        rotation="10 MB",
        retention="7 days",
    )
