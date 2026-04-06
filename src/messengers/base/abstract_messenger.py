"""Абстрактный класс мессенджера"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class IncomingMessage:
    """Входящее сообщение от пользователя"""

    user_id: str
    chat_id: str
    content: str
    message_type: str
    message_id: str
    created_at: datetime
    extra_data: dict[str, Any] | None = None


@dataclass
class OutgoingMessage:
    """Исходящее сообщение бота"""

    chat_id: str
    content: str
    buttons: list[dict[str, str]] | None = None
    reply_markup: Any | None = None
    parse_mode: str | None = "HTML"


class AbstractMessenger(ABC):
    """Абстрактный класс для всех мессенджеров"""

    messenger_type: str = ""

    @abstractmethod
    async def start(self):
        """Запуск мессенджера"""

    @abstractmethod
    async def stop(self):
        """Остановка мессенджера"""

    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> bool:
        """Отправка сообщения"""

    @abstractmethod
    async def send_typing(self, chat_id: str):
        """Индикатор печати"""

    @abstractmethod
    async def handle_incoming_message(self, message: IncomingMessage):
        """Обработка входящего сообщения"""
