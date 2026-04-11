"""Менеджер диалогов - управление состояниями и шагами"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from src.algorithms.loader import AlgorithmLoader
from src.config.settings import settings
from src.core.algorithm_engine import Step
from src.core.validators import (
    normalize_ru_phone,
    validate_email,
    validate_ru_phone,
)
from src.database.base import async_session_factory
from src.messengers.base import (
    IncomingMessage,
    MediaItem,
    OutgoingMessage,
)
from src.services.admin_service import AdminService
from src.services.consultation_service import (
    ConsultationService,
)
from src.services.outbound_sync import schedule_push_consultation

MSG_CANCEL_EMPTY = (
    "Сейчас нечего отменить - вы ещё не выбирали шаг в этом диалоге.\n\n"
    "Продолжайте ответ или нажмите <b>/restart</b>, чтобы начать сначала."
)
MSG_ERROR = "Произошла ошибка. Напишите /start чтобы начать заново."
MSG_CONTACT_FAIL = (
    "Не удалось распознать контакт.\n\n"
    "Нажмите кнопку "
    "«\U0001f4f1 Поделиться контактом» "
    "или отправьте:\n"
    "<b>Имя Фамилия, +7XXXXXXXXXX</b>"
)
MSG_CONTACT_OK = "\u2705 Контакт получен! Обрабатываем заявку..."
MSG_CHOOSE = "Пожалуйста, выберите один из вариантов ниже:\n\n"
MSG_PHONE_INVALID = (
    "\u274c Телефон не распознан как российский.\n"
    "Введите в формате: "
    "+7XXXXXXXXXX, 8XXXXXXXXXX "
    "или стационарный номер РФ."
)
MSG_EMAIL_INVALID = (
    "\u274c Email указан в неверном формате.\nПример: user@example.com"
)
MSG_DELETE_CONFIRM = (
    "\u26a0\ufe0f Вы уверены, что хотите удалить "
    "свои контактные данные и всю историю?\n"
    "Это действие <b>необратимо</b>.\n\n"
    "Подтвердите: <b>Да, удалить</b>"
)
MSG_DELETE_DONE = (
    "\u2705 Ваши данные полностью удалены. Спасибо, что были с нами!"
)
MSG_DELETE_CANCEL = "Удаление отменено. Ваши данные сохранены."
MSG_UNKNOWN_CMD = (
    "Команда не найдена.\n\n"
    "<b>Доступные команды:</b>\n"
    "/start - Начать консультацию\n"
    "/restart - Начать заново\n"
    "/help - Показать справку\n"
    "/cancel - Отменить последний ответ (шаг назад)\n"
    "/deletedata - Удалить мои данные"
)

HELP_TEXT = (
    "<b>Справка по командам:</b>\n\n"
    "/start - Начать консультацию\n"
    "/restart - Начать заново\n"
    "/help - Показать справку\n"
    "/cancel - Отменить последний ответ (шаг назад)\n"
    "/deletedata - Удалить мои данные\n\n"
    "Нажимайте на кнопки для навигации.\n"
    "<b>/cancel</b> возвращает к предыдущему вопросу (если он есть)."
)

PHONE_RE = re.compile(r"^\+?[\d\s\-\(\)]{10,}$")
EMAIL_RE = re.compile(r"[\w\.-]+@[\w\.-]+\.\w+")
NON_DIGIT_RE = re.compile(r"\D")


class ConversationContext:
    """Контекст активного диалога"""

    def __init__(
        self,
        chat_id: str,
        user_id: str,
        messenger_type: str,
    ):
        self.chat_id = chat_id
        self.user_id = user_id
        self.messenger_type = messenger_type
        self.current_step: str | None = None
        self.direction: str | None = None
        self.data: dict[str, Any] = {}
        self.chat_db_id: int | None = None
        self.user_db_id: int | None = None
        self.created_at = datetime.now(tz=timezone.utc)
        self.skip_contacts: bool = False
        self.awaiting_delete_confirm: bool = False
        # (step_id, direction) - шаг, на котором были до последнего ответа
        self.step_stack: list[tuple[str, str | None]] = []

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
        self._dialog_locks: dict[str, asyncio.Lock] = {}
        self._dialog_locks_guard = asyncio.Lock()

    def _context_key(self, message: IncomingMessage) -> str:
        return f"{message.user_id}_{message.chat_id}"

    def _get_or_create_context(
        self,
        message: IncomingMessage,
    ) -> ConversationContext:
        key = self._context_key(message)
        if key not in self.active_conversations:
            self.active_conversations[key] = ConversationContext(
                chat_id=message.chat_id,
                user_id=message.user_id,
                messenger_type=(self.messenger.messenger_type),
            )
        return self.active_conversations[key]

    async def _get_dialog_lock(self, key: str) -> asyncio.Lock:
        """Один lock на диалог (user+chat), чтобы апдейты не шли параллельно."""
        async with self._dialog_locks_guard:
            lock = self._dialog_locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._dialog_locks[key] = lock
            return lock

    # ---------------------------------------------------
    # Message routing
    # ---------------------------------------------------

    async def process_message(self, message: IncomingMessage):
        """Обработка входящего сообщения (строго по одному на диалог)."""
        key = self._context_key(message)
        lock = await self._get_dialog_lock(key)
        async with lock:
            await self._route_incoming_message(message)

    async def _route_incoming_message(self, message: IncomingMessage):
        preview = message.content[:50]
        logger.info(f"Message from {message.user_id}: {preview}...")

        cmd = message.content
        match cmd:
            case "/start":
                await self._handle_start(message)
            case "/restart":
                await self._handle_restart(message)
            case "/cancel":
                await self._handle_cancel(message)
            case "/help":
                await self._handle_help(message)
            case "/deletedata":
                await self._handle_delete_request(message)
            case "/admin" | "/stats" | "/users" | "/export":
                await self._handle_admin(message, cmd)
            case _ if cmd.startswith("/"):
                await self._handle_unknown_cmd(message)
            case _:
                await self._handle_user_input(message)

    # ---------------------------------------------------
    # /start - welcome; consent или сразу выбор направления
    # ---------------------------------------------------

    async def _handle_start(self, message: IncomingMessage):
        """Команда /start"""
        context = self._get_or_create_context(message)
        context.data.clear()
        context.step_stack.clear()
        context.direction = None
        context.current_step = None
        context.awaiting_delete_confirm = False

        async with async_session_factory() as session:
            svc = ConsultationService(session)
            user = await svc.get_or_create_user(
                message.user_id,
                self.messenger.messenger_type,
            )
            has_contacts = await svc.user_has_contacts(user.id)
            chat = await svc.create_chat(user.id)
            has_privacy_consent = user.privacy_consent_at is not None
            await session.commit()
            context.user_db_id = user.id
            context.chat_db_id = chat.id
            context.skip_contacts = has_contacts

        algo = self.algorithm_loader.load_main_algorithm()

        welcome = algo.get_step("welcome")
        if welcome:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=context.chat_id,
                    content=welcome.content,
                    photo=welcome.photo,
                    parse_mode="HTML",
                    media=self._build_media_items(welcome),
                )
            )

        if has_privacy_consent:
            direction_step = algo.get_step("direction_selection")
            if direction_step:
                resp = self._build_step_response(context, direction_step)
                await self.messenger.send_message(resp)
                context.set_step("direction_selection")
            return

        consent = algo.get_step("consent")
        if consent:
            resp = self._build_step_response(context, consent)
            await self.messenger.send_message(resp)
            context.set_step("consent")

    async def _handle_restart(self, message: IncomingMessage):
        """Команда /restart"""
        key = self._context_key(message)
        self.active_conversations.pop(key, None)
        await self._handle_start(message)

    async def _handle_cancel(self, message: IncomingMessage):
        """Команда /cancel - откат к предыдущему шагу (если был ответ)."""
        context = self._get_or_create_context(message)
        if not context.step_stack:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    content=MSG_CANCEL_EMPTY,
                ),
            )
            return

        step_id, saved_dir = context.step_stack.pop()
        context.direction = saved_dir
        self._trim_context_after_undo(context, step_id)

        if context.chat_db_id:
            async with async_session_factory() as session:
                svc = ConsultationService(session)
                if step_id == "consent" and context.user_db_id:
                    await svc.clear_privacy_consent(context.user_db_id)
                await svc.update_chat_direction(
                    context.chat_db_id,
                    saved_dir,
                )
                await session.commit()

        algo = self.algorithm_loader.load_algorithm(saved_dir or "main")
        await self._go_to_step(
            context,
            message,
            algo,
            step_id,
            chain_auto=True,
        )

    async def _handle_help(self, message: IncomingMessage):
        """Команда /help"""
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=HELP_TEXT,
                parse_mode="HTML",
            )
        )

    async def _handle_unknown_cmd(self, message: IncomingMessage):
        """Неизвестная команда - показать меню."""
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_UNKNOWN_CMD,
                parse_mode="HTML",
            )
        )

    # ---------------------------------------------------
    # /admin - админ-панель
    # ---------------------------------------------------

    def _is_admin(self, message: IncomingMessage) -> bool:
        if self.messenger.messenger_type == "max":
            return message.user_id in settings.MAX_ADMIN_IDS
        return message.user_id in settings.ADMIN_IDS

    async def _handle_admin(
        self,
        message: IncomingMessage,
        cmd: str,
    ):
        """Обработка админских команд."""
        if not self._is_admin(message):
            await self._handle_unknown_cmd(message)
            return

        match cmd:
            case "/admin":
                await self._admin_menu(message)
            case "/stats":
                await self._admin_stats(message)
            case "/users":
                await self._admin_users(message)
            case "/export":
                await self._admin_export(message)

    async def _admin_menu(self, message: IncomingMessage):
        text = (
            "<b>🔐 Админ-панель</b>\n\n"
            "/stats - Статистика бота\n"
            "/users - Последние клиенты\n"
            "/export - Выгрузка контактов (CSV)"
        )
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=text,
                parse_mode="HTML",
            )
        )

    async def _admin_stats(self, message: IncomingMessage):
        async with async_session_factory() as session:
            svc = AdminService(session)
            s = await svc.get_stats()

        lines = [
            "<b>📊 Статистика</b>\n",
            f"👥 Пользователей: <b>{s['total_users']}</b>",
            f"   └ за 24ч: {s['users_24h']}  |  за 7д: {s['users_7d']}",
            f"💬 Чатов: <b>{s['total_chats']}</b>  (за 24ч: {s['chats_24h']})",
            f"   └ активных: {s['active_chats']}  |  завершённых: {s['completed_chats']}",
            f"📋 Заявок: <b>{s['total_consultations']}</b>",
        ]

        if s["directions"]:
            lines.append("\n<b>📈 По направлениям:</b>")
            for direction, count in s["directions"]:
                lines.append(f"   {direction}: {count}")

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content="\n".join(lines),
                parse_mode="HTML",
            )
        )

    async def _admin_users(self, message: IncomingMessage):
        async with async_session_factory() as session:
            svc = AdminService(session)
            users = await svc.get_recent_users(limit=20)

        if not users:
            text = "Пользователей с контактами пока нет."
        else:
            lines = [f"<b>👥 Последние клиенты ({len(users)})</b>\n"]
            for u in users:
                lines.append(
                    f"• <b>{u['name']}</b>\n"
                    f"  📞 {u['phone']}"
                    + (f"  ✉ {u['email']}" if u["email"] != "-" else "")
                    + f"\n  📅 {u['created']}"
                )
            text = "\n".join(lines)

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=text,
                parse_mode="HTML",
            )
        )

    async def _admin_export(self, message: IncomingMessage):
        async with async_session_factory() as session:
            svc = AdminService(session)
            csv = await svc.export_users_csv()

        if csv.count("\n") == 0:
            text = "Нет данных для экспорта."
        else:
            text = f"<b>📤 Экспорт контактов</b>\n\n<pre>{csv}</pre>"

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=text,
                parse_mode="HTML",
            )
        )

    # ---------------------------------------------------
    # /deletedata - удаление данных
    # ---------------------------------------------------

    async def _handle_delete_request(self, message: IncomingMessage):
        """Запрос на удаление персональных данных."""
        context = self._get_or_create_context(message)
        context.awaiting_delete_confirm = True
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_DELETE_CONFIRM,
                parse_mode="HTML",
            )
        )

    async def _handle_delete_confirm(
        self,
        message: IncomingMessage,
        context: ConversationContext,
    ):
        """Подтверждение удаления данных."""
        context.awaiting_delete_confirm = False
        answer = message.content.strip().lower()
        confirmed = answer in (
            "да",
            "да, удалить",
            "удалить",
            "yes",
        )

        if not confirmed:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    content=MSG_DELETE_CANCEL,
                )
            )
            return

        async with async_session_factory() as session:
            svc = ConsultationService(session)
            user_id = context.user_db_id
            if user_id is None:
                user = await svc.get_user_by_messenger(
                    messenger_user_id=message.user_id,
                    messenger_type=self.messenger.messenger_type,
                )
                user_id = user.id if user else None
            if user_id:
                await svc.delete_user_data(user_id)
                await session.commit()

        key = self._context_key(message)
        self.active_conversations.pop(key, None)

        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_DELETE_DONE,
            )
        )

    # ---------------------------------------------------
    # User input dispatcher
    # ---------------------------------------------------

    async def _handle_user_input(self, message: IncomingMessage):
        """Обработка ответа пользователя"""
        context = self._get_or_create_context(message)

        if context.awaiting_delete_confirm:
            await self._handle_delete_confirm(message, context)
            return

        if not context.current_step:
            await self._handle_start(message)
            return

        self._touch_activity(context)

        direction = context.direction or "main"
        algo = self.algorithm_loader.load_algorithm(direction)
        step = algo.get_step(context.current_step)

        if not step:
            logger.error(f"Step {context.current_step} not found")
            await self._send_error(message)
            return

        is_dir_select = (
            direction == "main"
            and context.current_step == "direction_selection"
        )
        if is_dir_select:
            await self._handle_direction_selection(message, context, step)
            return

        if step.type == "question":
            next_id = self._find_next_step(step, message.content)
            if next_id:
                await self._save_step(context, step, message)
                if (
                    step.id == "consent"
                    and next_id == "direction_selection"
                    and context.user_db_id
                ):
                    async with async_session_factory() as session:
                        svc = ConsultationService(session)
                        await svc.set_privacy_consent(context.user_db_id)
                        await session.commit()
                self._push_step_undo(context, step.id, context.direction)
                await self._go_to_step(context, message, algo, next_id)
            else:
                await self._send_choose_button(message, step)

        elif step.type == "contact":
            await self._handle_contact_input(context, message, algo, step)

        elif step.type in ("text", "photo", "media"):
            if step.next_step:
                self._push_step_undo(context, step.id, context.direction)
                await self._go_to_step(
                    context,
                    message,
                    algo,
                    step.next_step,
                )

        else:
            if step.next_step:
                self._push_step_undo(context, step.id, context.direction)
                await self._go_to_step(
                    context,
                    message,
                    algo,
                    step.next_step,
                )

    # ---------------------------------------------------
    # Direction selection
    # ---------------------------------------------------

    async def _handle_direction_selection(
        self,
        message: IncomingMessage,
        context: ConversationContext,
        current_step: Step,
    ):
        """Обработка выбора направления."""
        if current_step.type != "question":
            await self._send_choose_button(message, current_step)
            return

        for btn in current_step.buttons:
            if btn.get("value") != message.content:
                continue

            next_step = btn.get("next_step")
            if next_step != "load_direction":
                break

            self._push_step_undo(
                context, "direction_selection", context.direction
            )
            context.direction = message.content
            context.update_data("direction", message.content)

            algo = self.algorithm_loader.load_algorithm(message.content)
            context.update_data("is_paid", algo.is_paid)

            async with async_session_factory() as session:
                svc = ConsultationService(session)
                if context.chat_db_id:
                    await svc.update_chat_direction(
                        context.chat_db_id,
                        message.content,
                    )
                await session.commit()

            await self._go_to_step(
                context,
                message,
                algo,
                "greeting",
            )
            return

        await self._send_choose_button(message, current_step)

    # ---------------------------------------------------
    # Contact handling
    # ---------------------------------------------------

    async def _handle_contact_input(
        self,
        context: ConversationContext,
        message: IncomingMessage,
        algorithm,
        current_step: Step,
    ):
        """Обработка контактных данных."""
        if context.skip_contacts:
            next_id = current_step.next_step or "confirmation"
            self._push_step_undo(context, current_step.id, context.direction)
            await self._go_to_step(context, message, algorithm, next_id)
            return

        parsed = None
        extra = message.extra_data

        is_tg_contact = message.message_type == "contact" and extra is not None
        if is_tg_contact and extra:
            first = extra.get("first_name", "")
            last = extra.get("last_name", "")
            phone = extra.get("phone_number", "")
            full_name = f"{first} {last}".strip()

            if full_name and phone:
                norm = normalize_ru_phone(phone)
                if norm:
                    parsed = {
                        "full_name": full_name,
                        "phone": norm,
                        "email": "",
                    }
                else:
                    parsed = {
                        "full_name": full_name,
                        "phone": phone,
                        "email": "",
                    }
        else:
            parsed = self._parse_contacts(message.content)

        if not parsed:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    content=MSG_CONTACT_FAIL,
                    contact_request=True,
                )
            )
            return

        phone_ok = validate_ru_phone(parsed["phone"])
        if not phone_ok:
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    content=MSG_PHONE_INVALID,
                    contact_request=True,
                )
            )
            return

        email = parsed.get("email", "")
        if email and not validate_email(email):
            await self.messenger.send_message(
                OutgoingMessage(
                    chat_id=message.chat_id,
                    content=MSG_EMAIL_INVALID,
                    contact_request=True,
                )
            )
            return

        norm_phone = normalize_ru_phone(parsed["phone"])
        if norm_phone:
            parsed["phone"] = norm_phone

        await self._save_contact_step(context, message, parsed)
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_CONTACT_OK,
                remove_keyboard=True,
            )
        )
        next_id = current_step.next_step or "confirmation"
        self._push_step_undo(context, current_step.id, context.direction)
        await self._go_to_step(context, message, algorithm, next_id)

    # ---------------------------------------------------
    # Step navigation
    # ---------------------------------------------------

    async def _go_to_step(
        self,
        context: ConversationContext,
        message: IncomingMessage,
        algorithm,
        step_id: str,
        *,
        chain_auto: bool = True,
    ):
        """Переход к шагу"""
        if step_id == "contact_collection" and context.skip_contacts:
            step = algorithm.get_step(step_id)
            next_id = "confirmation"
            if step and step.next_step:
                next_id = step.next_step
            await self._go_to_step(
                context,
                message,
                algorithm,
                next_id,
                chain_auto=chain_auto,
            )
            return

        step = algorithm.get_step(step_id)
        if not step:
            if step_id == "completed":
                await self._finalize_chat(context, message)
                return
            await self._send_error(message)
            return

        context.set_step(step_id)
        resp = self._build_step_response(context, step)
        await self.messenger.send_message(resp)

        if step.final_step or step.type == "end":
            await self._finalize_chat(context, message)
            return

        if (
            chain_auto
            and step.type in ("text", "photo", "media")
            and step.next_step
        ):
            await self._go_to_step(
                context,
                message,
                algorithm,
                step.next_step,
                chain_auto=chain_auto,
            )

    @staticmethod
    def _push_step_undo(
        context: ConversationContext,
        step_id: str | None,
        direction: str | None,
    ) -> None:
        if step_id:
            context.step_stack.append((step_id, direction))

    @staticmethod
    def _trim_context_after_undo(
        context: ConversationContext,
        step_id: str,
    ) -> None:
        if step_id in ("consent", "direction_selection"):
            context.data.pop("direction", None)
            context.data.pop("is_paid", None)

    async def _finalize_chat(
        self,
        context: ConversationContext,
        message: IncomingMessage,
    ):
        """Завершение чата."""
        new_consultation_id: int | None = None
        if context.chat_db_id and context.user_db_id:
            async with async_session_factory() as session:
                svc = ConsultationService(session)
                if context.direction:
                    is_paid = context.data.get("is_paid", False)
                    created = await svc.create_consultation(
                        chat_id=context.chat_db_id,
                        user_id=context.user_db_id,
                        direction=context.direction,
                        status="pending",
                        is_paid=is_paid,
                    )
                    new_consultation_id = created.id
                await svc.mark_chat_completed(context.chat_db_id)
                await session.commit()

        if new_consultation_id is not None:
            schedule_push_consultation(new_consultation_id)

        key = self._context_key(message)
        self.active_conversations.pop(key, None)

    # ---------------------------------------------------
    # Activity tracking
    # ---------------------------------------------------

    @staticmethod
    def _touch_activity(
        context: ConversationContext,
    ) -> None:
        """Обновить активность в БД (fire-and-forget)."""
        import asyncio

        async def _update():
            if not context.chat_db_id:
                return
            try:
                async with async_session_factory() as session:
                    svc = ConsultationService(session)
                    await svc.touch_chat_activity(context.chat_db_id)
                    await session.commit()
            except Exception as exc:
                logger.debug(f"Activity touch failed: {exc}")

        _task = asyncio.ensure_future(_update())
        _task.add_done_callback(lambda t: None)

    # ---------------------------------------------------
    # Helpers
    # ---------------------------------------------------

    @staticmethod
    def _find_next_step(step: Step, content: str) -> str | None:
        """Найти следующий шаг по значению кнопки."""
        for btn in step.buttons:
            if btn.get("value") == content:
                val = btn.get("next_step")
                if val is not None:
                    return str(val)
                return None
        return None

    def _parse_contacts(self, text: str) -> dict[str, str] | None:
        """Парсинг контактных данных из текста."""
        text = text.strip()
        parts = [p.strip() for p in re.split(r"[,;\n]", text) if p.strip()]
        if len(parts) < 2:
            parts = re.split(r"\s{2,}", text) or text.split()
        if len(parts) < 2:
            return None

        result: dict[str, str] = {
            "full_name": "",
            "phone": "",
            "email": "",
        }
        name_parts: list[str] = []

        for p in parts:
            if EMAIL_RE.search(p):
                result["email"] = p
            elif self._looks_like_phone(p):
                digits = NON_DIGIT_RE.sub("", p)
                if len(digits) >= 10 and not result["phone"]:
                    result["phone"] = self._normalize_phone(digits)
            else:
                name_parts.append(p)

        result["full_name"] = (
            " ".join(name_parts) if name_parts else (parts[0] or "")
        )

        if not result["phone"] and len(parts) >= 2:
            fallback = parts[-1] if result["email"] else parts[1]
            digits = NON_DIGIT_RE.sub("", fallback)
            if len(digits) >= 10:
                result["phone"] = self._normalize_phone(digits)

        if not result["full_name"]:
            return None
        if not result["phone"]:
            return None
        return result

    @staticmethod
    def _looks_like_phone(text: str) -> bool:
        digits = NON_DIGIT_RE.sub("", text)
        has_match = bool(PHONE_RE.match(text))
        return has_match or len(digits) >= 10

    @staticmethod
    def _normalize_phone(digits: str) -> str:
        if len(digits) == 10:
            return "+7" + digits[-10:]
        return "+" + digits

    async def _save_contact_step(
        self,
        context: ConversationContext,
        message: IncomingMessage,
        parsed: dict,
    ):
        """Сохранение контактных данных."""
        context.update_data("full_name", parsed["full_name"])
        context.update_data("phone", parsed["phone"])
        context.update_data("email", parsed.get("email", ""))

        if context.chat_db_id and context.user_db_id:
            async with async_session_factory() as session:
                svc = ConsultationService(session)
                await svc.update_user_contacts(
                    context.user_db_id,
                    full_name=parsed["full_name"],
                    phone=parsed["phone"],
                    email=parsed.get("email", ""),
                )
                await svc.save_conversation_step(
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
        """Сохранение шага в БД."""
        if context.chat_db_id and step.id:
            async with async_session_factory() as session:
                svc = ConsultationService(session)
                await svc.save_conversation_step(
                    context.chat_db_id,
                    step.id,
                    {
                        "answer": message.content,
                        "type": message.message_type,
                    },
                )
                await session.commit()

    @staticmethod
    def _build_media_items(
        step: Step,
    ) -> list[MediaItem]:
        """Конвертировать MediaAttachment → MediaItem."""
        return [
            MediaItem(
                type=m.type,
                file=m.file,
                caption=m.caption,
            )
            for m in step.media
        ]

    def _build_step_response(
        self,
        context: ConversationContext,
        step: Step,
    ) -> OutgoingMessage:
        """Построить ответ для шага."""
        content = self._replace_placeholders(step.content, context.data)
        reply_markup = None
        if step.buttons:
            reply_markup = self.messenger.build_inline_keyboard(step.buttons)

        is_photo = step.type == "photo"
        is_contact = step.type == "contact"

        return OutgoingMessage(
            chat_id=context.chat_id,
            content=content,
            buttons=step.buttons,
            reply_markup=reply_markup,
            parse_mode="HTML",
            photo=step.photo if is_photo else None,
            contact_request=is_contact,
            media=self._build_media_items(step),
        )

    @staticmethod
    def _replace_placeholders(text: str, data: dict) -> str:
        """Замена плейсхолдеров {key} в тексте."""

        def repl(m):
            return str(data.get(m.group(1), m.group(0)))

        return re.sub(r"\{(\w+)\}", repl, text)

    async def _send_choose_button(
        self,
        message: IncomingMessage,
        step: Step,
    ):
        """Отправить с просьбой выбрать кнопку."""
        markup = self.messenger.build_inline_keyboard(step.buttons)
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_CHOOSE + step.content,
                reply_markup=markup,
                parse_mode="HTML",
            )
        )

    async def _send_error(self, message: IncomingMessage):
        """Отправить сообщение об ошибке."""
        await self.messenger.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=MSG_ERROR,
            )
        )
