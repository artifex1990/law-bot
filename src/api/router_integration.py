"""Маршруты заявок для внешних интеграций."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query
from starlette import status as http_status

from src.api.deps import DbSession, RequireAuth
from src.api.schemas import (
    ConsultationDetailResponse,
    ConsultationListResponse,
    ConsultationOut,
    PushResponse,
    UserOut,
)
from src.services.consultation_service import ConsultationService
from src.services.outbound_sync import push_consultation_to_remote

router = APIRouter(prefix="/v1")


def _to_detail(c, u) -> ConsultationDetailResponse:
    return ConsultationDetailResponse(
        consultation=ConsultationOut(
            id=c.id,
            chat_id=c.chat_id,
            user_id=c.user_id,
            direction=c.direction,
            status=c.status,
            is_paid=c.is_paid,
            payment_amount=c.payment_amount,
            notes=c.notes,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ),
        user=UserOut(
            id=u.id,
            messenger_type=u.messenger_type,
            messenger_user_id=u.messenger_user_id,
            full_name=u.full_name,
            phone=u.phone,
            email=u.email,
            created_at=u.created_at,
        ),
    )


@router.get(
    "/consultations/{consultation_id}",
    response_model=ConsultationDetailResponse,
    tags=["Заявки"],
    summary="Заявка по идентификатору",
    description=(
        "Возвращает одну запись **consultations** и связанного **users** "
        "(имя, телефон, email, мессенджер)."
    ),
    responses={
        401: {"description": "Неверный или отсутствующий токен(если включён)"},
        404: {"description": "Заявка с таким id не найдена"},
    },
)
async def get_consultation(
    _auth: RequireAuth,
    db: DbSession,
    consultation_id: Annotated[
        int,
        Path(description="ID заявки в таблице consultations"),
    ],
):
    svc = ConsultationService(db)
    row = await svc.get_consultation_with_user(consultation_id)
    if not row:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Consultation not found",
        )
    c, u = row
    return _to_detail(c, u)


@router.get(
    "/consultations",
    response_model=ConsultationListResponse,
    tags=["Заявки"],
    summary="Поиск заявок",
    description=(
        "Фильтрация по телефону, email и/или статусу заявки. "
        "Нужен **хотя бы один** параметр. Несколько параметров объединяются "
        "по **AND**."
    ),
    responses={
        400: {"description": "Не передан ни один фильтр"},
        401: {"description": "Неверный или отсутствующий токен(если включён)"},
    },
)
async def list_consultations(
    _auth: RequireAuth,
    db: DbSession,
    phone: Annotated[
        str | None,
        Query(description="Телефон; для РФ приводится к +7XXXXXXXXXX"),
    ] = None,
    email: Annotated[
        str | None,
        Query(description="Email; сравнение без учёта регистра"),
    ] = None,
    consultation_status: Annotated[
        str | None,
        Query(
            description="Статус заявки, например pending",
            alias="status",
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200, description="Максимум записей в ответе"),
    ] = 50,
):
    if not phone and not email and not consultation_status:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Укажите хотя бы один фильтр: phone, email или status",
        )
    svc = ConsultationService(db)
    rows = await svc.search_consultations(
        phone=phone,
        email=email,
        status=consultation_status,
        limit=limit,
    )
    items = [_to_detail(c, u) for c, u in rows]
    return ConsultationListResponse(items=items, count=len(items))


@router.post(
    "/consultations/{consultation_id}/push",
    response_model=PushResponse,
    tags=["Заявки"],
    summary="Повторная отправка на webhook",
    description=(
        "Отправляет JSON заявки на URL из **OUTBOUND_WEBHOOK_URL** "
        "(тот же формат, что при автоматической отправке из бота). "
        "Заголовок Bearer к удалённому серверу - если задан "
        "**OUTBOUND_WEBHOOK_TOKEN**."
    ),
    responses={
        401: {"description": "Неверный или отсутствующий токен(если включён)"},
        404: {"description": "Заявка не найдена"},
        502: {"description": "Удалённый сервер отклонил запрос"},
        503: {"description": "OUTBOUND_WEBHOOK_URL не настроен"},
    },
)
async def push_consultation(
    _auth: RequireAuth,
    consultation_id: Annotated[
        int,
        Path(description="ID заявки"),
    ],
):
    code = await push_consultation_to_remote(consultation_id)
    if code == "no_url":
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OUTBOUND_WEBHOOK_URL is not configured",
        )
    if code == "not_found":
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="Consultation not found",
        )
    if code == "failed":
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="Remote server rejected the webhook",
        )
    return PushResponse(ok=True, detail="sent")
