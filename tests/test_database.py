"""Tests: database models and ORM operations on test SQLite DB."""

import pytest

from src.database.models import (
    Chat,
    Consultation,
    ConversationStep,
    Message,
    User,
)


@pytest.mark.asyncio
async def test_create_user(db_session):
    user = User(messenger_type="telegram", messenger_user_id="12345")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.id is not None
    assert user.messenger_type == "telegram"
    assert user.messenger_user_id == "12345"
    assert user.is_active is True


@pytest.mark.asyncio
async def test_create_chat(db_session):
    user = User(messenger_type="telegram", messenger_user_id="u1")
    db_session.add(user)
    await db_session.flush()

    chat = Chat(user_id=user.id, status="active")
    db_session.add(chat)
    await db_session.flush()
    await db_session.refresh(chat)

    assert chat.id is not None
    assert chat.user_id == user.id
    assert chat.status == "active"


@pytest.mark.asyncio
async def test_create_message(db_session):
    user = User(messenger_type="telegram", messenger_user_id="u2")
    db_session.add(user)
    await db_session.flush()

    chat = Chat(user_id=user.id, status="active")
    db_session.add(chat)
    await db_session.flush()

    msg = Message(
        chat_id=chat.id,
        sender="user",
        content="Hello",
        message_type="text",
    )
    db_session.add(msg)
    await db_session.flush()
    await db_session.refresh(msg)

    assert msg.id is not None
    assert msg.content == "Hello"


@pytest.mark.asyncio
async def test_create_conversation_step(db_session):
    user = User(messenger_type="telegram", messenger_user_id="u3")
    db_session.add(user)
    await db_session.flush()

    chat = Chat(user_id=user.id, status="active")
    db_session.add(chat)
    await db_session.flush()

    step = ConversationStep(
        chat_id=chat.id,
        step_name="greeting",
        step_data={"answer": "start"},
    )
    db_session.add(step)
    await db_session.flush()
    await db_session.refresh(step)

    assert step.id is not None
    assert step.step_name == "greeting"


@pytest.mark.asyncio
async def test_create_consultation(db_session):
    user = User(messenger_type="telegram", messenger_user_id="u4")
    db_session.add(user)
    await db_session.flush()

    chat = Chat(user_id=user.id, status="active")
    db_session.add(chat)
    await db_session.flush()

    consultation = Consultation(
        chat_id=chat.id,
        user_id=user.id,
        direction="family",
        status="pending",
    )
    db_session.add(consultation)
    await db_session.flush()
    await db_session.refresh(consultation)

    assert consultation.id is not None
    assert consultation.direction == "family"
    assert consultation.is_paid is False


@pytest.mark.asyncio
async def test_user_contacts_update(db_session):
    user = User(messenger_type="telegram", messenger_user_id="u5")
    db_session.add(user)
    await db_session.flush()

    user.full_name = "Ivan Ivanov"
    user.phone = "+79991234567"
    user.email = "ivan@test.com"
    await db_session.flush()
    await db_session.refresh(user)

    assert user.full_name == "Ivan Ivanov"
    assert user.phone == "+79991234567"
    assert user.email == "ivan@test.com"
