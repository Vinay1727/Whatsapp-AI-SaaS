from typing import Optional
from pydantic import BaseModel, Field


class WhatsAppTextEntry(BaseModel):
    body: str = ""


class WhatsAppImageEntry(BaseModel):
    id: str = ""
    mime_type: str = ""
    sha256: str = ""
    caption: Optional[str] = None


class WhatsAppDocumentEntry(BaseModel):
    id: str = ""
    mime_type: str = ""
    sha256: str = ""
    filename: str = ""
    caption: Optional[str] = None


class WhatsAppAudioEntry(BaseModel):
    id: str = ""
    mime_type: str = ""
    sha256: str = ""


class WhatsAppLocationEntry(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0
    name: Optional[str] = None
    address: Optional[str] = None


class WhatsAppMessage(BaseModel):
    from_: str = Field(..., alias="from")
    id: str
    timestamp: str
    type: str
    text: Optional[WhatsAppTextEntry] = None
    image: Optional[WhatsAppImageEntry] = None
    document: Optional[WhatsAppDocumentEntry] = None
    audio: Optional[WhatsAppAudioEntry] = None
    location: Optional[WhatsAppLocationEntry] = None


class WhatsAppContactProfile(BaseModel):
    name: str = ""


class WhatsAppContact(BaseModel):
    profile: WhatsAppContactProfile = WhatsAppContactProfile()
    wa_id: str = ""


class WhatsAppMetadata(BaseModel):
    phone_number_id: str = ""
    display_phone_number: str = ""


class WhatsAppStatusEntry(BaseModel):
    id: str = ""
    status: str = ""
    timestamp: str = ""
    recipient_id: str = ""
    conversation: Optional[dict] = None
    pricing: Optional[dict] = None


class WhatsAppValue(BaseModel):
    messaging_product: str = ""
    metadata: WhatsAppMetadata = WhatsAppMetadata()
    contacts: list[WhatsAppContact] = []
    messages: list[WhatsAppMessage] = []
    statuses: list[WhatsAppStatusEntry] = []


class WhatsAppChange(BaseModel):
    value: WhatsAppValue = WhatsAppValue()
    field: str = ""


class WhatsAppEntry(BaseModel):
    id: str = ""
    changes: list[WhatsAppChange] = []


class WhatsAppWebhookPayload(BaseModel):
    object: str = ""
    entry: list[WhatsAppEntry] = []


class WebhookSimulationRequest(BaseModel):
    phone_number_id: str = Field(
        ...,
        description="WhatsApp Business phone number ID",
        examples=["1093370313870773"],
    )
    from_number: str = Field(
        ...,
        description="Sender's phone number in E.164 format",
        examples=["+919999999999"],
    )
    sender_name: str = Field(
        default="Customer",
        description="Sender's profile name",
    )
    message_type: str = Field(
        default="text",
        description="Message type: text, image, document, audio, location",
    )
    message_body: str = Field(
        default="Hello",
        description="Message text body (for text type)",
    )
    media_url: str = Field(
        default="",
        description="Media URL (for image/document/audio types)",
    )
    latitude: float = Field(default=0.0, description="Latitude (for location type)")
    longitude: float = Field(default=0.0, description="Longitude (for location type)")


class WebhookSimulationResponse(BaseModel):
    success: bool
    tenant_id: str
    tenant_name: str
    session_id: str
    message_id: str
    direction: str
    ai_reply: Optional[str] = None
    ai_reply_message_id: Optional[str] = None


class AIReplyTestRequest(BaseModel):
    tenant_id: str = Field(..., description="Tenant ID to use for AI processing")
    session_id: str = Field(..., description="Session ID for context")
    message: str = Field(..., description="User message to generate AI reply for")


class AIReplyTestResponse(BaseModel):
    success: bool
    reply: str
    model: str
    tenant_id: str
    session_id: str
