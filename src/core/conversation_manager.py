"""Менеджер диалогов - управление состояниями и шагами"""

import re
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.algorithms.loader import AlgorithmLoader
from src.core.algorithm_engine import Step
from src.database.base import async_session_factory
from src.messengers.base import IncomingMessage, OutgoingMessage
from src.services.consultation_service import ConsultationService


class ConversationContext:
    """Контекст активного диалога"""

    def __init__(self, chat_id: str, user_id: str, messenger_type: str):
        self.chat_id = chat_id
        self.user_id = user_id
        self.messenger_type = messenger_type
        self.current_step: str | None = None
        self.direction: str | None = None
        self.data: dict[str, Any] = {}
        self.chat_db_id: int | None = None
        self.user_db_id: int | None = None
        self.created_at = datetime.now(tz=UTC)

    def set_step(self, step: str):
        self.current_step = step

    def update_data(self, key: str, value: Any):
        self.data[key] = value

    def get_data(self, key: str, default=None) -> Any:
        return self.data.get(key, default)


class ConversationManager:
    """Менеджер диалогов"""

    def __init__(self, messenger):
        self.messenger = messenger
        self.algorithm_loader = AlgorithmLoader()
        self.active_conversations: dict[str, ConversationContext] = {}

    def _context_key(self, message: IncomingMessage) -> str:
        return f"{message.user_id}_{message.chat_id}"

    def _get_or_create_context(self, message: IncomingMessage) -> ConversationContext:
        key = self._context_key(message)
        if key not in self.active_conversations:
            self.active_conversations[key] = ConversationContext(
                chat_id=message.chat_id,
                user_id=message.user_id,
                messenger_type=self.messenger.messenger_type,
            )
        return self.active_conversations[key]

    async def process_message(self, message: IncomingMessage):
        """Обработка входящего сообщения"""
        logger.info(f"Message from {message.user_id}: {message.content[:50]}...")

        if message.content == "/start":
            await self._handle_start(message)
        elif message.content == "/restart":
            await self._handle_restart(message)
        elif message.content == "/cancel":
            await self._handle_cancel(message)
        elif message.content == "/help":
            await self._handle_help(message)
        else:
            await self._handle_user_input(message)

    async def _handle_start(self, message: IncomingMessage):
        """Команда /start - начало консультации"""
        context = self._get_or_create_context(message)
        context.data.clear()
        context.direction = None
        context.current_step = "greeting"

        async with async_session_factory() as session:
            service = ConsultationService(session)
            user = await service.get_or_create_user(
                message.user_id,
                self.messenger.messenger_type,
            )
            chat = await service.create_chat(user.id)
            await session.commit()
            context.user_db_id = user.id
            context.chat_db_id = chat.id

        algorithm = self.algorithm_loader.load_main_algorithm()
        greeting = algorithm.get_step("greeting")
        direction_step = algorithm.get_step("direction_selection")

        combined_content = greeting.content + "\n\n" + direction_step.content
        response = OutgoingMessage(
            chat_id=context.chat_id,
            content=combined_content,
            buttons=direction_step.buttons,
            reply_markup=self.messenger.build_inline_keyboard(direction_step.buttons),
            parse_mode="HTML",
        )
        await self.messenger.send_message(response)
        context.set_step("direction_selection")

    async def _handle_restart(self, message: IncomingMessage):
        """Команда /restart - начать заново"""
        key = self._context_key(message)
        self.active_conversations.pop(key, None)
        await self._handle_start(message)

    async def _handle_cancel(self, message: IncomingMessage):
        """Команда /cancel"""
        context = self._get_or_create_context(message)
        if context.chat_db_id:
            async with async_session_factory() as session:
                service = ConsultationService(session)
                await service.mark_chat_abandoned(context.chat_db_id)
                await session.commit()

        key = self._context_key(message)
        self.active_conversations.pop(key, None)

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content="Операция отменена. Напишите /start чтобы начать заново.",
            )
        )

    async def _handle_help(self, message: IncomingMessage):
        """Команда /help"""
        help_text = (
            "<b>Справка по командам:</b>\n\n"
            "/start — Начать консультацию\n"
            "/restart — Начать заново\n"
            "/help — Показать справку\n"
            "/cancel — Отменить текущее действие\n\n"
            "Нажимайте на кнопки для навигации."
        )
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=help_text,
            )
        )

    async def _handle_user_input(self, message: IncomingMessage):
        """Обработка ответа пользователя"""
        context = self._get_or_create_context(message)

        direction = context.direction or "main"
        algorithm = self.algorithm_loader.load_algorithm(direction)
        current_step = algorithm.get_step(context.current_step)

        if not current_step:
            logger.error(f"Step {context.current_step} not found")
            await self._send_error(message)
            return

        if direction == "main" and context.current_step == "direction_selection":
            await self._handle_direction_selection(message, context, current_step)
            return

        if current_step.type == "question":
            next_step_id = self._find_next_step(current_step, message.content)
            if next_step_id:
                await self._save_step(context, current_step, message)
                await self._go_to_step(context, message, algorithm, next_step_id)
            else:
                await self._send_choose_button(message, current_step)

        elif current_step.type == "contact":
            parsed = self._parse_contacts(message.content)
            if parsed:
                await self._save_contact_step(context, message, parsed)
                await self._go_to_step(
                    context, message, algorithm, current_step.next_step
                )
            else:
                await self.messenger.send_message(
                    OutgoingMessage(
                        chat_id=message.chat_id,
                        content=(
                            "Неверный формат. Укажите: <b>Имя Фамилия, телефон, email</b>\n\n"
                            "Пример: Иван Иванов, +79991234567, ivan@mail.ru"
                        ),
                    )
                )

        else:
            await self._go_to_step(context, message, algorithm, current_step.next_step)

    async def _handle_direction_selection(
        self,
        message: IncomingMessage,
        context: ConversationContext,
        current_step: Step,
    ):
        """Обработка выбора направления консультации"""
        if current_step.type == "question":
            for btn in current_step.buttons:
                if btn.get("value") == message.content:
                    next_step = btn.get("next_step")
                    if next_step == "load_direction":
                        context.direction = message.content
                        context.update_data("direction", message.content)

                        async with async_session_factory() as session:
                            service = ConsultationService(session)
                            if context.chat_db_id:
                                await service.update_chat_direction(
                                    context.chat_db_id,
                                    message.content,
                                )
                            await session.commit()

                        algorithm = self.algorithm_loader.load_algorithm(
                            message.content
                        )
                        greeting = algorithm.get_step("greeting")
                        response = self._build_step_response(context, greeting)
                        await self.messenger.send_message(response)
                        context.set_step(greeting.next_step or "problem_status")
                        return
                    break

        await self._send_choose_button(message, current_step)

    @staticmethod
    def _find_next_step(step: Step, content: str) -> str | None:
        """Найти следующий шаг по значению кнопки"""
        for btn in step.buttons:
            if btn.get("value") == content:
                return btn.get("next_step")
        return None

    def _parse_contacts(self, text: str) -> dict[str, str] | None:
        """Парсинг контактных данных.

        Поддерживаемые форматы:
          Имя Фамилия, +79991234567, email@mail.ru
          Имя Фамилия +79991234567
        """
        text = text.strip()
        parts = [p.strip() for p in re.split(r"[,;\n]", text) if p.strip()]
        if len(parts) < 2:
            parts = re.split(r"\s{2,}", text) or text.split()

        if len(parts) < 2:
            return None

        result: dict[str, str] = {"full_name": "", "phone": "", "email": ""}
        email_re = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
        phone_clean = re.compile(r"\D")
        name_parts: list[str] = []

        for p in parts:
            if email_re.search(p):
                result["email"] = p
            elif (
                re.match(r"^\+?[\d\s\-\(\)]{10,}$", p)
                or len(phone_clean.sub("", p)) >= 10
            ):
                digits = phone_clean.sub("", p)
                if len(digits) >= 10 and not result["phone"]:
                    result["phone"] = (
                        "+7" + digits[-10:] if len(digits) == 10 else "+" + digits
                    )
            else:
                name_parts.append(p)

        result["full_name"] = " ".join(name_parts) if name_parts else (parts[0] or "")

        if not result["phone"] and len(parts) >= 2:
            fallback = parts[-1] if result["email"] else parts[1]
            digits = phone_clean.sub("", fallback)
            if len(digits) >= 10:
                result["phone"] = (
                    "+7" + digits[-10:] if len(digits) == 10 else "+" + digits
                )

        if not result["full_name"] or not result["phone"]:
            return None
        return result

    async def _save_contact_step(
        self,
        context: ConversationContext,
        message: IncomingMessage,
        parsed: dict,
    ):
        """Сохранение контактных данных"""
        context.update_data("full_name", parsed["full_name"])
        context.update_data("phone", parsed["phone"])
        context.update_data("email", parsed.get("email", ""))

        if context.chat_db_id and context.user_db_id:
            async with async_session_factory() as session:
                service = ConsultationService(session)
                await service.update_user_contacts(
                    context.user_db_id,
                    full_name=parsed["full_name"],
                    phone=parsed["phone"],
                    email=parsed.get("email", ""),
                )
                await service.save_conversation_step(
                    context.chat_db_id,
                    "contact_collection",
                    {"answer": parsed},
                )
                await session.commit()

    async def _save_step(
        self,
        context: ConversationContext,
        step: Step,
        message: IncomingMessage,
    ):
        """Сохранение шага в БД"""
        if context.chat_db_id and step.id:
            async with async_session_factory() as session:
                service = ConsultationService(session)
                await service.save_conversation_step(
                    context.chat_db_id,
                    step.id,
                    {"answer": message.content, "type": message.message_type},
                )
                await session.commit()

    async def _go_to_step(
        self,
        context: ConversationContext,
        message: IncomingMessage,
        algorithm,
        step_id: str,
    ):
        """Переход к шагу"""
        if step_id == "completed":
            await self._complete_consultation(context, message)
            return

        step = algorithm.get_step(step_id)
        if not step:
            await self._send_error(message)
            return

        context.set_step(step_id)
        response = self._build_step_response(context, step)
        await self.messenger.send_message(response)

        if step.type == "end":
            await self._complete_consultation(context, message)

    async def _complete_consultation(
        self,
        context: ConversationContext,
        message: IncomingMessage,
    ):
        """Завершение консультации"""
        if context.chat_db_id and context.user_db_id:
            async with async_session_factory() as session:
                service = ConsultationService(session)
                await service.create_consultation(
                    chat_id=context.chat_db_id,
                    user_id=context.user_db_id,
                    direction=context.direction or "unknown",
                    status="pending",
                )
                await service.mark_chat_completed(context.chat_db_id)
                await session.commit()

        key = self._context_key(message)
        self.active_conversations.pop(key, None)

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=(
                    "<b>Спасибо за обращение!</b>\n\n"
                    "Ваша заявка зарегистрирована. "
                    "Менеджер свяжется с вами в ближайшее время.\n\n"
                    "/start — Новая консультация\n"
                    "/help — Справка"
                ),
            )
        )

    def _build_step_response(
        self, context: ConversationContext, step: Step
    ) -> OutgoingMessage:
        """Построить ответ для шага"""
        content = self._replace_placeholders(step.content, context.data)
        reply_markup = None
        if step.buttons:
            reply_markup = self.messenger.build_inline_keyboard(step.buttons)

        return OutgoingMessage(
            chat_id=context.chat_id,
            content=content,
            buttons=step.buttons,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    @staticmethod
    def _replace_placeholders(text: str, data: dict) -> str:
        """Замена плейсхолдеров {key} в тексте"""

        def repl(m):
            return str(data.get(m.group(1), m.group(0)))

        return re.sub(r"\{(\w+)\}", repl, text)

    async def _send_choose_button(self, message: IncomingMessage, step: Step):
        """Отправить сообщение с просьбой выбрать кнопку"""
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=f"Пожалуйста, выберите один из вариантов ниже:\n\n{step.content}",
                reply_markup=self.messenger.build_inline_keyboard(step.buttons),
                parse_mode="HTML",
            )
        )

    async def _send_error(self, message: IncomingMessage):
        """Отправить сообщение об ошибке"""
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content="Произошла ошибка. Напишите /start чтобы начать заново.",
            )
        )
