"""Alembic env — поддержка async SQLAlchemy + .env конфигурации."""

import asyncio
import sys
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

from src.config.settings import settings  # noqa: E402
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

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Миграции в offline-режиме (генерация SQL)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Миграции в online-режиме (async engine)."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
