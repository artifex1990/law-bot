"""Telegram-специфичные модели (опционально для расширенной аналитики)"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship

from src.database.base import Base


class TelegramUser(Base):
    """Пользователь Telegram - расширенные данные"""
    __tablename__ = "telegram_users"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    language_code = Column(String(10), nullable=True)
    is_bot = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TelegramChat(Base):
    """Чат Telegram"""
    __tablename__ = "telegram_chats"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    telegram_chat_id = Column(Integer, unique=True, nullable=False, index=True)
    chat_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
