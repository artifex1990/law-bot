"""Тесты readiness: БД и бэкапы."""

import os
import time
from unittest.mock import AsyncMock, patch

import pytest

from src.config.settings import settings
from src.services.backup_service import BACKUP_PREFIX, BACKUP_SUFFIX
from src.services.health_service import (
    check_backups,
    run_ready_checks,
)


@pytest.mark.asyncio
async def test_check_backups_disabled(monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", False)
    ok, msg = await check_backups()
    assert ok is True
    assert msg == "disabled"


@pytest.mark.asyncio
async def test_check_backups_local_ok_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_STORAGE_TYPE", "local")
    monkeypatch.setattr(settings, "BACKUP_LOCAL_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_INTERVAL_HOURS", 1)
    ok, msg = await check_backups()
    assert ok is True
    assert "awaiting first backup" in msg


@pytest.mark.asyncio
async def test_check_backups_local_fails_stale_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_STORAGE_TYPE", "local")
    monkeypatch.setattr(settings, "BACKUP_LOCAL_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_INTERVAL_HOURS", 1)

    name = f"{BACKUP_PREFIX}20200101_000000{BACKUP_SUFFIX}"
    p = tmp_path / name
    p.write_bytes(b"x")
    old = time.time() - 86400 * 10
    os.utime(p, (old, old))

    ok, msg = await check_backups()
    assert ok is False
    assert "too old" in msg


@pytest.mark.asyncio
async def test_check_backups_ftp_requires_host(monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_STORAGE_TYPE", "ftp")
    monkeypatch.setattr(settings, "BACKUP_FTP_HOST", "")
    monkeypatch.setattr(settings, "BACKUP_FTP_USER", "u")
    ok, msg = await check_backups()
    assert ok is False
    assert "BACKUP_FTP_HOST" in msg


@pytest.mark.asyncio
async def test_run_ready_checks_includes_backup_key(monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", False)

    with patch(
        "src.services.health_service.check_database",
        new_callable=AsyncMock,
        return_value=(True, ""),
    ):
        data = await run_ready_checks()

    assert "backup" in data["checks"]
    assert data["checks"]["backup"] == "disabled"


@pytest.mark.asyncio
async def test_check_backups_local_fresh_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_ENABLED", True)
    monkeypatch.setattr(settings, "BACKUP_STORAGE_TYPE", "local")
    monkeypatch.setattr(settings, "BACKUP_LOCAL_PATH", str(tmp_path))
    monkeypatch.setattr(settings, "BACKUP_INTERVAL_HOURS", 1)

    name = f"{BACKUP_PREFIX}20990101_120000{BACKUP_SUFFIX}"
    (tmp_path / name).write_bytes(b"x")

    ok, msg = await check_backups()
    assert ok is True
    assert msg == "ok"
