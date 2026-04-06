"""Tests: ConversationManager logic (messenger + DB mocked)."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from src.core.algorithm_engine import Step
from src.core.conversation_manager import (
    MSG_DELETE_CANCEL,
    MSG_DELETE_CONFIRM,
    MSG_DELETE_DONE,
    ConversationContext,
    ConversationManager,
)
from src.messengers.base import (
    IncomingMessage,
    MediaItem,
)


def _make_message(
    content: str = "/start",
    user_id: str = "1",
    chat_id: str = "1",
    message_type: str = "text",
    extra_data: dict | None = None,
):
    return IncomingMessage(
        user_id=user_id,
        chat_id=chat_id,
        content=content,
        message_type=message_type,
        message_id="m1",
        created_at=datetime.now(tz=timezone.utc),
        extra_data=extra_data,
    )


# ---- ConversationContext ----


def test_context_set_step():
    ctx = ConversationContext("c1", "u1", "telegram")
    ctx.set_step("greeting")
    assert ctx.current_step == "greeting"


def test_context_update_data():
    ctx = ConversationContext("c1", "u1", "telegram")
    ctx.update_data("direction", "family")
    assert ctx.get_data("direction") == "family"
    assert ctx.get_data("missing", "default") == "default"


def test_context_initial_state():
    ctx = ConversationContext("c1", "u1", "telegram")
    assert ctx.direction is None
    assert ctx.current_step is None
    assert ctx.data == {}
    assert ctx.created_at is not None
    assert ctx.skip_contacts is False
    assert ctx.awaiting_delete_confirm is False


# ---- parse_contacts ----


def test_parse_contacts_full():
    mgr = ConversationManager(AsyncMock())
    result = mgr._parse_contacts("Ivan Ivanov, +79991234567, ivan@mail.ru")
    assert result is not None
    assert result["full_name"] == "Ivan Ivanov"
    assert result["phone"] == "+79991234567"
    assert result["email"] == "ivan@mail.ru"


def test_parse_contacts_no_email():
    mgr = ConversationManager(AsyncMock())
    result = mgr._parse_contacts("Ivan Ivanov, +79991234567")
    assert result is not None
    assert result["full_name"] == "Ivan Ivanov"
    assert result["phone"].endswith("9991234567")


def test_parse_contacts_invalid():
    mgr = ConversationManager(AsyncMock())
    assert mgr._parse_contacts("hello") is None
    assert mgr._parse_contacts("") is None


# ---- replace_placeholders ----


def test_replace_placeholders():
    text = "Hello {name}, direction: {direction}"
    result = ConversationManager._replace_placeholders(
        text,
        {"name": "Ivan", "direction": "family"},
    )
    assert result == "Hello Ivan, direction: family"


def test_replace_placeholders_missing_key():
    text = "Hello {name}, {unknown}"
    result = ConversationManager._replace_placeholders(text, {"name": "Ivan"})
    assert "{unknown}" in result


# ---- _build_media_items ----


def test_build_media_items():
    step = Step(
        {
            "id": "s1",
            "type": "text",
            "media": [
                {
                    "type": "photo",
                    "file": "media/img.jpg",
                    "caption": "Photo",
                },
                {
                    "type": "video_note",
                    "file": "media/circle.mp4",
                },
            ],
        }
    )
    items = ConversationManager._build_media_items(step)
    assert len(items) == 2
    assert isinstance(items[0], MediaItem)
    assert items[0].type == "photo"
    assert items[0].caption == "Photo"
    assert items[1].type == "video_note"
    assert items[1].caption is None


def test_build_media_items_empty():
    step = Step({"id": "s1", "type": "text"})
    items = ConversationManager._build_media_items(step)
    assert items == []


# ---- process_message routing ----


def _mock_db():
    mock_session = AsyncMock()
    mock_user = AsyncMock()
    mock_user.id = 1
    mock_user.privacy_consent_at = None
    mock_chat = AsyncMock()
    mock_chat.id = 10
    mock_svc = AsyncMock()
    mock_svc.get_or_create_user.return_value = mock_user
    mock_svc.create_chat.return_value = mock_chat
    mock_svc.user_has_contacts.return_value = False

    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session, mock_svc


@pytest.mark.asyncio
async def test_process_message_help(mock_messenger):
    mgr = ConversationManager(mock_messenger)
    msg = _make_message("/help")
    await mgr.process_message(msg)
    mock_messenger.send_message.assert_called_once()
    sent = mock_messenger.send_message.call_args[0][0]
    assert "/start" in sent.content
    assert "/deletedata" in sent.content


@pytest.mark.asyncio
async def test_process_message_cancel(mock_messenger):
    mgr = ConversationManager(mock_messenger)
    msg = _make_message("/cancel")
    await mgr.process_message(msg)
    mock_messenger.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_start(mock_messenger):
    """/start sends welcome photo + consent."""
    mgr = ConversationManager(mock_messenger)
    mock_session, mock_svc = _mock_db()

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg = _make_message("/start")
        await mgr.process_message(msg)

    assert mock_messenger.send_message.call_count == 2
    first = mock_messenger.send_message.call_args_list[0][0][0]
    second = mock_messenger.send_message.call_args_list[1][0][0]
    assert first.photo is not None
    text = second.content.lower()
    assert "согласие" in text or "согласен" in text

    ctx_key = "1_1"
    assert ctx_key in mgr.active_conversations
    ctx = mgr.active_conversations[ctx_key]
    assert ctx.current_step == "consent"


@pytest.mark.asyncio
async def test_start_sets_skip_contacts(
    mock_messenger,
):
    """Returning user with contacts → skip_contacts."""
    mgr = ConversationManager(mock_messenger)
    mock_session, mock_svc = _mock_db()
    mock_svc.user_has_contacts.return_value = True

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg = _make_message("/start")
        await mgr.process_message(msg)

    ctx = mgr.active_conversations["1_1"]
    assert ctx.skip_contacts is True


@pytest.mark.asyncio
async def test_start_skips_consent_when_privacy_already_recorded(
    mock_messenger,
):
    """Пользователь с сохранённым согласием: welcome, затем выбор направления."""
    mgr = ConversationManager(mock_messenger)
    mock_session, mock_svc = _mock_db()
    mock_svc.get_or_create_user.return_value.privacy_consent_at = datetime.now(
        tz=timezone.utc
    )

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg = _make_message("/start")
        await mgr.process_message(msg)

    assert mock_messenger.send_message.call_count == 2
    second = mock_messenger.send_message.call_args_list[1][0][0]
    text = second.content.lower()
    assert "согласие" not in text
    assert "фз-152" not in text
    assert "виктория" in text or "направлен" in text or "область" in text

    ctx = mgr.active_conversations["1_1"]
    assert ctx.current_step == "direction_selection"


@pytest.mark.asyncio
async def test_process_message_start_sends_media(
    mock_messenger,
):
    """Welcome step media list is passed through."""
    mgr = ConversationManager(mock_messenger)
    mock_session, mock_svc = _mock_db()

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg = _make_message("/start")
        await mgr.process_message(msg)

    first = mock_messenger.send_message.call_args_list[0][0][0]
    assert isinstance(first.media, list)


@pytest.mark.asyncio
async def test_process_message_unknown_resets(
    mock_messenger,
):
    """Text without context → reset to /start."""
    mgr = ConversationManager(mock_messenger)
    mock_session, mock_svc = _mock_db()

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg = _make_message("random text")
        await mgr.process_message(msg)

    assert mock_messenger.send_message.call_count >= 1


# ---- /deletedata ----


@pytest.mark.asyncio
async def test_deletedata_sends_confirm(
    mock_messenger,
):
    mgr = ConversationManager(mock_messenger)
    msg = _make_message("/deletedata")
    await mgr.process_message(msg)
    mock_messenger.send_message.assert_called_once()
    sent = mock_messenger.send_message.call_args[0][0]
    assert sent.content == MSG_DELETE_CONFIRM


@pytest.mark.asyncio
async def test_deletedata_confirm_yes(mock_messenger):
    """Confirmed deletion clears context."""
    mgr = ConversationManager(mock_messenger)
    msg1 = _make_message("/deletedata")
    await mgr.process_message(msg1)

    ctx = mgr.active_conversations["1_1"]
    ctx.user_db_id = 42

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_svc = AsyncMock()
    mock_svc.delete_user_data.return_value = True

    with (
        patch(
            "src.core.conversation_manager.async_session_factory",
            return_value=mock_session,
        ),
        patch(
            "src.core.conversation_manager.ConsultationService",
            return_value=mock_svc,
        ),
    ):
        msg2 = _make_message("Да, удалить")
        await mgr.process_message(msg2)

    assert "1_1" not in mgr.active_conversations
    last = mock_messenger.send_message.call_args_list[-1][0][0]
    assert last.content == MSG_DELETE_DONE


@pytest.mark.asyncio
async def test_deletedata_confirm_no(mock_messenger):
    """Cancelled deletion keeps context."""
    mgr = ConversationManager(mock_messenger)
    msg1 = _make_message("/deletedata")
    await mgr.process_message(msg1)

    msg2 = _make_message("Нет")
    await mgr.process_message(msg2)

    last = mock_messenger.send_message.call_args_list[-1][0][0]
    assert last.content == MSG_DELETE_CANCEL


# ---- _find_next_step ----


def test_find_next_step():
    step = Step(
        {
            "id": "q1",
            "type": "question",
            "buttons": [
                {
                    "text": "Yes",
                    "value": "yes",
                    "next_step": "s2",
                },
                {
                    "text": "No",
                    "value": "no",
                    "next_step": "s3",
                },
            ],
        }
    )
    found_yes = ConversationManager._find_next_step(step, "yes")
    found_no = ConversationManager._find_next_step(step, "no")
    found_maybe = ConversationManager._find_next_step(step, "maybe")
    assert found_yes == "s2"
    assert found_no == "s3"
    assert found_maybe is None
