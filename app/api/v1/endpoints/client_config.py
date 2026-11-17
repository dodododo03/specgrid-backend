from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings

router = APIRouter(tags=["config"])


class ClientConfig(BaseModel):
    kakao_js_key: str | None = Field(description="카카오맵 JavaScript 키 (설정되지 않았으면 null → 지도 숨김)")


@router.get("/client-config")
def client_config() -> ClientConfig:
    """Public settings the web frontend needs at runtime. Only values that are safe to expose."""
    return ClientConfig(kakao_js_key=settings.kakao_js_key or None)
