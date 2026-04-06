"""Сервис консультаций - работа с БД через ORM"""

from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.validators import normalize_ru_phone
from src.database.models import (
    Chat,
    Consultation,
    ConversationStep,
    Message,
    User,
)


class ConsultationService:
    """Сервис управления консультациями"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(
        self,
        messenger_user_id: str,
        messenger_type: str,
    ) -> User:
        """Получить или создать пользователя"""
        query = select(User).where(
            User.messenger_user_id == messenger_user_id,
            User.messenger_type == messenger_type,
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                messenger_type=messenger_type,
                messenger_user_id=messenger_user_id,
            )
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
            logger.info(f"Created user {user.id}")

        return user

    async def close_active_chats(self, user_id: int) -> None:
        """Закрыть все активные чаты пользователя."""
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(Chat)
            .where(Chat.user_id == user_id, Chat.status == "active")
            .values(status="abandoned", completed_at=now)
        )
        await self.session.flush()

    async def create_chat(self, user_id: int) -> Chat:
        """Создать новый чат (предварительно закрывая старые)."""
        await self.close_active_chats(user_id)
        chat = Chat(user_id=user_id, status="active")
        self.session.add(chat)
        await self.session.flush()
        await self.session.refresh(chat)
        logger.info(f"Created chat {chat.id}")
        return chat

    async def update_chat_direction(
        self,
        chat_id: int,
        direction: str,
    ):
        """Обновить направление чата"""
        query = select(Chat).where(Chat.id == chat_id)
        result = await self.session.execute(query)
        chat = result.scalar_one_or_none()
        if chat:
            chat.direction = direction
            await self.session.flush()

    async def mark_chat_completed(self, chat_id: int) -> None:
        """Отметить чат как завершённый"""
        query = select(Chat).where(Chat.id == chat_id)
        result = await self.session.execute(query)
        chat = result.scalar_one_or_none()
        if chat:
            chat.status = "completed"
            chat.completed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def mark_chat_abandoned(self, chat_id: int) -> None:
        """Отметить чат как заброшенный"""
        query = select(Chat).where(Chat.id == chat_id)
        result = await self.session.execute(query)
        chat = result.scalar_one_or_none()
        if chat:
            chat.status = "abandoned"
            chat.completed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def touch_chat_activity(self, chat_id: int) -> None:
        """Обновить время последней активности."""
        await self.session.execute(
            update(Chat)
            .where(Chat.id == chat_id)
            .values(
                last_activity_at=datetime.now(timezone.utc),
                reminder_count=0,
                last_reminder_at=None,
            )
        )
        await self.session.flush()

    async def save_conversation_step(
        self,
        chat_id: int,
        step_name: str,
        step_data: dict,
    ):
        """Сохранить шаг диалога"""
        step = ConversationStep(
            chat_id=chat_id,
            step_name=step_name,
            step_data=step_data,
        )
        self.session.add(step)
        await self.session.flush()

    async def create_consultation(
        self,
        chat_id: int,
        user_id: int,
        direction: str,
        status: str = "pending",
        **kwargs,
    ) -> Consultation:
        """Создать заявку на консультацию"""
        consultation = Consultation(
            chat_id=chat_id,
            user_id=user_id,
            direction=direction,
            status=status,
            is_paid=kwargs.get("is_paid", False),
            payment_amount=kwargs.get("payment_amount"),
            notes=kwargs.get("notes"),
        )
        self.session.add(consultation)
        await self.session.flush()
        await self.session.refresh(consultation)
        logger.info(f"Created consultation {consultation.id}")
        return consultation

    async def get_consultation_with_user(
        self,
        consultation_id: int,
    ) -> tuple[Consultation, User] | None:
        """Заявка с пользователем по id."""
        query = (
            select(Consultation, User)
            .join(User, Consultation.user_id == User.id)
            .where(Consultation.id == consultation_id)
        )
        result = await self.session.execute(query)
        row = result.one_or_none()
        return (row[0], row[1]) if row else None

    async def search_consultations(
        self,
        *,
        phone: str | None = None,
        email: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[tuple[Consultation, User]]:
        """Поиск заявок по телефону, email и/или статусу."""
        query = select(Consultation, User).join(
            User, Consultation.user_id == User.id
        )
        if phone:
            p = phone.strip()
            norm = normalize_ru_phone(p)
            if norm:
                query = query.where(User.phone == norm)
            else:
                query = query.where(User.phone == p)
        if email:
            em = email.strip().lower()
            query = query.where(
                User.email.isnot(None),
                func.lower(User.email) == em,
            )
        if status:
            query = query.where(Consultation.status == status.strip())
        query = query.order_by(Consultation.created_at.desc()).limit(
            min(max(limit, 1), 200),
        )
        result = await self.session.execute(query)
        return [(c, u) for c, u in result.all()]

    async def update_user_contacts(
        self,
        user_id: int,
        full_name: str | None = None,
        phone: str | None = None,
        email: str | None = None,
    ):
        """Обновить контакты пользователя"""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if user:
            if full_name:
                user.full_name = full_name
            if phone:
                user.phone = phone
            if email:
                user.email = email
            await self.session.flush()

    # ---- Работа с завершёнными клиентами ----

    async def set_privacy_consent(self, user_id: int) -> None:
        """Зафиксировать согласие на обработку персональных данных."""
        now = datetime.now(timezone.utc)
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(privacy_consent_at=now, updated_at=now),
        )
        await self.session.flush()

    async def user_has_contacts(self, user_id: int) -> bool:
        """Проверить, есть ли у пользователя контакты."""
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            return False
        return bool(user.phone or user.full_name)

    async def get_last_completed_chat(
        self,
        user_id: int,
    ) -> Chat | None:
        """Последний завершённый чат пользователя."""
        query = (
            select(Chat)
            .where(
                Chat.user_id == user_id,
                Chat.status == "completed",
            )
            .order_by(Chat.completed_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    # ---- Удаление персональных данных ----

    async def delete_user_data(self, user_id: int) -> bool:
        """Полностью удалить данные пользователя.

        Удаляет: consultations, conversation_steps,
        messages, chats, user.
        """
        query = select(User).where(User.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            return False

        chat_ids_q = select(Chat.id).where(Chat.user_id == user_id)
        chat_ids = await self.session.execute(chat_ids_q)
        cids = [r[0] for r in chat_ids.all()]

        if cids:
            await self.session.execute(
                delete(Consultation).where(Consultation.chat_id.in_(cids))
            )
            await self.session.execute(
                delete(ConversationStep).where(
                    ConversationStep.chat_id.in_(cids)
                )
            )
            await self.session.execute(
                delete(Message).where(Message.chat_id.in_(cids))
            )
            await self.session.execute(
                delete(Chat).where(Chat.user_id == user_id)
            )

        await self.session.execute(
            delete(Consultation).where(Consultation.user_id == user_id)
        )
        await self.session.execute(delete(User).where(User.id == user_id))
        await self.session.flush()

        logger.info(f"Deleted all data for user {user_id}")
        return True
