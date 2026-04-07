"""Реализация Telegram мессенджера"""

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.filters import Command
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.webhook.aiohttp_server import (
    SimpleRequestHandler,
    setup_application,
)
from aiohttp import web
from loguru import logger

from src.config.settings import settings
from src.core.conversation_manager import ConversationManager
from src.messengers.base import (
    AbstractMessenger,
    IncomingMessage,
    MediaItem,
    OutgoingMessage,
)
from src.services.health_service import run_ready_checks

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

SHARE_CONTACT_TEXT = "\U0001f4f1 Поделиться контактом"

_TELEGRAM_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


class TelegramMessenger(AbstractMessenger):
    """Telegram мессенджер через aiogram 3.x"""

    messenger_type = "telegram"

    def __init__(self):
        self.bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
        )
        self.bot.session.timeout = 60
        self.dp = Dispatcher()
        self.conversation_manager = ConversationManager(self)
        self._webhook_runner: web.AppRunner | None = None
        self._webhook_site: web.TCPSite | None = None
        self._setup_handlers()

    # -------------------------------------------------------
    # Handlers
    # -------------------------------------------------------

    def _setup_handlers(self):
        """Регистрация обработчиков"""

        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            await self._handle_message(message, "/start")

        @self.dp.message(Command("restart"))
        async def cmd_restart(message: Message):
            await self._handle_message(message, "/restart")

        @self.dp.message(Command("cancel"))
        async def cmd_cancel(message: Message):
            await self._handle_message(message, "/cancel")

        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            await self._handle_message(message, "/help")

        @self.dp.message(Command("deletedata"))
        async def cmd_deletedata(message: Message):
            await self._handle_message(message, "/deletedata")

        @self.dp.message(Command("admin"))
        async def cmd_admin(message: Message):
            await self._handle_message(message, "/admin")

        @self.dp.message(Command("stats"))
        async def cmd_stats(message: Message):
            await self._handle_message(message, "/stats")

        @self.dp.message(Command("users"))
        async def cmd_users(message: Message):
            await self._handle_message(message, "/users")

        @self.dp.message(Command("export"))
        async def cmd_export(message: Message):
            await self._handle_message(message, "/export")

        @self.dp.callback_query()
        async def handle_callback(cb: CallbackQuery):
            try:
                await cb.answer()
            except (
                TelegramBadRequest,
                TelegramNetworkError,
                TimeoutError,
            ) as exc:
                logger.debug(f"cb.answer() skipped: {exc}")

            user = cb.from_user
            cb_msg = cb.message
            if not user or not cb_msg:
                return
            if not hasattr(cb_msg, "chat"):
                return
            msg = IncomingMessage(
                user_id=str(user.id),
                chat_id=str(cb_msg.chat.id),
                content=cb.data or "",
                message_type="button",
                message_id=str(cb_msg.message_id),
                created_at=datetime.now(tz=timezone.utc),
                extra_data={"callback_id": cb.id},
            )
            await self.conversation_manager.process_message(msg)

        @self.dp.message(F.contact)
        async def handle_contact(message: Message):
            user = message.from_user
            if not user or not message.contact:
                return
            contact = message.contact
            first = contact.first_name or ""
            last = contact.last_name or ""
            full_name = f"{first} {last}".strip()
            msg = IncomingMessage(
                user_id=str(user.id),
                chat_id=str(message.chat.id),
                content=full_name,
                message_type="contact",
                message_id=str(message.message_id),
                created_at=(message.date or datetime.now(tz=timezone.utc)),
                extra_data={
                    "phone_number": contact.phone_number,
                    "first_name": first,
                    "last_name": last,
                },
            )
            await self.conversation_manager.process_message(msg)

        @self.dp.message(F.text)
        async def handle_text(message: Message):
            await self._handle_message(message, message.text or "")

    async def _handle_message(self, message: Message, content: str):
        """Обработка входящего текстового сообщения"""
        user = message.from_user
        if not user:
            return
        msg = IncomingMessage(
            user_id=str(user.id),
            chat_id=str(message.chat.id),
            content=content,
            message_type="text",
            message_id=str(message.message_id),
            created_at=(message.date or datetime.now(tz=timezone.utc)),
            extra_data={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
        )
        await self.conversation_manager.process_message(msg)

    # -------------------------------------------------------
    # Keyboard builder
    # -------------------------------------------------------

    def build_inline_keyboard(
        self, buttons: list
    ) -> InlineKeyboardMarkup | None:
        """Построение inline-клавиатуры"""
        if not buttons:
            return None

        max_len = max(
            (len(btn.get("text", "")) for btn in buttons),
            default=0,
        )
        cols = 1 if max_len > 30 or len(buttons) > 4 else 2

        keyboard: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for btn in buttons:
            row.append(
                InlineKeyboardButton(
                    text=btn.get("text", "")[:64],
                    callback_data=btn.get("value", "")[:64],
                )
            )
            if len(row) >= cols:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    # -------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------

    async def start(self):
        """Запуск: webhook (продакшен) или long polling (разработка)."""
        logger.info("Starting Telegram bot...")
        await self._set_bot_commands()
        bot_info = await self.bot.get_me()
        logger.info(f"Telegram bot: @{bot_info.username}")
        if settings.TELEGRAM_USE_WEBHOOK:
            await self._start_webhook()
        else:
            logger.info("Telegram mode: long polling")
            await self.dp.start_polling(self.bot)

    async def _start_webhook(self) -> None:
        """HTTPS webhook: aiohttp+setWebhook(рекомендуется для продакшена)."""

        public_url = settings.build_telegram_webhook_url()
        if not public_url:
            msg = (
                "TELEGRAM_USE_WEBHOOK=True требует непустой WEBHOOK_URL "
                "(публичный https://… URL, см. README)."
            )
            logger.error(msg)
            raise RuntimeError(msg)

        path = settings.TELEGRAM_WEBHOOK_PATH.strip()
        if not path.startswith("/"):
            path = "/" + path

        secret_raw = settings.TELEGRAM_WEBHOOK_SECRET.strip()
        secret: str | None = secret_raw or None
        if secret and not _TELEGRAM_SECRET_RE.match(secret):
            msg = (
                "TELEGRAM_WEBHOOK_SECRET: допустимы только A–Z, a–z, 0–9, "
                "_ и -, длина 1–256 (требование Telegram API)."
            )
            logger.error(msg)
            raise ValueError(msg)

        app = web.Application()

        async def _health_live(_request: web.Request) -> web.Response:
            return web.json_response(
                {"status": "ok", "service": "telegram_webhook"},
            )

        async def _health_ready(_request: web.Request) -> web.Response:
            data = await run_ready_checks()
            code = 200 if data["ready"] else 503
            payload = {**data, "service": "telegram_webhook"}
            return web.json_response(payload, status=code)

        app.router.add_get("/health/live", _health_live)
        app.router.add_get("/health/ready", _health_ready)

        handler = SimpleRequestHandler(
            dispatcher=self.dp,
            bot=self.bot,
            handle_in_background=True,
            secret_token=secret,
        )
        handler.register(app, path=path)
        setup_application(app, self.dp, bot=self.bot)

        self._webhook_runner = web.AppRunner(app)
        await self._webhook_runner.setup()
        self._webhook_site = web.TCPSite(
            self._webhook_runner,
            settings.WEBHOOK_LISTEN_HOST,
            settings.WEBHOOK_PORT,
        )
        await self._webhook_site.start()

        try:
            await self.bot.set_webhook(
                url=public_url,
                secret_token=secret,
                drop_pending_updates=settings.TELEGRAM_WEBHOOK_DROP_PENDING,
            )
        except Exception:
            await self._webhook_runner.cleanup()
            self._webhook_runner = None
            self._webhook_site = None
            raise

        logger.info(
            f"Telegram webhook: public URL={public_url!r}, "
            f"listen http://{settings.WEBHOOK_LISTEN_HOST}:"
            f"{settings.WEBHOOK_PORT}{path}; "
            f"health http://{settings.WEBHOOK_LISTEN_HOST}:"
            f"{settings.WEBHOOK_PORT}/health/live",
        )

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise

    async def _set_bot_commands(self) -> None:
        """Установить меню команд бота."""
        commands = [
            BotCommand(
                command="start",
                description="Начать консультацию",
            ),
            BotCommand(
                command="restart",
                description="Начать заново",
            ),
            BotCommand(
                command="help",
                description="Справка по командам",
            ),
            BotCommand(
                command="cancel",
                description="Отменить последний ответ (шаг назад)",
            ),
            BotCommand(
                command="deletedata",
                description="Удалить мои данные",
            ),
        ]
        await self.bot.set_my_commands(
            commands=commands,
            scope=BotCommandScopeAllPrivateChats(),
        )

    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping Telegram bot...")
        if self._webhook_runner is not None:
            try:
                telegram_webhook_d_p = settings.TELEGRAM_WEBHOOK_DROP_PENDING
                await self.bot.delete_webhook(
                    drop_pending_updates=telegram_webhook_d_p,
                )
            except Exception as exc:
                logger.warning(f"delete_webhook: {exc}")
            await self._webhook_runner.cleanup()
            self._webhook_runner = None
            self._webhook_site = None
        else:
            await self.bot.session.close()

    # -------------------------------------------------------
    # Send message (main dispatcher)
    # -------------------------------------------------------

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Отправка сообщения в чат"""
        try:
            chat = int(message.chat_id)
            pm = message.parse_mode or "HTML"

            for item in message.media:
                await self._send_media_item(chat, item, pm)

            if message.photo:
                return await self._send_photo_message(message)

            reply_markup = self._resolve_markup(message)

            await self._send_with_retry(
                self.bot.send_message,
                chat_id=chat,
                text=message.content,
                parse_mode=pm,
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def _send_with_retry(self, method, **kwargs):
        """Вызов Telegram API с retry при сетевых ошибках."""
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await method(**kwargs)
            except TelegramRetryAfter as e:
                logger.warning(f"Rate limited, retry after {e.retry_after}s")
                await asyncio.sleep(e.retry_after)
            except (TelegramNetworkError, TimeoutError) as e:
                last_exc = e
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"Network error (attempt {attempt}/{MAX_RETRIES}), "
                    f"retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
        raise last_exc or RuntimeError("Send failed after retries")

    def _resolve_markup(self, message: OutgoingMessage):
        """Определить reply_markup для сообщения."""
        if message.contact_request:
            btn = KeyboardButton(
                text=SHARE_CONTACT_TEXT,
                request_contact=True,
            )
            return ReplyKeyboardMarkup(
                keyboard=[[btn]],
                resize_keyboard=True,
                one_time_keyboard=True,
            )
        if message.remove_keyboard:
            return ReplyKeyboardRemove()
        if message.reply_markup:
            return message.reply_markup
        if message.buttons:
            return self.build_inline_keyboard(message.buttons)
        return None

    # -------------------------------------------------------
    # Media sending helpers
    # -------------------------------------------------------

    def _resolve_media_path(self, relative: str) -> Path | None:
        """Разрешить путь к медиа-файлу."""
        base = Path(settings.BASE_DIR)
        path = base / relative
        if path.exists():
            return path
        media_dir = base / "src" / "scenarios" / "media"
        alt = media_dir / Path(relative).name
        if alt.exists():
            return alt
        return None

    async def _send_media_item(
        self,
        chat_id: int,
        item: MediaItem,
        parse_mode: str = "HTML",
    ) -> bool:
        """Отправка одного медиа-элемента."""
        resolved = self._resolve_media_path(item.file)
        if not resolved:
            logger.warning(f"Media not found: {item.file}")
            if item.caption:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=item.caption,
                    parse_mode=parse_mode,
                )
            return False

        file = FSInputFile(resolved)
        caption = item.caption
        try:
            return await self._dispatch_media(
                chat_id,
                item.type,
                file,
                caption,
                parse_mode,
            )
        except Exception as e:
            logger.warning(f"Media {item.type} failed, fallback to text: {e}")
            if caption:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    parse_mode=parse_mode,
                )
            return False

    async def _dispatch_media(
        self,
        chat_id: int,
        media_type: str,
        file: FSInputFile,
        caption: str | None,
        parse_mode: str,
    ) -> bool:
        """Маршрутизация отправки по типу медиа."""
        kw: dict = {"chat_id": chat_id}
        short_caption = caption[:1024] if caption else None

        if media_type == "photo":
            kw["photo"] = file
            if short_caption:
                kw["caption"] = short_caption
                kw["parse_mode"] = parse_mode
            await self.bot.send_photo(**kw)

        elif media_type == "video_note":
            kw["video_note"] = file
            await self.bot.send_video_note(**kw)

        elif media_type == "video":
            kw["video"] = file
            if short_caption:
                kw["caption"] = short_caption
                kw["parse_mode"] = parse_mode
            await self.bot.send_video(**kw)

        elif media_type == "animation":
            kw["animation"] = file
            if short_caption:
                kw["caption"] = short_caption
                kw["parse_mode"] = parse_mode
            await self.bot.send_animation(**kw)

        elif media_type == "sticker":
            kw["sticker"] = file
            await self.bot.send_sticker(**kw)

        else:
            logger.warning(f"Unknown media type: {media_type}")
            return False

        return True

    async def _send_photo_message(self, message: OutgoingMessage) -> bool:
        """Отправка фото с подписью (legacy).

        При любой ошибке автоматически шлёт текст.
        """
        if not message.photo:
            return await self._send_text_fallback(message)

        resolved = self._resolve_media_path(message.photo)
        if not resolved:
            logger.warning(f"Photo not found: {message.photo}")
            return await self._send_text_fallback(message)

        chat = int(message.chat_id)
        photo = FSInputFile(resolved)
        caption = message.content
        pm = message.parse_mode or "HTML"

        try:
            if len(caption) <= 1024:
                await self._send_with_retry(
                    self.bot.send_photo,
                    chat_id=chat,
                    photo=photo,
                    caption=caption,
                    parse_mode=pm,
                )
            else:
                await self._send_with_retry(
                    self.bot.send_photo,
                    chat_id=chat,
                    photo=photo,
                )
                await self._send_with_retry(
                    self.bot.send_message,
                    chat_id=chat,
                    text=caption,
                    parse_mode=pm,
                )
            return True
        except Exception as e:
            logger.warning(f"Photo send failed, fallback to text: {e}")
            return await self._send_text_fallback(message)

    async def _send_text_fallback(self, message: OutgoingMessage) -> bool:
        """Отправить как текст (фолбэк при отсутствии фото)."""
        return await self.send_message(
            OutgoingMessage(
                chat_id=message.chat_id,
                content=message.content,
                parse_mode=message.parse_mode,
            )
        )

    async def send_typing(self, chat_id: str):
        """Индикатор набора текста"""
        try:
            await self.bot.send_chat_action(
                chat_id=int(chat_id),
                action="typing",
            )
        except Exception as e:
            logger.debug(f"Typing indicator error: {e}")

    async def handle_incoming_message(self, message: IncomingMessage):
        """Обработка входящего"""
        await self.conversation_manager.process_message(message)
