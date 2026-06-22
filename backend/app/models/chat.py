from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class EscalationInfo(BaseModel):
    is_escalated: bool = False
    escalated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    reason: Optional[str] = None
    resolved_at: Optional[datetime] = None


class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    customer_wa_id: str
    customer_name: str = ""

    status: str = "active"
    mode: str = "ai"

    message_count: int = 0
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None

    escalation: EscalationInfo = EscalationInfo()

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSessionResponse(BaseModel):
    session_id: str
    tenant_id: str
    customer_wa_id: str
    customer_name: str
    status: str
    mode: str
    message_count: int
    last_message_at: Optional[datetime]
    last_message_preview: Optional[str]
    escalation: EscalationInfo
    created_at: datetime
    updated_at: datetime
