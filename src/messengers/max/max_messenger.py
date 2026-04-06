"""Реализация мессенджера MAX"""
from datetime import datetime
from typing import Optional, List, Dict

from maxapi import Bot, Dispatcher, F
from maxapi.types import (
    MessageCreated,
    MessageCallback,
    BotStarted,
)
from loguru import logger

from src.messengers.base import (
    AbstractMessenger,
    IncomingMessage,
    OutgoingMessage,
)
from src.config.settings import settings
from src.core.conversation_manager import ConversationManager


class MaxMessenger(AbstractMessenger):
    """MAX мессенджер"""

    messenger_type = "max"

    def __init__(self):
        self.bot = Bot(token=settings.MAX_BOT_TOKEN)
        self.dp = Dispatcher()
        self.conversation_manager = ConversationManager(self)
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
                extra_data={
                    "name": getattr(user, "username", None)
                        or getattr(user, "name", None)
                        or str(user.user_id),
                },
            )

        @self.dp.message_callback()
        async def on_callback(event: MessageCallback):
            payload = event.callback.payload or ""
            user = event.callback.user
            await self.bot.send_callback(
                callback_id=event.callback.callback_id,
            )
            await self._handle_event(
                user_id=str(user.user_id),
                chat_id=str(event.message.recipient.chat_id),
                content=payload,
                message_type="button",
                message_id=str(event.message.body.mid),
                extra_data={
                    "callback_id": event.callback.callback_id,
                    "name": getattr(user, "username", None)
                        or getattr(user, "name", None)
                        or str(user.user_id),
                },
            )

        @self.dp.message_created(F.message.body.text)
        async def on_message(event: MessageCreated):
            text = event.message.body.text or ""
            sender = event.message.sender
            await self._handle_event(
                user_id=str(sender.user_id),
                chat_id=str(event.chat_id),
                content=text,
                message_type="text",
                message_id=str(event.message.body.mid),
                extra_data={
                    "name": getattr(sender, "username", None)
                        or getattr(sender, "name", None)
                        or str(sender.user_id),
                },
            )

    async def _handle_event(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        message_type: str,
        message_id: str,
        extra_data: Optional[Dict] = None,
    ):
        """Общий обработчик событий"""
        msg = IncomingMessage(
            user_id=user_id,
            chat_id=chat_id,
            content=content,
            message_type=message_type,
            message_id=message_id,
            created_at=datetime.now(),
            extra_data=extra_data,
        )
        await self.conversation_manager.process_message(msg)

    def build_inline_keyboard(
        self, buttons: list
    ) -> Optional[List[List[Dict]]]:
        """Построение inline-клавиатуры для MAX.

        Возвращает структуру кнопок для
        InlineKeyboardAttachment.
        """
        if not buttons:
            return None

        keyboard: List[List[Dict]] = []
        row: List[Dict] = []
        for btn in buttons:
            row.append({
                "type": "callback",
                "text": btn.get("text", "")[:64],
                "payload": btn.get("value", "")[:255],
            })
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        return keyboard

    async def start(self):
        """Запуск бота"""
        logger.info("Starting MAX bot...")
        me = await self.bot.get_me()
        bot_name = getattr(me, "username", None) or getattr(me, "name", None) or str(me.user_id)
        logger.info(f"MAX bot started: {bot_name}")
        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping MAX bot...")

    async def send_message(
        self, message: OutgoingMessage
    ) -> bool:
        """Отправка сообщения"""
        try:
            attachments = None
            keyboard = message.reply_markup
            if keyboard:
                attachments = [{
                    "type": "inline_keyboard",
                    "payload": {"buttons": keyboard},
                }]

            from maxapi.types import ParseMode
            fmt = None
            if message.parse_mode:
                mode = message.parse_mode.lower()
                if mode == "html":
                    fmt = ParseMode.HTML
                elif mode == "markdown":
                    fmt = ParseMode.MARKDOWN

            await self.bot.send_message(
                chat_id=int(message.chat_id),
                text=message.content,
                attachments=attachments,
                parse_mode=fmt,
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

    async def handle_incoming_message(
        self, message: IncomingMessage
    ):
        """Обработка входящего (для совместимости)"""
        await self.conversation_manager.process_message(message)
