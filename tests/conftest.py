"""Shared fixtures for all tests.

Uses a separate in-memory SQLite DB so production data is never touched.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.database.base import Base  # noqa: E402
from src.database.models import (  # noqa: E402, F401
    Chat,
    Consultation,
    ConversationStep,
    Message,
    User,
)
from src.database.models.telegram_models import (  # noqa: E402, F401
    TelegramChat,
    TelegramUser,
)

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def mock_messenger():
    messenger = AsyncMock()
    messenger.messenger_type = "telegram"
    messenger.build_inline_keyboard.return_value = None
    messenger.send_message.return_value = True
    return messenger
