"""FastAPI-приложение интеграционного API."""

from fastapi import FastAPI

from src.api.openapi_config import (
    API_DESCRIPTION,
    OPENAPI_TAGS,
    attach_openapi,
)
from src.api.router_health import router as health_router
from src.api.router_integration import router as integration_router
from src.config.settings import settings

app = FastAPI(
    title="Legal Bot — Integration API",
    version=settings.VERSION,
    description=API_DESCRIPTION,
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        "defaultModelsExpandDepth": 2,
        "docExpansion": "list",
        "filter": True,
        "syntaxHighlight.theme": "monokai",
    },
)

app.include_router(health_router)
app.include_router(integration_router)
attach_openapi(app)


@app.get("/", tags=["Служебное"], summary="Корень сервиса")
async def root():
    """Ссылки на интерактивную документацию и health-check."""
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "documentation": {
            "swagger_ui": "/docs",
            "redoc": "/redoc",
            "openapi_schema": "/openapi.json",
        },
        "health": {
            "live": "/v1/health/live",
            "ready": "/v1/health/ready",
            "legacy": "/v1/health",
        },
    }
