"""Конфигурация приложения"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)


class Settings:
    """Конфигурация приложения"""

    BASE_DIR = BASE_DIR
    PROJECT_NAME = "Legal Consultation Bot"
    VERSION = "1.0.0"
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_USE_WEBHOOK = os.getenv("TELEGRAM_USE_WEBHOOK", "False").lower() in (
        "true",
        "1",
        "yes",
    )
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))

    # MAX Messenger (опционально)
    MAX_BOT_TOKEN: str = os.getenv("MAX_BOT_TOKEN", "")

    # БД: SQLite по умолчанию для локальной разработки
    _default_db = (BASE_DIR / "legal_bot.db").as_posix()
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{_default_db}",
    )

    # AI
    AI_DEFAULT_MODEL: str = os.getenv("AI_DEFAULT_MODEL", "mock")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    YANDEX_GPT_API_KEY: str = os.getenv("YANDEX_GPT_API_KEY", "")

    # Логирование
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: Path = BASE_DIR / "logs" / "bot.log"

    # Уведомления
    NOTIFY_ADMIN_ON_CONSULTATION = os.getenv(
        "NOTIFY_ADMIN_ON_CONSULTATION", "False"
    ).lower() in ("true", "1", "yes")
    ADMIN_CHAT_ID: str = os.getenv("ADMIN_CHAT_ID", "")

    # Таймауты
    MESSAGE_TIMEOUT: int = int(os.getenv("MESSAGE_TIMEOUT", "30"))
    CONVERSATION_TIMEOUT: int = int(os.getenv("CONVERSATION_TIMEOUT", "3600"))

    # ---- Бэкапы ----
    BACKUP_ENABLED = os.getenv("BACKUP_ENABLED", "False").lower() in (
        "true",
        "1",
        "yes",
    )
    # local | ftp | s3
    BACKUP_STORAGE_TYPE: str = os.getenv(
        "BACKUP_STORAGE_TYPE",
        "local",
    )
    BACKUP_INTERVAL_HOURS: int = int(
        os.getenv("BACKUP_INTERVAL_HOURS", "1"),
    )
    BACKUP_RETENTION_DAYS: int = int(
        os.getenv("BACKUP_RETENTION_DAYS", "30"),
    )

    # Local storage
    BACKUP_LOCAL_PATH: str = os.getenv(
        "BACKUP_LOCAL_PATH",
        str(BASE_DIR / "backups"),
    )

    # FTP / FTPS
    BACKUP_FTP_HOST: str = os.getenv("BACKUP_FTP_HOST", "")
    BACKUP_FTP_PORT: int = int(os.getenv("BACKUP_FTP_PORT", "21"))
    BACKUP_FTP_USER: str = os.getenv("BACKUP_FTP_USER", "")
    BACKUP_FTP_PASSWORD: str = os.getenv("BACKUP_FTP_PASSWORD", "")
    BACKUP_FTP_PATH: str = os.getenv("BACKUP_FTP_PATH", "/backups")
    BACKUP_FTP_TLS = os.getenv("BACKUP_FTP_TLS", "False").lower() in (
        "true",
        "1",
        "yes",
    )

    # S3-совместимое облако (AWS, MinIO, Yandex OS)
    BACKUP_S3_ENDPOINT: str = os.getenv("BACKUP_S3_ENDPOINT", "")
    BACKUP_S3_BUCKET: str = os.getenv("BACKUP_S3_BUCKET", "")
    BACKUP_S3_ACCESS_KEY: str = os.getenv(
        "BACKUP_S3_ACCESS_KEY",
        "",
    )
    BACKUP_S3_SECRET_KEY: str = os.getenv(
        "BACKUP_S3_SECRET_KEY",
        "",
    )
    BACKUP_S3_REGION: str = os.getenv("BACKUP_S3_REGION", "")
    BACKUP_S3_PREFIX: str = os.getenv("BACKUP_S3_PREFIX", "backups")


settings = Settings()
