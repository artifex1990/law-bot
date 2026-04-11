"""Общие проверки health для webhook-портов Telegram и MAX (aiohttp).

Один набор маршрутов **GET /health/live** и **GET /health/ready** (`run_ready_checks`),
различается только поле **service** в JSON.
"""

from __future__ import annotations

from aiohttp import web
from maxapi.webhook.aiohttp import AiohttpMaxWebhook
from maxapi.webhook.base import DEFAULT_PATH

from src.services.health_service import run_ready_checks

# Значения поля service в ответах (как раньше у каждого мессенджера)
SERVICE_TELEGRAM_WEBHOOK = "telegram_webhook"
SERVICE_MAX_WEBHOOK = "max_webhook"


def register_aiohttp_webhook_health_routes(
    app: web.Application,
    service: str,
) -> None:
    """Зарегистрировать GET /health/live и /health/ready на aiohttp-приложении."""

    async def _health_live(_request: web.Request) -> web.Response:
        return web.json_response(
            {"status": "ok", "service": service},
        )

    async def _health_ready(_request: web.Request) -> web.Response:
        data = await run_ready_checks()
        code = 200 if data["ready"] else 503
        payload = {**data, "service": service}
        return web.json_response(payload, status=code)

    app.router.add_get("/health/live", _health_live)
    app.router.add_get("/health/ready", _health_ready)


class AiohttpMaxWebhookWithHealth(AiohttpMaxWebhook):
    """MAX: то же aiohttp-приложение, что в maxapi, плюс общие health-маршруты."""

    def create_app(self, path: str = DEFAULT_PATH) -> web.Application:
        app = web.Application()
        app.on_startup.append(self.on_startup)
        register_aiohttp_webhook_health_routes(app, SERVICE_MAX_WEBHOOK)
        self.setup(app, path)
        return app
