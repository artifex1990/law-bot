"""Проверки готовности сервисов (БД, бэкапы) для health/readiness."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from sqlalchemy import text

from src.config.settings import settings
from src.database.base import async_session_factory
from src.services.backup_service import BACKUP_PREFIX, BACKUP_SUFFIX


async def check_database() -> tuple[bool, str]:
    """Проверить соединение с БД (лёгкий SELECT 1)."""
    try:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        return False, str(exc)
    return True, ""


def _check_local_backup_health_sync() -> tuple[bool, str]:
    """Локальное хранилище: каталог, свежесть последнего файла."""
    p = Path(settings.BACKUP_LOCAL_PATH)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"fail: backup directory: {exc}"
    if not os.access(p, os.W_OK):
        return False, "fail: backup directory not writable"

    pattern = f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"
    files = list(p.glob(pattern))
    if not files:
        return True, "ok: awaiting first backup (no files yet)"

    newest = max(files, key=lambda f: f.stat().st_mtime)
    age_sec = time.time() - newest.stat().st_mtime
    max_age_sec = max(
        86400 * 2,
        3600 * settings.BACKUP_INTERVAL_HOURS * 3,
    )
    if age_sec > max_age_sec:
        h = int(age_sec // 3600)
        hm = int(max_age_sec // 3600)
        return False, f"fail: newest backup too old ({h}h, max {hm}h)"
    return True, "ok"


def _check_ftp_backup_config() -> tuple[bool, str]:
    """Минимальная проверка конфигурации FTP (без сетевого подключения)."""
    if not settings.BACKUP_FTP_HOST.strip():
        return False, "fail: BACKUP_FTP_HOST empty"
    if not settings.BACKUP_FTP_USER.strip():
        return False, "fail: BACKUP_FTP_USER empty"
    return True, "ok: ftp configured (connectivity not verified)"


def _check_s3_backup_config() -> tuple[bool, str]:
    """Минимальная проверка конфигурации S3."""
    if not settings.BACKUP_S3_BUCKET.strip():
        return False, "fail: BACKUP_S3_BUCKET empty"
    if not settings.BACKUP_S3_ACCESS_KEY.strip():
        return False, "fail: BACKUP_S3_ACCESS_KEY empty"
    if not settings.BACKUP_S3_SECRET_KEY.strip():
        return False, "fail: BACKUP_S3_SECRET_KEY empty"
    return True, "ok: s3 configured (connectivity not verified)"


async def check_backups() -> tuple[bool, str]:
    """Работоспособность цепочки бэкапов для readiness."""
    if not settings.BACKUP_ENABLED:
        return True, "disabled"

    st = (settings.BACKUP_STORAGE_TYPE or "local").strip().lower()
    if st == "local":
        return await asyncio.to_thread(_check_local_backup_health_sync)
    if st == "ftp":
        return _check_ftp_backup_config()
    if st == "s3":
        return _check_s3_backup_config()
    return False, f"fail: unknown BACKUP_STORAGE_TYPE {st!r}"


async def run_ready_checks() -> dict:
    """Сводка для readiness: БД и (если включено) бэкапы."""
    db_ok, db_err = await check_database()
    backup_ok, backup_msg = await check_backups()

    checks: dict[str, str] = {
        "database": "ok" if db_ok else f"fail: {db_err}",
        "backup": backup_msg,
    }
    ready = db_ok and backup_ok
    return {
        "status": "ready" if ready else "unready",
        "ready": ready,
        "checks": checks,
    }
