"""Модель шага диалога"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from src.database.base import Base


class ConversationStep(Base):
    """Пройденный шаг диалога"""
    __tablename__ = "conversation_steps"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False, index=True)
    step_name = Column(String(100), nullable=False)
    step_data = Column(JSON, nullable=True)
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="conversation_steps")
