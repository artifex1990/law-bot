"""Реализация Telegram мессенджера"""

from datetime import UTC, datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from src.config.settings import settings
from src.core.conversation_manager import ConversationManager
from src.messengers.base import AbstractMessenger, IncomingMessage, OutgoingMessage


class TelegramMessenger(AbstractMessenger):
    """Telegram мессенджер через aiogram 3.x"""

    messenger_type = "telegram"

    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
        self.dp = Dispatcher()
        self.conversation_manager = ConversationManager(self)
        self._setup_handlers()

    def _setup_handlers(self):
        """Регистрация обработчиков"""

        @self.dp.message(Command("start"))
        async def cmd_start(message: Message):
            await self._handle_message(message, message.text or "/start")

        @self.dp.message(Command("restart"))
        async def cmd_restart(message: Message):
            await self._handle_message(message, "/restart")

        @self.dp.message(Command("cancel"))
        async def cmd_cancel(message: Message):
            await self._handle_message(message, "/cancel")

        @self.dp.message(Command("help"))
        async def cmd_help(message: Message):
            await self._handle_message(message, "/help")

        @self.dp.callback_query()
        async def handle_callback(callback: CallbackQuery):
            await callback.answer()
            user = callback.from_user
            if not user or not callback.message:
                return
            msg = IncomingMessage(
                user_id=str(user.id),
                chat_id=str(callback.message.chat.id),
                content=callback.data or "",
                message_type="button",
                message_id=str(callback.message.message_id),
                created_at=datetime.now(tz=UTC),
                extra_data={"callback_id": callback.id},
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

        created_at = message.date or datetime.now(tz=UTC)

        msg = IncomingMessage(
            user_id=str(user.id),
            chat_id=str(message.chat.id),
            content=content,
            message_type="text",
            message_id=str(message.message_id),
            created_at=created_at,
            extra_data={
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
            },
        )
        await self.conversation_manager.process_message(msg)

    def build_inline_keyboard(self, buttons: list) -> InlineKeyboardMarkup | None:
        """Построение inline-клавиатуры (кнопки по 2 в ряд)"""
        if not buttons:
            return None

        keyboard: list[list[InlineKeyboardButton]] = []
        row: list[InlineKeyboardButton] = []
        for btn in buttons:
            row.append(
                InlineKeyboardButton(
                    text=btn.get("text", "")[:64],
                    callback_data=btn.get("value", "")[:64],
                )
            )
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    async def start(self):
        """Запуск бота (long polling)"""
        logger.info("Starting Telegram bot...")
        bot_info = await self.bot.get_me()
        logger.info(f"Telegram bot started: @{bot_info.username}")
        await self.dp.start_polling(self.bot)

    async def stop(self):
        """Остановка бота"""
        logger.info("Stopping Telegram bot...")
        await self.bot.session.close()

    async def send_message(self, message: OutgoingMessage) -> bool:
        """Отправка сообщения в чат"""
        try:
            await self.bot.send_message(
                chat_id=int(message.chat_id),
                text=message.content,
                parse_mode=message.parse_mode or "HTML",
                reply_markup=message.reply_markup,
            )
            return True
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return False

    async def send_typing(self, chat_id: str):
        """Индикатор набора текста"""
        try:
            await self.bot.send_chat_action(chat_id=int(chat_id), action="typing")
        except Exception as e:
            logger.debug(f"Typing indicator error: {e}")

    async def handle_incoming_message(self, message: IncomingMessage):
        """Обработка входящего (для совместимости с абстрактным классом)"""
        await self.conversation_manager.process_message(message)
