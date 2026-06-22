"""
WhatsApp Cloud API — Request & Response Models
===============================================

These models define the wire format for the Phase 3 test endpoints.
Each request maps 1:1 to a WhatsApp Cloud API message type.

Why separate models?
- Keeps the API contract explicit in one file.
- Pydantic v2 validation catches malformed payloads before they reach the service layer.
- Swagger/OpenAPI docs are auto-generated from these models.

How future LangGraph nodes will use these:
  agent_response = await whatsapp_service.send_text(
      to=customer_wa_id,
      text=llm_reply,
  )
"""

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Request models — used by POST /api/v1/test/* endpoints
# ---------------------------------------------------------------------------

class TextMessageRequest(BaseModel):
    """
    Send a plain text message.

    WhatsApp Cloud API endpoint: POST /{version}/{phone-number-id}/messages
    Payload type: "text"

    LangGraph usage:
        After the LLM generates a reply, the agent node calls
        whatsapp_service.send_text(to=session.customer_wa_id, text=llm_response)
    """
    phone: str = Field(
        ...,
        description="Recipient phone number (digits only or E.164 with +)",
        examples=["919999999999"],
        min_length=10,
        max_length=15,
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="Text message body (max 4096 characters)",
        examples=["Hello"],
    )


class ImageMessageRequest(BaseModel):
    """
    Send an image message.

    WhatsApp Cloud API expects one of:
      - "id"  : a previously uploaded media ID
      - "link": a publicly accessible URL  (used here for simplicity)

    The API will download the image from the link and send it.
    Supported formats: JPEG, PNG, WEBP, GIF (static).

    LangGraph usage:
        Agent sends a product image from the catalog.
        whatsapp_service.send_image(to=customer, image_url=product_image_url)
    """
    phone: str = Field(
        ...,
        description="Recipient phone number (digits only or E.164 with +)",
        examples=["919999999999"],
        min_length=10,
        max_length=15,
    )
    image_url: str = Field(
        ...,
        description="Publicly accessible HTTPS URL of the image",
        examples=["https://example.com/image.jpg"],
        max_length=2048,
    )
    caption: str = Field(
        default="",
        max_length=1024,
        description="Image caption (optional)",
        examples=["Example Image"],
    )


class DocumentMessageRequest(BaseModel):
    """
    Send a document message (PDF, DOC, XLS, PPT, TXT, etc.).

    WhatsApp Cloud API expects one of:
      - "id"  : a previously uploaded media ID
      - "link": a publicly accessible URL  (used here for simplicity)

    The filename parameter is what the recipient sees.
    Max file size: 100 MB.

    LangGraph usage:
        Agent sends a brochure, invoice, or report.
        whatsapp_service.send_document(to=customer, document_url=pdf_url)
    """
    phone: str = Field(
        ...,
        description="Recipient phone number (digits only or E.164 with +)",
        examples=["919999999999"],
        min_length=10,
        max_length=15,
    )
    document_url: str = Field(
        ...,
        description="Publicly accessible HTTPS URL of the document",
        examples=["https://example.com/catalog.pdf"],
        max_length=2048,
    )
    filename: str = Field(
        default="document.pdf",
        description="Display filename shown to the recipient",
        examples=["catalog.pdf"],
        max_length=255,
    )


class TypingRequest(BaseModel):
    """
    Send a typing indicator ("typing_on" action).

    WhatsApp Cloud API action types:
      - typing_on   : shows "typing..." bubble
      - typing_off  : hides the bubble (sent automatically after a message)

    Best practice: send typing_on before each bot response, then follow with
    the actual message. The indicator auto-expires after ~20 seconds.

    LangGraph usage:
        Before sending an LLM response, the agent sets the typing indicator.
        # TODO: Re-enable after WhatsApp API compatible implementation
        # await whatsapp_service.typing_on(to=customer_wa_id)
        # await asyncio.sleep(0.5)           # brief pause for realism
        await whatsapp_service.send_text(...)
    """
    phone: str = Field(
        ...,
        description="Recipient phone number (digits only or E.164 with +)",
        examples=["919999999999"],
        min_length=10,
        max_length=15,
    )


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class WhatsAppTextMessageResponse(BaseModel):
    """
    Standard response for send-text / send-image / send-document endpoints.
    """
    success: bool = Field(..., description="True if the WhatsApp API returned 200/201")
    whatsapp_message_id: str | None = Field(
        default=None,
        description="The wamid (WhatsApp Message ID) assigned by Meta",
        examples=["wamid.HBgNMTIzNDU2Nzg5MBUCABEYOjNF"],
    )
    error: str | None = Field(
        default=None,
        description="Error message from WhatsApp API if the request failed",
        examples=[
            "(#100) Parameter 'to' is required",
            "(#131026) Recipient phone number not in allowed list",
            "(#190) Invalid OAuth 2.0 Access Token",
        ],
    )


class WhatsAppStatusResponse(BaseModel):
    """
    Standard response for typing / mark-read endpoints (no message ID returned).
    """
    success: bool
    error: str | None = Field(default=None)
