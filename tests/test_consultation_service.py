"""Tests: ConsultationService CRUD operations on test DB."""

import pytest

from src.services.consultation_service import ConsultationService


@pytest.mark.asyncio
async def test_get_or_create_user_new(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_100", "telegram")

    assert user.id is not None
    assert user.messenger_user_id == "tg_100"
    assert user.messenger_type == "telegram"


@pytest.mark.asyncio
async def test_get_or_create_user_existing(db_session):
    svc = ConsultationService(db_session)
    u1 = await svc.get_or_create_user("tg_200", "telegram")
    u2 = await svc.get_or_create_user("tg_200", "telegram")

    assert u1.id == u2.id


@pytest.mark.asyncio
async def test_create_chat(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_300", "telegram")
    chat = await svc.create_chat(user.id)

    assert chat.id is not None
    assert chat.user_id == user.id
    assert chat.status == "active"


@pytest.mark.asyncio
async def test_update_chat_direction(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_400", "telegram")
    chat = await svc.create_chat(user.id)
    await svc.update_chat_direction(chat.id, "labor")
    await db_session.refresh(chat)

    assert chat.direction == "labor"


@pytest.mark.asyncio
async def test_mark_chat_completed(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_500", "telegram")
    chat = await svc.create_chat(user.id)
    await svc.mark_chat_completed(chat.id)
    await db_session.refresh(chat)

    assert chat.status == "completed"
    assert chat.completed_at is not None


@pytest.mark.asyncio
async def test_mark_chat_abandoned(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_600", "telegram")
    chat = await svc.create_chat(user.id)
    await svc.mark_chat_abandoned(chat.id)
    await db_session.refresh(chat)

    assert chat.status == "abandoned"


@pytest.mark.asyncio
async def test_save_conversation_step(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_700", "telegram")
    chat = await svc.create_chat(user.id)
    await svc.save_conversation_step(chat.id, "greeting", {"answer": "hi"})

    # No exception = success; the step was flushed.


@pytest.mark.asyncio
async def test_create_consultation(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_800", "telegram")
    chat = await svc.create_chat(user.id)
    consultation = await svc.create_consultation(
        chat_id=chat.id,
        user_id=user.id,
        direction="bankruptcy",
    )

    assert consultation.id is not None
    assert consultation.direction == "bankruptcy"
    assert consultation.status == "pending"


@pytest.mark.asyncio
async def test_update_user_contacts(db_session):
    svc = ConsultationService(db_session)
    user = await svc.get_or_create_user("tg_900", "telegram")
    await svc.update_user_contacts(
        user.id,
        full_name="Test User",
        phone="+79990001122",
        email="test@example.com",
    )
    await db_session.refresh(user)

    assert user.full_name == "Test User"
    assert user.phone == "+79990001122"
    assert user.email == "test@example.com"
