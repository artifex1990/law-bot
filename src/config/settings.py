"""Конфигурация приложения"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings:
    """Конфигурация приложения"""
    
    # Проект
    BASE_DIR = BASE_DIR
    PROJECT_NAME = "Legal Consultation Bot"
    VERSION = "1.0.0"
    DEBUG = os.getenv("DEBUG", "False") == "True"
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_USE_WEBHOOK = os.getenv("TELEGRAM_USE_WEBHOOK", "False") == "True"
    WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://example.com")
    WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))

    # MAX Messenger
    MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN", "")
    
    # База данных (SQLite по умолчанию для удобства разработки)
    _default_db = (BASE_DIR / "legal_bot.db").as_posix()
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite+aiosqlite:///{_default_db}"
    )
    
    # AI
    AI_DEFAULT_MODEL = os.getenv("AI_DEFAULT_MODEL", "mock")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY", "")
    
    # Логирование
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = BASE_DIR / "logs" / "bot.log"
    
    # Уведомления
    NOTIFY_ADMIN_ON_CONSULTATION = os.getenv("NOTIFY_ADMIN_ON_CONSULTATION", "False") == "True"
    ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
    
    # Таймауты
    MESSAGE_TIMEOUT = int(os.getenv("MESSAGE_TIMEOUT", "30"))
    CONVERSATION_TIMEOUT = int(os.getenv("CONVERSATION_TIMEOUT", "3600"))


settings = Settings()
