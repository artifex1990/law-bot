"""Конфигурация приложения"""

import json
import os
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

_TRUTHY = ("true", "1", "yes")


def _flag(key: str, default: str = "False") -> bool:
    return os.getenv(key, default).lower() in _TRUTHY


def _flag_optional(key: str, default: bool) -> bool:
    """Если переменная не задана — ``default``; иначе как булев флаг."""
    raw = os.getenv(key, "").strip()
    if raw == "":
        return default
    return raw.lower() in _TRUTHY


class Settings:
    """Конфигурация приложения"""

    BASE_DIR = BASE_DIR
    PROJECT_NAME = "Legal Consultation Bot"
    VERSION = "2.1.0"
    DEBUG = _flag("DEBUG")
    # OpenAPI/Swagger: по умолчанию как DEBUG; в проде без явного True — доки скрыты
    API_DOCS_ENABLED = _flag_optional("API_DOCS_ENABLED", DEBUG)

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_USE_WEBHOOK = _flag("TELEGRAM_USE_WEBHOOK")
    # Публичный HTTPS URL для Telegram setWebhook (см. build_telegram_webhook_url)
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    # Локальная привязка HTTP-сервера под updates (443, 80, 88, 8443 - см. Telegram)
    WEBHOOK_PORT: int = int(os.getenv("WEBHOOK_PORT", "8443"))
    WEBHOOK_LISTEN_HOST: str = os.getenv("WEBHOOK_LISTEN_HOST", "0.0.0.0")
    # Путь на вашем сервере (дописывается к WEBHOOK_URL, если в URL нет пути)
    TELEGRAM_WEBHOOK_PATH: str = os.getenv("TELEGRAM_WEBHOOK_PATH", "/webhook")
    # Секрет X-Telegram-Bot-Api-Secret-Token (только A–Z a–z 0–9 _-)
    TELEGRAM_WEBHOOK_SECRET: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    TELEGRAM_WEBHOOK_DROP_PENDING = _flag("TELEGRAM_WEBHOOK_DROP_PENDING")

    # MAX Messenger (опционально)
    MAX_BOT_TOKEN: str = os.getenv("MAX_BOT_TOKEN", "")
    MAX_USE_WEBHOOK = _flag("MAX_USE_WEBHOOK")
    # Публичный HTTPS URL для subscribe_webhook (если без пути — добавится MAX_WEBHOOK_PATH)
    MAX_WEBHOOK_URL: str = os.getenv("MAX_WEBHOOK_URL", "")
    MAX_WEBHOOK_PATH: str = os.getenv("MAX_WEBHOOK_PATH", "/max/webhook")
    # Секрет в заголовке X-Max-Bot-Api-Secret (должен совпадать с subscribe_webhook)
    MAX_WEBHOOK_SECRET: str = os.getenv("MAX_WEBHOOK_SECRET", "")
    # Локальный HTTP-сервер webhook (по умолчанию 8444, чтобы не конфликтовать с Telegram на 8443)
    MAX_WEBHOOK_PORT: int = int(os.getenv("MAX_WEBHOOK_PORT", "8444"))
    MAX_WEBHOOK_LISTEN_HOST: str = os.getenv(
        "MAX_WEBHOOK_LISTEN_HOST",
        os.getenv("WEBHOOK_LISTEN_HOST", "0.0.0.0"),
    )

    # БД
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
    NOTIFY_ADMIN_ON_CONSULTATION = _flag("NOTIFY_ADMIN_ON_CONSULTATION")
    ADMIN_CHAT_ID: str = os.getenv("ADMIN_CHAT_ID", "")
    _admin_raw = os.getenv(
        "ADMIN_IDS",
        os.getenv("ADMIN_CHAT_ID", ""),
    )
    ADMIN_IDS: ClassVar[set[str]] = {
        s.strip() for s in _admin_raw.split(",") if s.strip()
    }
    # Админы в MAX (user_id из MAX; через запятую). Отдельно от Telegram ADMIN_IDS
    _max_admin_raw = os.getenv("MAX_ADMIN_IDS", "")
    MAX_ADMIN_IDS: ClassVar[set[str]] = {
        s.strip() for s in _max_admin_raw.split(",") if s.strip()
    }

    # Таймауты
    MESSAGE_TIMEOUT: int = int(os.getenv("MESSAGE_TIMEOUT", "30"))
    CONVERSATION_TIMEOUT: int = int(os.getenv("CONVERSATION_TIMEOUT", "3600"))

    # ---- Догоняющие напоминания (followup) ----
    FOLLOWUP_ENABLED = _flag("FOLLOWUP_ENABLED")
    FOLLOWUP_CHECK_INTERVAL_MIN: int = int(
        os.getenv("FOLLOWUP_CHECK_INTERVAL_MIN", "10"),
    )
    _default_intervals = "[1, 12, 24, 72]"
    FOLLOWUP_INTERVALS_HOURS: list[int] = json.loads(
        os.getenv(
            "FOLLOWUP_INTERVALS_HOURS",
            _default_intervals,
        )
    )
    _default_messages = json.dumps(
        [
            (
                "Здравствуйте! Вы начали консультацию, "
                "но не завершили. Мы готовы помочь - "
                "продолжим?\n\n"
                "Нажмите /start чтобы продолжить."
            ),
            (
                "Напоминаем: ваша заявка ещё не "
                "завершена. Наши юристы ждут вас! "
                "Напишите /start чтобы продолжить."
            ),
            (
                "Мы заметили, что вы давно не "
                "возвращались. Если у вас остались "
                "вопросы - мы на связи. /start"
            ),
            (
                "Последнее напоминание: если вам всё "
                "ещё нужна помощь юриста, напишите "
                "/start. Будем рады помочь!"
            ),
        ],
        ensure_ascii=False,
    )
    FOLLOWUP_MESSAGES: list[str] = json.loads(
        os.getenv("FOLLOWUP_MESSAGES", _default_messages)
    )

    # ---- Бэкапы ----
    BACKUP_ENABLED = _flag("BACKUP_ENABLED")
    BACKUP_STORAGE_TYPE: str = os.getenv("BACKUP_STORAGE_TYPE", "local")
    BACKUP_INTERVAL_HOURS: int = int(
        os.getenv("BACKUP_INTERVAL_HOURS", "1"),
    )
    BACKUP_RETENTION_DAYS: int = int(
        os.getenv("BACKUP_RETENTION_DAYS", "30"),
    )
    BACKUP_LOCAL_PATH: str = os.getenv(
        "BACKUP_LOCAL_PATH",
        str(BASE_DIR / "backups"),
    )
    BACKUP_FTP_HOST: str = os.getenv("BACKUP_FTP_HOST", "")
    BACKUP_FTP_PORT: int = int(os.getenv("BACKUP_FTP_PORT", "21"))
    BACKUP_FTP_USER: str = os.getenv("BACKUP_FTP_USER", "")
    BACKUP_FTP_PASSWORD: str = os.getenv("BACKUP_FTP_PASSWORD", "")
    BACKUP_FTP_PATH: str = os.getenv("BACKUP_FTP_PATH", "/backups")
    BACKUP_FTP_TLS = _flag("BACKUP_FTP_TLS")
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

    # ---- HTTP API для внешних сервисов ----
    API_ENABLED = _flag("API_ENABLED")
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8080"))
    # Пусто = без авторизации на входящих запросах (только для изолированной сети)
    INTEGRATION_API_TOKEN: str = os.getenv("INTEGRATION_API_TOKEN", "")

    # Исходящий webhook: POST на URL при новой заявке (токен опционален)
    OUTBOUND_WEBHOOK_URL: str = os.getenv("OUTBOUND_WEBHOOK_URL", "")
    OUTBOUND_WEBHOOK_TOKEN: str = os.getenv("OUTBOUND_WEBHOOK_TOKEN", "")
    # True — не фильтровать localhost/частные IP (только доверенная сеть)
    OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS = _flag(
        "OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS",
    )

    def build_telegram_webhook_url(self) -> str:
        """Полный URL для Bot.set_webhook.

        Если WEBHOOK_URL уже содержит путь (не только ``/``), используется как есть.
        Иначе к origin добавляется TELEGRAM_WEBHOOK_PATH.
        """
        raw = self.WEBHOOK_URL.strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        path = (parsed.path or "").strip()
        if path and path != "/":
            return raw.rstrip("/")
        wh_path = self.TELEGRAM_WEBHOOK_PATH.strip()
        if not wh_path.startswith("/"):
            wh_path = "/" + wh_path
        origin = raw.rstrip("/")
        return origin + wh_path

    def build_max_webhook_url(self) -> str:
        """Полный публичный URL для Bot.subscribe_webhook (MAX).

        Если MAX_WEBHOOK_URL уже содержит путь (не только ``/``), используется как есть.
        Иначе к origin добавляется MAX_WEBHOOK_PATH.
        """
        raw = self.MAX_WEBHOOK_URL.strip()
        if not raw:
            return ""
        parsed = urlparse(raw)
        path = (parsed.path or "").strip()
        if path and path != "/":
            return raw.rstrip("/")
        wh_path = self.MAX_WEBHOOK_PATH.strip()
        if not wh_path.startswith("/"):
            wh_path = "/" + wh_path
        origin = raw.rstrip("/")
        return origin + wh_path


settings = Settings()
