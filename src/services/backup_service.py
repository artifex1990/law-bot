"""Сервис резервного копирования БД.

Поддерживаемые хранилища (BACKUP_STORAGE_TYPE):
  local — локальная папка (BACKUP_LOCAL_PATH)
  ftp   — FTP / FTPS сервер
  s3    — S3-совместимое облако

Расписание и ретеншн настраиваются через .env:
  BACKUP_INTERVAL_HOURS  — интервал (по умолчанию 1 ч)
  BACKUP_RETENTION_DAYS  — срок хранения (30 дней)
"""

import asyncio
import contextlib
import gzip
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from ftplib import FTP, FTP_TLS
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from src.config.settings import settings

BACKUP_PREFIX = "legal_bot_"
BACKUP_SUFFIX = ".sql.gz"


class BackupService:
    """Автоматическое резервное копирование БД"""

    def __init__(self):
        self.storage_type: str = settings.BACKUP_STORAGE_TYPE
        self.interval_hours: int = settings.BACKUP_INTERVAL_HOURS
        self.interval_sec: int = self.interval_hours * 3600
        self.retention = timedelta(days=settings.BACKUP_RETENTION_DAYS)
        self.local_path = Path(settings.BACKUP_LOCAL_PATH)
        self._running = False
        self._task: asyncio.Task | None = None

    # -------------------------------------------------------
    # Публичный API
    # -------------------------------------------------------

    async def start(self):
        """Запустить планировщик бэкапов"""
        if not settings.BACKUP_ENABLED:
            logger.info("Backups disabled (BACKUP_ENABLED=False)")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop())
        hours = self.interval_hours
        days = settings.BACKUP_RETENTION_DAYS
        logger.info(
            f"Backup scheduler started: every {hours}h, retain {days}d, storage={self.storage_type}"
        )

    async def stop(self):
        """Остановить планировщик"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Backup scheduler stopped")

    async def create_backup(self) -> str | None:
        """Создать один бэкап."""
        try:
            db_info = self._parse_db_url()
            filename = self._make_filename()

            with tempfile.TemporaryDirectory() as tmpdir:
                gz_path = Path(tmpdir) / filename

                if db_info["type"] == "sqlite":
                    await self._dump_sqlite(db_info["path"], gz_path)
                else:
                    await self._dump_postgres(db_info, gz_path)

                await self._store(gz_path)

            await self._cleanup()
            logger.info(f"Backup created: {filename}")
            return filename

        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return None

    # -------------------------------------------------------
    # Планировщик
    # -------------------------------------------------------

    async def _loop(self):
        """Фоновый цикл"""
        while self._running:
            await self.create_backup()
            await asyncio.sleep(self.interval_sec)

    # -------------------------------------------------------
    # Дамп БД
    # -------------------------------------------------------

    @staticmethod
    def _parse_db_url() -> dict:
        url = settings.DATABASE_URL
        if url.startswith("sqlite"):
            db_path = url.split("///", 1)[-1]
            return {"type": "sqlite", "path": db_path}

        clean = url.split("+", 1)[0] + "://" + url.split("://", 1)[-1]
        parsed = urlparse(clean)
        return {
            "type": "postgres",
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 5432,
            "user": parsed.username or "postgres",
            "password": parsed.password or "",
            "dbname": (parsed.path or "/postgres").lstrip("/"),
        }

    async def _dump_sqlite(self, db_path: str, gz_path: Path):
        src = Path(db_path)
        if not await asyncio.to_thread(src.exists):
            raise FileNotFoundError(f"SQLite file not found: {src}")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._gzip_file, src, gz_path)

    async def _dump_postgres(self, db_info: dict, gz_path: Path):
        env = {**os.environ, "PGPASSWORD": db_info["password"]}
        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h",
            db_info["host"],
            "-p",
            str(db_info["port"]),
            "-U",
            db_info["user"],
            "-d",
            db_info["dbname"],
            "--format=custom",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            msg = stderr.decode().strip()
            raise RuntimeError(f"pg_dump error: {msg}")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._write_gz, gz_path, stdout)

    # -------------------------------------------------------
    # Хранилище — роутинг
    # -------------------------------------------------------

    async def _store(self, local_file: Path):
        if self.storage_type == "local":
            await self._store_local(local_file)
        elif self.storage_type == "ftp":
            await self._store_ftp(local_file)
        elif self.storage_type == "s3":
            await self._store_s3(local_file)
        else:
            raise ValueError(
                f"Unknown BACKUP_STORAGE_TYPE: {self.storage_type}"
            )

    async def _cleanup(self):
        try:
            if self.storage_type == "local":
                await self._cleanup_local()
            elif self.storage_type == "ftp":
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._cleanup_ftp)
            elif self.storage_type == "s3":
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._cleanup_s3)
        except Exception as e:
            logger.warning(f"Cleanup old backups error: {e}")

    # -------------------------------------------------------
    # LOCAL
    # -------------------------------------------------------

    async def _store_local(self, local_file: Path):
        await asyncio.to_thread(
            self.local_path.mkdir,
            parents=True,
            exist_ok=True,
        )
        dest = self.local_path / local_file.name
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            shutil.copy2,
            str(local_file),
            str(dest),
        )

    def _cleanup_local_sync(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention
        if not self.local_path.exists():
            return
        pattern = f"{BACKUP_PREFIX}*{BACKUP_SUFFIX}"
        for f in self.local_path.glob(pattern):
            ts = self._parse_timestamp(f.name)
            if ts and ts < cutoff:
                f.unlink()
                logger.debug(f"Deleted old backup: {f.name}")

    async def _cleanup_local(self):
        await asyncio.to_thread(self._cleanup_local_sync)

    # -------------------------------------------------------
    # FTP / FTPS
    # -------------------------------------------------------

    async def _store_ftp(self, local_file: Path):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._ftp_upload, local_file)

    def _ftp_connect(self) -> FTP:
        use_tls = settings.BACKUP_FTP_TLS
        ftp: FTP = FTP_TLS() if use_tls else FTP()
        ftp.connect(
            settings.BACKUP_FTP_HOST,
            settings.BACKUP_FTP_PORT,
        )
        ftp.login(
            settings.BACKUP_FTP_USER,
            settings.BACKUP_FTP_PASSWORD,
        )
        if use_tls and isinstance(ftp, FTP_TLS):
            ftp.prot_p()
        remote = settings.BACKUP_FTP_PATH
        if remote:
            self._ftp_ensure_dir(ftp, remote)
            ftp.cwd(remote)
        return ftp

    @staticmethod
    def _ftp_ensure_dir(ftp: FTP, path: str):
        dirs = path.strip("/").split("/")
        for d in dirs:
            try:
                ftp.cwd(d)
            except Exception:
                ftp.mkd(d)
                ftp.cwd(d)
        ftp.cwd("/")

    def _ftp_upload(self, local_file: Path):
        with (
            self._ftp_connect() as ftp,
            open(local_file, "rb") as f,
        ):
            ftp.storbinary(f"STOR {local_file.name}", f)

    def _cleanup_ftp(self):
        cutoff = datetime.now(timezone.utc) - self.retention
        with self._ftp_connect() as ftp:
            for name in ftp.nlst():
                is_backup = name.startswith(BACKUP_PREFIX) and name.endswith(
                    BACKUP_SUFFIX
                )
                if not is_backup:
                    continue
                ts = self._parse_timestamp(name)
                if ts and ts < cutoff:
                    ftp.delete(name)
                    logger.debug(f"Deleted old FTP backup: {name}")

    # -------------------------------------------------------
    # S3
    # -------------------------------------------------------

    async def _store_s3(self, local_file: Path):
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._s3_upload, local_file)

    def _s3_client(self):
        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for S3 backups. Install: pip install boto3"
            ) from exc
        return boto3.client(
            "s3",
            endpoint_url=(settings.BACKUP_S3_ENDPOINT or None),
            aws_access_key_id=settings.BACKUP_S3_ACCESS_KEY,
            aws_secret_access_key=settings.BACKUP_S3_SECRET_KEY,
            region_name=settings.BACKUP_S3_REGION or None,
        )

    def _s3_key(self, filename: str) -> str:
        prefix = settings.BACKUP_S3_PREFIX
        if prefix:
            return f"{prefix.strip('/')}/{filename}"
        return filename

    def _s3_upload(self, local_file: Path):
        client = self._s3_client()
        key = self._s3_key(local_file.name)
        client.upload_file(
            str(local_file),
            settings.BACKUP_S3_BUCKET,
            key,
        )

    def _cleanup_s3(self):
        client = self._s3_client()
        cutoff = datetime.now(timezone.utc) - self.retention
        prefix = settings.BACKUP_S3_PREFIX
        pfx = f"{prefix.strip('/')}/" if prefix else ""

        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(
            Bucket=settings.BACKUP_S3_BUCKET,
            Prefix=pfx,
        )
        for page in pages:
            for obj in page.get("Contents", []):
                key = obj["Key"]
                name = key.rsplit("/", 1)[-1]
                is_backup = name.startswith(BACKUP_PREFIX) and name.endswith(
                    BACKUP_SUFFIX
                )
                if not is_backup:
                    continue
                ts = self._parse_timestamp(name)
                if ts and ts < cutoff:
                    client.delete_object(
                        Bucket=settings.BACKUP_S3_BUCKET,
                        Key=key,
                    )
                    logger.debug(f"Deleted old S3 backup: {key}")

    # -------------------------------------------------------
    # Утилиты
    # -------------------------------------------------------

    @staticmethod
    def _make_filename() -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{BACKUP_PREFIX}{ts}{BACKUP_SUFFIX}"

    @staticmethod
    def _gzip_file(src: Path, dst: Path):
        with (
            open(src, "rb") as f_in,
            gzip.open(dst, "wb") as f_out,
        ):
            shutil.copyfileobj(f_in, f_out)

    @staticmethod
    def _write_gz(dst: Path, data: bytes):
        with gzip.open(dst, "wb") as f:
            f.write(data)

    @staticmethod
    def _parse_timestamp(filename: str) -> datetime | None:
        """Извлечь дату из имени файла
        legal_bot_20260406_120000.sql.gz"""
        try:
            no_prefix = filename.replace(BACKUP_PREFIX, "")
            core = no_prefix.replace(BACKUP_SUFFIX, "")
            dt = datetime.strptime(  # noqa: DTZ007
                core, "%Y%m%d_%H%M%S"
            )
            return dt.replace(tzinfo=timezone.utc)
        except (ValueError, IndexError):
            return None
