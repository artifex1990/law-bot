"""Проверки готовности сервисов (БД и др.) для health/readiness."""

from __future__ import annotations

from sqlalchemy import text

from src.database.base import async_session_factory


async def check_database() -> tuple[bool, str]:
    """Проверить соединение с БД (лёгкий SELECT 1)."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        return False, str(exc)
    return True, ""


async def run_ready_checks() -> dict:
    """Сводка для readiness: все обязательные зависимости."""
    db_ok, db_err = await check_database()
    checks: dict[str, str] = {
        "database": "ok" if db_ok else f"fail: {db_err}",
    }
    ready = db_ok
    return {
        "status": "ready" if ready else "unready",
        "ready": ready,
        "checks": checks,
    }
