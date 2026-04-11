"""Реализация мессенджера MAX (паритет с Telegram там, где поддерживает Bot API)."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from maxapi import Bot, Dispatcher, F

if TYPE_CHECKING:
    from maxapi.types import BotStarted, MessageCallback, MessageCreated

from src.config.settings import settings
from src.core.conversation_manager import ConversationManager
from src.messengers.base import (
    AbstractMessenger,
    IncomingMessage,
    MediaItem,
    OutgoingMessage,
)
from src.messengers.webhook_health import AiohttpMaxWebhookWithHealth

MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0

SHARE_CONTACT_TEXT = "\U0001f4f1 Поделиться контактом"

# Сообщения вида /cmd@BotName — как в Telegram
_CMD_AT_BOT_RE = re.compile(r"^(/[A-Za-z0-9_]+)@[A-Za-z0-9_]+(\s.*)?$")


def _user_name(user) -> str:
    """Извлечь имя пользователя MAX."""
    username = getattr(user, "username", None)
    name = getattr(user, "name", None)
    return username or name or str(user.user_id)


def _normalize_max_text(text: str) -> str:
    """Нормализовать текст: trim, /команда@бот -> /команда, регистр команд."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return text
    m = _CMD_AT_BOT_RE.match(text)
    if m:
        rest = m.group(2) or ""
        text = m.group(1) + rest
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    if len(parts) == 1:
        return cmd
    return f"{cmd} {parts[1]}"


def _sender_extra(sender) -> dict:
    """Поля для ConversationManager (аналог Telegram extra_data)."""
    extra: dict = {"name": _user_name(sender)}
    for key in ("username", "first_name", "last_name"):
        if hasattr(sender, key):
            val = getattr(sender, key, None)
            if val is not None:
                extra[key] = val
    return extra


