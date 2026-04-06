"""Абстрактный класс мессенджера"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class IncomingMessage:
    """Входящее сообщение от пользователя"""
    user_id: str
    chat_id: str
    content: str
    message_type: str
    message_id: str
    created_at: datetime
    extra_data: Optional[Dict[str, Any]] = None


@dataclass
class OutgoingMessage:
    """Исходящее сообщение бота"""
    chat_id: str
    content: str
    buttons: Optional[List[Dict[str, str]]] = None
    reply_markup: Optional[Any] = None
    parse_mode: Optional[str] = "HTML"


class AbstractMessenger(ABC):
    """Абстрактный класс для всех мессенджеров"""
    
    messenger_type: str = ""
    
    @abstractmethod
    async def start(self):
        """Запуск мессенджера"""
        pass
    
    @abstractmethod
    async def stop(self):
        """Остановка мессенджера"""
        pass
    
    @abstractmethod
    async def send_message(self, message: OutgoingMessage) -> bool:
        """Отправка сообщения"""
        pass
    
    @abstractmethod
    async def send_typing(self, chat_id: str):
        """Индикатор печати"""
        pass
    
    @abstractmethod
    async def handle_incoming_message(self, message: IncomingMessage):
        """Обработка входящего сообщения"""
        pass
