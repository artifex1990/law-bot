"""Модель чата"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Chat(Base):
    """Чат/Диалог"""

    __tablename__ = "chats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    direction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active")

    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat")
    conversation_steps = relationship("ConversationStep", back_populates="chat")
    consultations = relationship("Consultation", back_populates="chat")
