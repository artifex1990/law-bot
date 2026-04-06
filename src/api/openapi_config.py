"""Описание OpenAPI (Swagger UI / ReDoc) для интеграционного API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.openapi.utils import get_openapi

if TYPE_CHECKING:
    from fastapi import FastAPI

API_DESCRIPTION = """
## Назначение

HTTP API для **CRM и внешних сервисов**: чтение заявок (консультаций)
и связанных пользователей из той же базы, что использует бот.

## Документация

- **Swagger UI** — этот интерфейс (`/docs`)
- **ReDoc** — альтернативная справка (`/redoc`)
- **OpenAPI JSON** — `/openapi.json` (Postman, генерация клиентов)

## Авторизация

Если задан **`INTEGRATION_API_TOKEN`** (непустая строка):

1. Нажмите **Authorize** и введите токен в **BearerAuth**, **или**
2. Укажите заголовок **`X-API-Key`** с тем же значением.

Если токен **пустой** — проверка отключена (только изолированная сеть;
в интернете задайте токен).

## Health на порту webhook

Если интеграционный API **выключен** (`API_ENABLED=False`), а бот в режиме
**webhook**, проверки доступны на том же порту, что и webhook
(`WEBHOOK_PORT`): **`GET /health/live`**, **`GET /health/ready`**
(см. README, раздел про health).

## Методы

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/v1/health`, `/v1/health/live` | Liveness (без токена, без БД) |
| GET | `/v1/health/ready` | Readiness (проверка БД, **503** при сбое) |
| GET | `/v1/consultations/{id}` | Заявка + пользователь |
| GET | `/v1/consultations` | Поиск: phone, email, status (≥1) |
| POST | `/v1/consultations/{id}/push` | Повторный POST на webhook |

### Поиск заявок

- **phone** — для РФ → `+7XXXXXXXXXX`
- **email** — без учёта регистра
- **status** — например `pending`
- Фильтры **комбинируются** (AND)

### Исходящий webhook (бот)

При новой заявке — **POST** на `OUTBOUND_WEBHOOK_URL`
(`event`, `consultation`, `user`). Заголовок **Bearer** к внешнему URL —
если задан `OUTBOUND_WEBHOOK_TOKEN`.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "Служебное",
        "description": "Проверка работы сервиса без авторизации.",
    },
    {
        "name": "Заявки",
        "description": (
            "Чтение заявок и пользователей. "
            "Токен: Authorize (Bearer или X-API-Key)."
        ),
    },
]

_SECURED_PATHS = frozenset(
    {
        "/v1/consultations",
        "/v1/consultations/{consultation_id}",
        "/v1/consultations/{consultation_id}/push",
    },
)


def build_openapi_schema(app: FastAPI) -> dict:
    """OpenAPI 3: security для защищённых маршрутов (Swagger Authorize)."""
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    components = openapi_schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "opaque",
        "description": (
            "**INTEGRATION_API_TOKEN**. В Swagger введите только токен "
            "(префикс Bearer подставится сам)."
        ),
    }
    schemes["ApiKeyAuth"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": (
            "Тот же секрет, что Bearer (альтернативный заголовок)."
        ),
    }

    paths = openapi_schema.get("paths") or {}
    for path_key, path_item in paths.items():
        if path_key not in _SECURED_PATHS:
            continue
        for method, operation in list(path_item.items()):
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            if not isinstance(operation, dict):
                continue
            operation["security"] = [
                {"BearerAuth": []},
                {"ApiKeyAuth": []},
            ]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


def attach_openapi(app: FastAPI) -> None:
    """Подключить кастомную генерацию схемы."""

    def _openapi() -> dict:
        return build_openapi_schema(app)

    app.openapi = _openapi  # type: ignore[method-assign]
