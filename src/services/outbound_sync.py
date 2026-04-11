"""Исходящая отправка данных заявки на удалённый URL."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import aiohttp
from loguru import logger

from src.config.settings import settings
from src.database.base import async_session_factory
from src.security.url_validation import is_safe_outbound_webhook_url
from src.services.consultation_service import ConsultationService

if TYPE_CHECKING:
    from datetime import datetime

# Ссылки на fire-and-forget задачи (RUF006 / предотвращение GC)
_outbound_tasks: set[asyncio.Task[None]] = set()


def _serialize_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.isoformat() + "Z"
    return value.isoformat()


def build_consultation_payload(
    consultation,
    user,
) -> dict:
    """JSON-сериализуемый словарь для webhook / внешних систем."""
    return {
        "event": "consultation.created",
        "consultation": {
            "id": consultation.id,
            "chat_id": consultation.chat_id,
            "user_id": consultation.user_id,
            "direction": consultation.direction,
            "status": consultation.status,
            "is_paid": consultation.is_paid,
            "payment_amount": consultation.payment_amount,
            "notes": consultation.notes,
            "created_at": _serialize_dt(consultation.created_at),
            "updated_at": _serialize_dt(consultation.updated_at),
        },
        "user": {
            "id": user.id,
            "messenger_type": user.messenger_type,
            "messenger_user_id": user.messenger_user_id,
            "full_name": user.full_name,
            "phone": user.phone,
            "email": user.email,
            "created_at": _serialize_dt(user.created_at),
        },
    }


async def push_consultation_to_remote(consultation_id: int) -> str:
    """POST JSON на OUTBOUND_WEBHOOK_URL. Результат: ok | no_url | not_found | failed."""
    url = settings.OUTBOUND_WEBHOOK_URL.strip()
    if not url:
        return "no_url"
    if not is_safe_outbound_webhook_url(
        url,
        allow_private=settings.OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS,
    ):
        logger.error(
            "Outbound webhook URL rejected (SSRF protection): "
            "use HTTPS to a public host or set "
            "OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS=True only on trusted networks",
        )
        return "failed"

    async with async_session_factory() as session:
        svc = ConsultationService(session)
        row = await svc.get_consultation_with_user(consultation_id)
        if not row:
            logger.warning(
                f"Outbound: consultation {consultation_id} not found"
            )
            return "not_found"
        consultation, user = row
        payload = build_consultation_payload(consultation, user)

    headers = {"Content-Type": "application/json"}
    token = settings.OUTBOUND_WEBHOOK_TOKEN.strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    timeout = aiohttp.ClientTimeout(total=30)
    try:
        async with (
            aiohttp.ClientSession(timeout=timeout) as http,
            http.post(
                url,
                json=payload,
                headers=headers,
            ) as resp,
        ):
            text = await resp.text()
            if resp.status >= 400:
                logger.error(
                    f"Outbound webhook HTTP {resp.status}: {text[:500]}"
                )
                return "failed"
            logger.info(
                f"Outbound webhook OK for consultation {consultation_id}"
            )
            return "ok"
    except Exception as exc:
        logger.error(f"Outbound webhook failed: {exc}")
        return "failed"


def schedule_push_consultation(consultation_id: int) -> None:
    """Fire-and-forget: не блокирует завершение чата в боте."""
    url = settings.OUTBOUND_WEBHOOK_URL.strip()
    if not url:
        return
    if not is_safe_outbound_webhook_url(
        url,
        allow_private=settings.OUTBOUND_WEBHOOK_ALLOW_PRIVATE_IPS,
    ):
        logger.warning(
            "schedule_push: OUTBOUND_WEBHOOK_URL failed SSRF check, skipped",
        )
        return

    async def _run():
        try:
            code = await push_consultation_to_remote(consultation_id)
            if code not in ("ok", "no_url"):
                logger.debug(f"Outbound result for #{consultation_id}: {code}")
        except Exception as exc:
            logger.error(f"Outbound task error: {exc}")

    task = asyncio.create_task(_run())
    _outbound_tasks.add(task)
    task.add_done_callback(_outbound_tasks.discard)
