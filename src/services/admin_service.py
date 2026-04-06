"""Сервис администрирования — статистика и доступ к данным."""

# pylint: disable=not-callable

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Chat, Consultation, User


class AdminService:
    """Запросы к БД для административной панели."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_stats(self) -> dict:
        """Общая статистика по боту."""
        now = datetime.now(timezone.utc)
        day_ago = now - timedelta(days=1)
        week_ago = now - timedelta(days=7)

        total_users = await self._count(select(func.count(User.id)))
        total_chats = await self._count(select(func.count(Chat.id)))
        total_consultations = await self._count(
            select(func.count(Consultation.id))
        )

        active_chats = await self._count(
            select(func.count(Chat.id)).where(Chat.status == "active")
        )
        completed_chats = await self._count(
            select(func.count(Chat.id)).where(Chat.status == "completed")
        )

        users_24h = await self._count(
            select(func.count(User.id)).where(User.created_at >= day_ago)
        )
        users_7d = await self._count(
            select(func.count(User.id)).where(User.created_at >= week_ago)
        )
        chats_24h = await self._count(
            select(func.count(Chat.id)).where(Chat.started_at >= day_ago)
        )

        directions = await self._direction_stats()

        return {
            "total_users": total_users,
            "total_chats": total_chats,
            "total_consultations": total_consultations,
            "active_chats": active_chats,
            "completed_chats": completed_chats,
            "users_24h": users_24h,
            "users_7d": users_7d,
            "chats_24h": chats_24h,
            "directions": directions,
        }

    async def get_recent_users(self, limit: int = 20) -> list[dict]:
        """Последние пользователи с контактами."""
        query = (
            select(User)
            .where(User.phone.isnot(None))
            .order_by(User.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        users = result.scalars().all()

        return [
            {
                "id": u.id,
                "name": u.full_name or "—",
                "phone": u.phone or "—",
                "email": u.email or "—",
                "messenger": u.messenger_type,
                "created": u.created_at.strftime("%d.%m.%Y %H:%M"),
            }
            for u in users
        ]

    async def get_recent_consultations(self, limit: int = 20) -> list[dict]:
        """Последние заявки на консультацию."""
        query = (
            select(Consultation, User)
            .join(User, Consultation.user_id == User.id)
            .order_by(Consultation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows = result.all()

        return [
            {
                "id": c.id,
                "direction": c.direction,
                "status": c.status,
                "is_paid": c.is_paid,
                "name": u.full_name or "—",
                "phone": u.phone or "—",
                "created": c.created_at.strftime("%d.%m.%Y %H:%M"),
            }
            for c, u in rows
        ]

    async def export_users_csv(self) -> str:
        """Экспорт пользователей с контактами в CSV-строку."""
        query = (
            select(User)
            .where(User.phone.isnot(None))
            .order_by(User.created_at.desc())
        )
        result = await self.session.execute(query)
        users = result.scalars().all()

        lines = ["Имя;Телефон;Email;Мессенджер;Дата"]
        for u in users:
            lines.append(
                f"{u.full_name or ''};{u.phone or ''};"
                f"{u.email or ''};{u.messenger_type};"
                f"{u.created_at.strftime('%d.%m.%Y %H:%M')}"
            )
        return "\n".join(lines)

    async def _direction_stats(self) -> list[tuple[str, int]]:
        query = (
            select(Consultation.direction, func.count(Consultation.id))
            .group_by(Consultation.direction)
            .order_by(func.count(Consultation.id).desc())
        )
        result = await self.session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def _count(self, query) -> int:
        result = await self.session.execute(query)
        return result.scalar() or 0
