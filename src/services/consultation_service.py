"""Сервис консультаций - работа с БД через ORM"""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from src.database.models import User, Chat, Consultation, ConversationStep


class ConsultationService:
    """Сервис управления консультациями"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(
        self, messenger_user_id: str, messenger_type: str
    ) -> User:
        """Получить или создать пользователя"""
        result = await self.session.execute(
            select(User).where(
                User.messenger_user_id == messenger_user_id,
                User.messenger_type == messenger_type
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                messenger_type=messenger_type,
                messenger_user_id=messenger_user_id
            )
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
            logger.info(f"Created user {user.id}")

        return user

    async def create_chat(self, user_id: int) -> Chat:
        """Создать новый чат"""
        chat = Chat(user_id=user_id, status="active")
        self.session.add(chat)
        await self.session.flush()
        await self.session.refresh(chat)
        logger.info(f"Created chat {chat.id}")
        return chat

    async def update_chat_direction(self, chat_id: int, direction: str):
        """Обновить направление чата"""
        result = await self.session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            setattr(chat, "direction", direction)
            await self.session.flush()

    async def mark_chat_completed(self, chat_id: int):
        """Отметить чат как завершённый"""
        result = await self.session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            setattr(chat, "status", "completed")
            setattr(chat, "completed_at", datetime.now(datetime.timezone.utc))
            await self.session.flush()

    async def mark_chat_abandoned(self, chat_id: int):
        """Отметить чат как заброшенный"""
        result = await self.session.execute(
            select(Chat).where(Chat.id == chat_id)
        )
        chat = result.scalar_one_or_none()
        if chat:
            setattr(chat, "status", "abandoned")
            setattr(chat, "completed_at", datetime.now(datetime.timezone.utc))
            await self.session.flush()

    async def save_conversation_step(
        self, chat_id: int, step_name: str, step_data: dict
    ):
        """Сохранить шаг диалога"""
        step = ConversationStep(
            chat_id=chat_id,
            step_name=step_name,
            step_data=step_data
        )
        self.session.add(step)
        await self.session.flush()

    async def create_consultation(
        self,
        chat_id: int,
        user_id: int,
        direction: str,
        status: str = "pending",
        **kwargs
    ) -> Consultation:
        """Создать заявку на консультацию"""
        consultation = Consultation(
            chat_id=chat_id,
            user_id=user_id,
            direction=direction,
            status=status,
            is_paid=kwargs.get('is_paid', False),
            payment_amount=kwargs.get('payment_amount'),
            notes=kwargs.get('notes')
        )
        self.session.add(consultation)
        await self.session.flush()
        await self.session.refresh(consultation)
        logger.info(f"Created consultation {consultation.id}")
        return consultation

    async def update_user_contacts(
        self,
        user_id: int,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None
    ):
        """Обновить контакты пользователя"""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            if full_name:
                setattr(user, "full_name", full_name)
            if phone:
                setattr(user, "phone", phone)
            if email:
                setattr(user, "email", email)
            await self.session.flush()
