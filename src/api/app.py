"""FastAPI-приложение интеграционного API."""

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.openapi_config import (
    API_DESCRIPTION,
    OPENAPI_TAGS,
    attach_openapi,
)
from src.api.router_health import router as health_router
from src.api.router_integration import router as integration_router
from src.config.settings import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Базовые заголовки для снижения риска XSS/clickjacking на API."""

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers.setdefault(
            "Referrer-Policy",
            "strict-origin-when-cross-origin",
        )
        return response


def _docs_url() -> str | None:
    return "/docs" if settings.API_DOCS_ENABLED else None


app = FastAPI(
    title="Legal Bot - Integration API",
    version=settings.VERSION,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    docs_url=_docs_url(),
    redoc_url=("/redoc" if settings.API_DOCS_ENABLED else None),
    openapi_url=("/openapi.json" if settings.API_DOCS_ENABLED else None),
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 2,
        "docExpansion": "list",
        "filter": True,
        "syntaxHighlight.theme": "monokai",
    },
)

app.add_middleware(SecurityHeadersMiddleware)

app.include_router(health_router)
app.include_router(integration_router)
attach_openapi(app)


@app.get("/", tags=["Служебное"], summary="Корень сервиса")
async def root():
    """Ссылки на документацию (если включена) и health-check."""
    out: dict = {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "health": {
            "live": "/v1/health/live",
            "ready": "/v1/health/ready",
            "legacy": "/v1/health",
        },
    }
    if settings.API_DOCS_ENABLED:
        out["documentation"] = {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_schema": "/openapi.json",
        }
    return out
