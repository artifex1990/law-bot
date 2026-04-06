"""Базовая конфигурация БД с async SQLAlchemy"""
from typing import AsyncIterator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase
from loguru import logger

from src.config.settings import settings


class Base(DeclarativeBase):
    """Базовый класс для моделей"""
    pass


# Синхронный URL для SQLite - aiosqlite требует sqlite+aiosqlite
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Получить сессию БД"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Инициализация БД - создание таблиц.
    Импорт моделей здесь, чтобы избежать циклического импорта (модели импортируют Base).
    """
    from src.database.models import (  # noqa: F401
        User,
        Chat,
        Message,
        ConversationStep,
        Consultation,
    )
    from src.database.models.telegram_models import (  # noqa: F401
        TelegramUser,
        TelegramChat,
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise
