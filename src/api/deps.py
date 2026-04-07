"""Зависимости FastAPI: БД и авторизация."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import settings
from src.database.base import async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def verify_integration_auth(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    """Если INTEGRATION_API_TOKEN задан - требуется Bearer или X-API-Key."""
    expected = settings.INTEGRATION_API_TOKEN.strip()
    if not expected:
        return

    provided: str | None = None
    if authorization:
        prefix = "Bearer "
        if authorization.startswith(prefix):
            provided = authorization[len(prefix) :].strip()
        elif authorization.strip():
            provided = authorization.strip()
    if x_api_key:
        provided = x_api_key.strip()

    if not provided or provided != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API token",
        )


DbSession = Annotated[AsyncSession, Depends(get_db)]
RequireAuth = Annotated[None, Depends(verify_integration_auth)]
