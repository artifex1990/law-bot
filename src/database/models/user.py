"""Модель пользователя"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """Пользователь системы"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    messenger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    messenger_user_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Согласие на обработку ПДн (ФЗ-152); сбрасывается при удалении
    # № пользователя из БД
    privacy_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    chats = relationship("Chat", back_populates="user")
    consultations = relationship("Consultation", back_populates="user")
