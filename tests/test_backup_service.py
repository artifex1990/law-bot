"""Tests: BackupService (all I/O and storage mocked)."""

import asyncio
import gzip
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from src.services.backup_service import (
    BACKUP_PREFIX,
    BACKUP_SUFFIX,
    BackupService,
)


@pytest.fixture
def backup_svc():
    with patch("src.services.backup_service.settings") as mock_settings:
        mock_settings.BACKUP_ENABLED = True
        mock_settings.BACKUP_STORAGE_TYPE = "local"
        mock_settings.BACKUP_INTERVAL_HOURS = 1
        mock_settings.BACKUP_RETENTION_DAYS = 30
        mock_settings.BACKUP_LOCAL_PATH = tempfile.mkdtemp()
        mock_settings.DATABASE_URL = "sqlite+aiosqlite:///./test.db"
        yield BackupService()


def test_make_filename():
    name = BackupService._make_filename()
    assert name.startswith(BACKUP_PREFIX)
    assert name.endswith(BACKUP_SUFFIX)


def test_parse_timestamp_valid():
    ts = BackupService._parse_timestamp("legal_bot_20260406_120000.sql.gz")
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 4
    assert ts.tzinfo is not None


def test_parse_timestamp_invalid():
    assert BackupService._parse_timestamp("bad_file.txt") is None
    assert BackupService._parse_timestamp("") is None


def test_parse_db_url_sqlite(backup_svc):
    with patch("src.services.backup_service.settings") as ms:
        ms.DATABASE_URL = "sqlite+aiosqlite:///./test.db"
        info = BackupService._parse_db_url()
    assert info["type"] == "sqlite"
    assert info["path"] == "./test.db"


def test_parse_db_url_postgres(backup_svc):
    with patch("src.services.backup_service.settings") as ms:
        ms.DATABASE_URL = "postgresql+asyncpg://user:pass@host:5432/mydb"
        info = BackupService._parse_db_url()
    assert info["type"] == "postgres"
    assert info["host"] == "host"
    assert info["user"] == "user"
    assert info["dbname"] == "mydb"


@pytest.mark.asyncio
async def test_create_backup_sqlite(backup_svc):
    """Full backup cycle with a fake SQLite file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        f.write(b"SQLite test data")
        db_path = f.name

    with patch.object(
        backup_svc,
        "_parse_db_url",
        return_value={"type": "sqlite", "path": db_path},
    ):
        result = await backup_svc.create_backup()

    assert result is not None
    assert result.startswith(BACKUP_PREFIX)

    stored = await asyncio.to_thread(
        lambda: list(Path(backup_svc.local_path).glob("*.sql.gz")),
    )
    assert len(stored) == 1
    with gzip.open(stored[0], "rb") as f:
        assert f.read() == b"SQLite test data"

    await asyncio.to_thread(lambda: Path(db_path).unlink(missing_ok=True))


@pytest.mark.asyncio
async def test_cleanup_local(backup_svc):
    """Old files are removed, fresh ones stay."""
    local = Path(backup_svc.local_path)
    await asyncio.to_thread(local.mkdir, parents=True, exist_ok=True)

    old = datetime.now(timezone.utc) - timedelta(days=60)
    old_name = f"{BACKUP_PREFIX}{old.strftime('%Y%m%d_%H%M%S')}{BACKUP_SUFFIX}"
    (local / old_name).write_bytes(b"old")

    new = datetime.now(timezone.utc)
    new_name = f"{BACKUP_PREFIX}{new.strftime('%Y%m%d_%H%M%S')}{BACKUP_SUFFIX}"
    (local / new_name).write_bytes(b"new")

    await backup_svc._cleanup_local()

    remaining = await asyncio.to_thread(
        lambda: list(local.glob(f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}")),
    )
    names = [f.name for f in remaining]
    assert old_name not in names
    assert new_name in names


@pytest.mark.asyncio
async def test_start_disabled():
    with patch("src.services.backup_service.settings") as ms:
        ms.BACKUP_ENABLED = False
        ms.BACKUP_STORAGE_TYPE = "local"
        ms.BACKUP_INTERVAL_HOURS = 1
        ms.BACKUP_RETENTION_DAYS = 30
        ms.BACKUP_LOCAL_PATH = "/tmp/bk"
        svc = BackupService()
        await svc.start()
        assert svc._task is None


@pytest.mark.asyncio
async def test_stop_no_task(backup_svc):
    await backup_svc.stop()  # no exception when task is None
