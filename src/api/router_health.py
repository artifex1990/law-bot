"""Маршруты liveness / readiness для оркестраторов и балансировщиков."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.api.schemas import HealthLiveResponse, HealthReadyResponse
from src.config.settings import settings
from src.services.health_service import run_ready_checks

router = APIRouter(prefix="/v1", tags=["Служебное"])


@router.get(
    "/health",
    response_model=HealthLiveResponse,
    summary="Liveness (совместимость)",
    description=(
        "Процесс отвечает. Не проверяет БД - для Kubernetes livenessProbe."
    ),
)
async def health_legacy():
    return HealthLiveResponse(
        status="ok",
        service="legal_bot_integration",
    )


@router.get(
    "/health/live",
    response_model=HealthLiveResponse,
    summary="Liveness",
    description="Только факт, что HTTP-слой жив. Без обращения к БД.",
)
async def health_live():
    return HealthLiveResponse(
        status="ok",
        service="legal_bot_integration",
    )


@router.get(
    "/health/ready",
    response_model=HealthReadyResponse,
    summary="Readiness",
    description=(
        "Проверка **БД** (`SELECT 1`). HTTP **503**, если БД недоступна "
        "(Kubernetes readinessProbe)."
    ),
    responses={
        503: {"description": "БД или другая проверка не прошла"},
    },
)
async def health_ready():
    data = await run_ready_checks()
    body = HealthReadyResponse(
        status=data["status"],
        ready=data["ready"],
        checks=data["checks"],
        version=settings.VERSION,
    )
    if not data["ready"]:
        return JSONResponse(
            status_code=503,
            content=body.model_dump(),
        )
    return body