class MaxMessenger(AbstractMessenger):
    """MAX мессенджер"""

    messenger_type = "max"

    def __init__(self):
        self.bot = Bot(token=settings.MAX_BOT_TOKEN)
        self.dp = Dispatcher()
        self.conversation_manager = ConversationManager(self)
        self._webhook_mode = False
        self._setup_handlers()

    def _setup_handlers(self):
        """Регистрация обработчиков"""

        @self.dp.bot_started()
        async def on_bot_started(event: BotStarted):
            user = event.user
            await self._handle_event(
                user_id=str(user.user_id),
                chat_id=str(event.chat_id),
                content="/start",
                message_type="text",
                message_id="",
                extra_data=_sender_extra(user),
            )

        @self.dp.message_callback()
        async def on_callback(event: MessageCallback):
            payload = event.callback.payload or ""
            user = event.callback.user
            cb_id = event.callback.callback_id
            try:
                await self.bot.send_callback(callback_id=cb_id)
            except Exception as exc:
                logger.debug(f"MAX send_callback: {exc}")

            chat_id = event.message.recipient.chat_id
            msg_id = event.message.body.mid
            await self._handle_event(
                user_id=str(user.user_id),
                chat_id=str(chat_id),
                content=payload,
                message_type="button",
                message_id=str(msg_id),
                extra_data={
                    "callback_id": cb_id,
                    **_sender_extra(user),
                },
            )

        @self.dp.message_created(F.message.body.text)
        async def on_message(event: MessageCreated):
            raw = event.message.body.text or ""
            text = _normalize_max_text(raw)
            sender = event.message.sender
            msg_id = event.message.body.mid
            await self._handle_event(
                user_id=str(sender.user_id),
                chat_id=str(event.chat_id),
                content=text,
                message_type="text",
                message_id=str(msg_id),
                extra_data=_sender_extra(sender),
            )

    async def _handle_event(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        message_type: str,
        message_id: str,
        extra_data: dict | None = None,
    ):
        """Общий обработчик событий"""
        msg = IncomingMessage(
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            message_type=message_type,
            message_id=message_id,
            created_at=datetime.now(tz=timezone.utc),
            extra_data=extra_data,
        )
        await self.conversation_manager.process_message(msg)

    def build_inline_keyboard(self, buttons: list) -> list[list[dict]] | None:
        """Построение inline-клавиатуры (та же логика колонок, что в Telegram)."""
        if not buttons:
            return None

        max_len = max(
            (len(btn.get("text", "")) for btn in buttons),
            default=0,
        )
        cols = 1 if max_len > 30 or len(buttons) > 4 else 2

        keyboard: list[list[dict]] = []
        row: list[dict] = []
        for btn in buttons:
            row.append(
                {
                    "type": "callback",
                    "text": btn.get("text", "")[:64],
                    "payload": btn.get("value", "")[:255],
                }
            )
            if len(row) >= cols:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        return keyboard

    @staticmethod
    def _resolve_media_path(relative: str) -> Path | None:
        base = Path(settings.BASE_DIR)
        path = base / relative
        if path.exists():
            return path
        media_dir = base / "src" / "scenarios" / "media"
        alt = media_dir / Path(relative).name
        if alt.exists():
            return alt
        return None

    def _resolve_parse_mode(self, parse_mode: str | None):
        if not parse_mode:
            return None
        mode = parse_mode.lower()
        try:
            from maxapi.enums.parse_mode import ParseMode
        except ImportError:
            from maxapi.types import ParseMode

        if mode == "html":
            return ParseMode.HTML
        if mode == "markdown":
            return ParseMode.MARKDOWN
        return None

    async def _send_with_retry(self, **kwargs):
        last_exc: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await self.bot.send_message(**kwargs)
            except Exception as e:
                last_exc = e
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    f"MAX send retry {attempt}/{MAX_RETRIES} in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _inline_keyboard_attachment(
        self,
        message: OutgoingMessage,
    ) -> list | None:
        """Собрать вложение inline_keyboard + опционально RequestContactButton."""
        keyboard = message.reply_markup
        if not keyboard and message.buttons:
            keyboard = self.build_inline_keyboard(message.buttons)

        markup_objs: list = []

        if message.contact_request:
            try:
                from maxapi.types import CallbackButton, RequestContactButton
                from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

                builder = InlineKeyboardBuilder()
                builder.row(RequestContactButton(text=SHARE_CONTACT_TEXT))
                if keyboard:
                    for row in keyboard:
                        btns = []
                        for b in row:
                            btns.append(
                                CallbackButton(
                                    text=b.get("text", "")[:64],
                                    payload=b.get("payload", "")[:255],
                                )
                            )
                        if btns:
                            builder.row(*btns)
                markup_objs.append(builder.as_markup())
                return markup_objs
            except Exception as exc:
                logger.debug(
                    f"MAX RequestContactButton unavailable, text only: {exc}"
                )

        if keyboard:
            markup_objs.append(
                {
                    "type": "inline_keyboard",
                    "payload": {"buttons": keyboard},
                }
            )
        return markup_objs or None

    async def _send_text_message(
        self,
        chat_id: int,
        message: OutgoingMessage,
        *,
        text: str,
        attachments: list | None,
    ) -> None:
        fmt = self._resolve_parse_mode(message.parse_mode)
        kw: dict = {"chat_id": chat_id, "text": text}
        if attachments is not None:
            kw["attachments"] = attachments
        if fmt is not None:
            kw["parse_mode"] = fmt
        await self._send_with_retry(**kw)

    async def _send_media_item(
        self,
        chat_id: int,
        item: MediaItem,
        parse_mode,
    ) -> bool:
        try:
            from maxapi.types.input_media import InputMedia
        except ImportError:
            logger.warning("MAX: InputMedia недоступен, медиа пропущено")
            if item.caption:
                await self._send_with_retry(
                    chat_id=chat_id,
                    text=item.caption,
                    parse_mode=parse_mode,
                )
            return False

        resolved = self._resolve_media_path(item.file)
        if not resolved:
            logger.warning(f"MAX: медиа не найдено: {item.file}")
            if item.caption:
                await self._send_with_retry(
                    chat_id=chat_id,
                    text=item.caption,
                    parse_mode=parse_mode,
                )
            return False

        photo = InputMedia(path=str(resolved))
        caption = (item.caption or "").strip() or "\u200b"
        try:
            await self._send_with_retry(
                chat_id=chat_id,
                text=caption[:4096],
                attachments=[photo],
                parse_mode=parse_mode,
            )
            return True
        except Exception as e:
            logger.warning(f"MAX: отправка медиа {item.type}: {e}")
            if item.caption:
                await self._send_with_retry(
                    chat_id=chat_id,
                    text=item.caption,
                    parse_mode=parse_mode,
                )
            return False

    async def _send_photo_legacy(self, message: OutgoingMessage) -> bool:
        try:
            from maxapi.types.input_media import InputMedia
        except ImportError:
            return False

        resolved = self._resolve_media_path(message.photo or "")
        if not resolved:
            return False

        chat_id = int(message.chat_id)
        photo = InputMedia(path=str(resolved))
        caption = message.content
        fmt = self._resolve_parse_mode(message.parse_mode)

        try:
            if len(caption) <= 1024:
                kw: dict = {
                    "chat_id": chat_id,
                    "text": caption,
                    "attachments": [photo],
                }
                if fmt is not None:
                    kw["parse_mode"] = fmt
                await self._send_with_retry(**kw)
            else:
                await self._send_with_retry(
                    chat_id=chat_id,
                    text=caption[:1024],
                    attachments=[photo],
                    parse_mode=fmt,
                )
                await self._send_with_retry(
                    chat_id=chat_id,
                    text=caption,
                    parse_mode=fmt,
                )
            return True
        except Exception as e:
            logger.warning(f"MAX: фото не отправлено: {e}")
            return False

    async def start(self):
        """Запуск: long polling или HTTPS webhook (maxapi)."""
        logger.info("Starting MAX bot...")
        me = await self.bot.get_me()
        logger.info(f"MAX bot started: {_user_name(me)}")

        if settings.MAX_USE_WEBHOOK:
            public_url = settings.build_max_webhook_url()
            if not public_url:
                msg = (
                    "MAX_USE_WEBHOOK=True требует непустой MAX_WEBHOOK_URL "
                    "(публичный https://… URL для subscribe_webhook)."
                )
                logger.error(msg)
                raise RuntimeError(msg)

            from maxapi.enums.update import UpdateType

            update_types = [
                UpdateType.MESSAGE_CREATED,
                UpdateType.MESSAGE_CALLBACK,
                UpdateType.BOT_STARTED,
            ]
            secret_raw = settings.MAX_WEBHOOK_SECRET.strip()
            secret: str | None = secret_raw or None

            await self.bot.subscribe_webhook(
                url=public_url,
                update_types=update_types,
                secret=secret,
            )
            self._webhook_mode = True
            path = settings.MAX_WEBHOOK_PATH.strip()
            if not path.startswith("/"):
                path = "/" + path
            logger.info(
                f"MAX webhook: public URL={public_url!r}, "
                f"listen http://{settings.MAX_WEBHOOK_LISTEN_HOST}:"
                f"{settings.MAX_WEBHOOK_PORT}{path}; "
                f"health http://{settings.MAX_WEBHOOK_LISTEN_HOST}:"
                f"{settings.MAX_WEBHOOK_PORT}/health/live",
            )
            await self.dp.handle_webhook(
                self.bot,
                host=settings.MAX_WEBHOOK_LISTEN_HOST,
                port=settings.MAX_WEBHOOK_PORT,
                path=path,
                secret=secret,
                webhook_type=AiohttpMaxWebhookWithHealth,
            )
            return

        self._webhook_mode = False
        logger.info("MAX mode: long polling")
        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping MAX bot...")
        if self._webhook_mode:
            try:
                await self.bot.delete_webhook()
            except Exception as exc:
                logger.warning(f"MAX delete_webhook: {exc}")
            self._webhook_mode = False
        has_session = hasattr(self.bot, "session") and self.bot.session
        if has_session:
            await self.bot.session.close()

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Отправка: медиа и фото — как в Telegram; клавиатура и контакт — через API MAX."""
        try:
            chat_id = int(message.chat_id)
            fmt = self._resolve_parse_mode(message.parse_mode)

            for item in message.media:
                await self._send_media_item(chat_id, item, fmt)

            if message.photo:
                ok = await self._send_photo_legacy(message)
                if ok:
                    return True
                logger.warning(
                    "MAX: фото из сценария недоступно, отправляем текст"
                )

            if message.remove_keyboard:
                await self._send_text_message(
                    chat_id,
                    message,
                    text=message.content,
                    attachments=None,
                )
                return True

            attachments = self._inline_keyboard_attachment(message)
            await self._send_text_message(
                chat_id,
                message,
                text=message.content,
                attachments=attachments,
            )
            return True
        except Exception as e:
            logger.error(f"Error sending MAX message: {e}")
            return False

    async def send_typing(self, chat_id: str):
        """Индикатор печати"""
        try:
            from maxapi.types import SenderAction

            await self.bot.send_action(
                chat_id=int(chat_id),
                action=SenderAction.TYPING_ON,
            )
        except Exception as e:
            logger.debug(f"MAX typing error: {e}")

    async def handle_incoming_message(self, message: IncomingMessage):
        """Обработка входящего (для совместимости)"""
        await self.conversation_manager.process_message(message)
