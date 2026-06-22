from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class MessageContent(BaseModel):
    text: Optional[str] = None
    media_url: Optional[str] = None
    mime_type: Optional[str] = None
    caption: Optional[str] = None
    file_size: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None


class MessageBase(BaseModel):
    tenant_id: str
    session_id: str
    whatsapp_message_id: Optional[str] = None
    sender_number: Optional[str] = None
    sender_name: Optional[str] = None
    direction: str = "incoming"
    message_type: str = "text"
    message_text: Optional[str] = None
    content: MessageContent = MessageContent()
    whatsapp_status: str = "received"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Message(MessageBase):
    message_id: str = Field(default_factory=lambda: str(uuid4()))


class MessageResponse(MessageBase):
    message_id: str
