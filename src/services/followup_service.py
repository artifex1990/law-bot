"""Сервис догоняющих напоминаний.

Периодически проверяет неактивные чаты и отправляет
напоминания по расписанию: 1ч, 12ч, 24ч, 72ч.
После последнего интервала чат завершается.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select, update

from src.config.settings import settings
from src.database.base import async_session_factory
from src.database.models import Chat, User
from src.messengers.base import OutgoingMessage


class FollowupService:
    """Фоновый сервис напоминаний."""

    def __init__(self, messenger):
        self.messenger = messenger
        self._task: asyncio.Task | None = None
        self._running = False

        self.intervals: list[timedelta] = [
            timedelta(hours=int(h)) for h in settings.FOLLOWUP_INTERVALS_HOURS
        ]
        self.messages: list[str] = [str(m) for m in settings.FOLLOWUP_MESSAGES]

    async def start(self) -> None:
        if not settings.FOLLOWUP_ENABLED:
            logger.info("Followup service disabled")
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "Followup service started "
            f"(intervals={settings.FOLLOWUP_INTERVALS_HOURS}h)"
        )

    async def stop(self) -> None:
        import contextlib

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Followup service stopped")

    async def _loop(self) -> None:
        interval_sec = settings.FOLLOWUP_CHECK_INTERVAL_MIN * 60
        while self._running:
            try:
                await self._check_inactive_chats()
            except Exception as exc:
                logger.error(f"Followup check error: {exc}")
            await asyncio.sleep(interval_sec)

    @staticmethod
    def _ensure_aware(dt: datetime) -> datetime:
        """Гарантировать timezone-aware (UTC) datetime."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    async def _check_inactive_chats(self) -> None:
        """Найти неактивные чаты и отправить напоминания."""
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            query = (
                select(Chat, User)
                .join(User, Chat.user_id == User.id)
                .where(Chat.status == "active")
            )
            result = await session.execute(query)
            rows = result.all()

        for chat, user in rows:
            activity = self._ensure_aware(chat.last_activity_at)
            since = now - activity
            sent = chat.reminder_count

            idx = self._pick_reminder_index(since, sent)
            if idx is None:
                if self._should_complete(since):
                    await self._mark_completed(chat.id)
                continue

            text = self._get_message(idx)
            chat_id = user.messenger_user_id
            await self._send_reminder(chat_id, text)
            await self._record_reminder(chat.id, idx + 1)

    def _pick_reminder_index(
        self,
        since: timedelta,
        already_sent: int,
    ) -> int | None:
        """Выбрать индекс напоминания, или None."""
        for i, threshold in enumerate(self.intervals):
            if i < already_sent:
                continue
            if since >= threshold:
                return i
        return None

    def _should_complete(self, since: timedelta) -> bool:
        """Нужно ли завершить чат (прошло > последний интервал)."""
        if not self.intervals:
            return False
        last: timedelta = self.intervals[-1]
        return since > last

    def _get_message(self, index: int) -> str:
        if index < len(self.messages):
            return str(self.messages[index])
        if self.messages:
            return str(self.messages[-1])
        return ""

    async def _send_reminder(
        self,
        chat_id: str,
        text: str,
    ) -> None:
        try:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=chat_id,
                    content=text,
                    parse_mode="HTML",
                    buttons=[
                        {
                            "text": "▶️ Продолжить консультацию",
                            "value": "/start",
                        }
                    ],
                )
            )
            logger.info(f"Followup sent to {chat_id}")
        except Exception as exc:
            logger.error(f"Failed followup to {chat_id}: {exc}")

    @staticmethod
    async def _record_reminder(
        chat_id: int,
        count: int,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            await session.execute(
                update(Chat)
                .where(Chat.id == chat_id)
                .values(
                    reminder_count=count,
                    last_reminder_at=now,
                )
            )
            await session.commit()

    @staticmethod
    async def _mark_completed(chat_id: int) -> None:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            await session.execute(
                update(Chat)
                .where(Chat.id == chat_id)
                .values(
                    status="completed",
                    completed_at=now,
                )
            )
            await session.commit()
        logger.info(
            f"Chat {chat_id} auto-completed (no response after reminders)"
        )
