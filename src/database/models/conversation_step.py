"""Модель шага диалога"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConversationStep(Base):
    """Пройденный шаг диалога"""

    __tablename__ = "conversation_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    chat_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chats.id"),
        nullable=False,
        index=True,
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    step_data: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )

    chat = relationship("Chat", back_populates="conversation_steps")
