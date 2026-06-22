from datetime import datetime, timezone
from uuid import uuid4
from typing import Optional
from pydantic import BaseModel, Field


class WhatsAppConfig(BaseModel):
    phone_number_id: str
    business_account_id: str = ""
    access_token: str = ""
    webhook_secret: str = ""
    api_version: str = "v21.0"


class AIConfig(BaseModel):
    openai_api_key: str = ""
    system_prompt: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 1024
    confidence_threshold: float = 0.8
    human_handover_threshold: float = 0.6


class TenantSettings(BaseModel):
    timezone: str = "UTC"
    business_name: str = ""


class MediaItem(BaseModel):
    media_id: str = ""
    type: str = "image"
    url: str = ""
    caption: str = ""
    tags: list[str] = []
    active: bool = True


class Tenant(BaseModel):
    tenant_id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    slug: str
    status: str = "active"

    whatsapp: Optional[WhatsAppConfig] = None
    ai_config: AIConfig = Field(default_factory=AIConfig)
    settings: TenantSettings = Field(default_factory=TenantSettings)
    media_library: list[MediaItem] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TenantResponse(BaseModel):
    tenant_id: str
    name: str
    slug: str
    status: str
    settings: TenantSettings
    created_at: datetime
    updated_at: datetime
