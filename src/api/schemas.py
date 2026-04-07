"""Схемы ответов интеграционного API."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    """Пользователь бота (контакты для CRM)."""

    id: int
    messenger_type: str = Field(description="telegram | max")
    messenger_user_id: str
    full_name: str | None = None
    phone: str | None = Field(default=None, description="Телефон в БД")
    email: str | None = None
    created_at: datetime | None = Field(
        default=None,
        description="Регистрация в системе",
    )


class ConsultationOut(BaseModel):
    """Заявка на консультацию."""

    id: int
    chat_id: int = Field(description="Связанный чат")
    user_id: int
    direction: str = Field(description="Код направления, напр. bankruptcy")
    status: str = Field(description="pending и др.")
    is_paid: bool
    payment_amount: float | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ConsultationDetailResponse(BaseModel):
    """Одна заявка с данными пользователя."""

    consultation: ConsultationOut
    user: UserOut


class ConsultationListResponse(BaseModel):
    """Результат поиска по фильтрам."""

    items: list[ConsultationDetailResponse]
    count: int = Field(description="Число записей в этом ответе")


class HealthLiveResponse(BaseModel):
    """Liveness: процесс принимает HTTP."""

    status: str = Field(default="ok", description="Сервис жив")
    service: str = Field(description="Идентификатор сервиса")


class HealthReadyResponse(BaseModel):
    """Readiness: зависимости (БД) доступны."""

    status: str = Field(description="ready | unready")
    ready: bool
    checks: dict[str, str] = Field(
        description="Ключ - имя проверки, значение - ok или fail: …",
    )
    version: str = Field(description="Версия приложения")


class PushResponse(BaseModel):
    """Результат вызова повторной отправки на webhook."""

    ok: bool
    detail: str | None = Field(default=None, description="Пояснение")
