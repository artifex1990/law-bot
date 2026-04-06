"""Модель консультации"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Float, Text
from sqlalchemy.orm import relationship

from src.database.base import Base


class Consultation(Base):
    """Запрос на консультацию"""
    __tablename__ = "consultations"
    
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    direction = Column(String(100), nullable=False)
    status = Column(String(50), default="pending")
    scheduled_at = Column(DateTime, nullable=True)
    lawyer_id = Column(Integer, nullable=True)
    is_paid = Column(Boolean, default=False)
    payment_amount = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    chat = relationship("Chat", back_populates="consultations")
    user = relationship("User", back_populates="consultations")
