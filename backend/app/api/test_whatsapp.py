import logging

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.mongodb import get_db
from app.models.chat import ChatSession, ChatSessionResponse
from app.models.message import Message, MessageResponse
from app.models.webhook import (
    AIReplyTestRequest,
    AIReplyTestResponse,
    WebhookSimulationRequest,
    WebhookSimulationResponse,
)
from app.models.whatsapp import (
    DocumentMessageRequest,
    ImageMessageRequest,
    TextMessageRequest,
    TypingRequest,
    WhatsAppStatusResponse,
    WhatsAppTextMessageResponse,
)
from app.core.config import settings
from app.services.ai_service import generate_ai_reply
from app.services.message_service import save_incoming_message, save_outgoing_message
from app.services.session_service import get_or_create_session
from app.services.tenant_service import get_tenant_by_id, get_tenant_by_phone_number_id
from app.services.whatsapp_service import WhatsAppServiceError, whatsapp_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/test", tags=["test-whatsapp"])


def _normalise_phone(phone: str) -> str:
    phone = phone.strip()
    if not phone.startswith("+"):
        phone = "+" + phone
    return phone


def _extract_message_id(response: dict) -> str | None:
    try:
        return response["messages"][0]["id"]
    except (KeyError, IndexError):
        return None


@router.post(
    "/webhook-simulation",
    response_model=WebhookSimulationResponse,
    summary="Simulate incoming WhatsApp webhook",
    description=(
        "Simulates a WhatsApp message webhook event. This endpoint processes "
        "the message through the full pipeline: tenant lookup, session management, "
        "message storage, AI reply generation, and WhatsApp API response.\n\n"
        "Useful for testing the complete flow without a real WhatsApp message."
    ),
)
async def simulate_webhook(
    request: WebhookSimulationRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    tenant = await get_tenant_by_phone_number_id(db, request.phone_number_id)

    session = await get_or_create_session(
        db,
        tenant_id=tenant.tenant_id,
        customer_wa_id=request.from_number,
        customer_name=request.sender_name,
    )

    msg = await save_incoming_message(
        db=db,
        tenant_id=tenant.tenant_id,
        session_id=session.session_id,
        whatsapp_message_id=f"simulated_{session.session_id[:8]}",
        sender_number=request.from_number,
        sender_name=request.sender_name,
        message_type=request.message_type,
        message_text=request.message_body,
    )

    tenant_token = tenant.whatsapp.access_token or None if tenant.whatsapp else None
    tenant_pid = tenant.whatsapp.phone_number_id or None if tenant.whatsapp else None

    if request.message_type == "text" and request.message_body:
        conversation_history = await db.messages.find(
            {"session_id": session.session_id},
        ).sort("created_at", -1).limit(20).to_list(length=20)
        conversation_history.reverse()

        try:
            ai_reply = await generate_ai_reply(
                tenant=tenant,
                user_message=request.message_body,
                conversation_history=conversation_history,
            )
        except Exception:
            ai_reply = "I'm sorry, I'm having trouble processing your request."

        ai_reply_wamid = None
        try:
            resp = await whatsapp_service.send_text(
                to=request.from_number,
                text=ai_reply,
                phone_number_id=tenant_pid,
                access_token=tenant_token,
            )
            ai_reply_wamid = _extract_message_id(resp)

            await save_outgoing_message(
                db=db,
                tenant_id=tenant.tenant_id,
                session_id=session.session_id,
                whatsapp_message_id=ai_reply_wamid,
                recipient_number=request.from_number,
                recipient_name=request.sender_name,
                message_type="text",
                message_text=ai_reply,
            )
        except WhatsAppServiceError:
            pass
    else:
        ai_reply = None
        ai_reply_wamid = None

    return WebhookSimulationResponse(
        success=True,
        tenant_id=tenant.tenant_id,
        tenant_name=tenant.name,
        session_id=session.session_id,
        message_id=msg.message_id,
        direction="incoming",
        ai_reply=ai_reply,
        ai_reply_message_id=ai_reply_wamid,
    )


@router.post(
    "/ai-reply",
    response_model=AIReplyTestResponse,
    summary="Test AI reply generation",
    description=(
        "Test the AI reply engine directly. Provide a tenant_id, session_id, "
        "and a user message to get an AI-generated reply.\n\n"
        "This does NOT send the reply via WhatsApp — it only generates it."
    ),
)
async def test_ai_reply(
    request: AIReplyTestRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    tenant = await get_tenant_by_id(db, request.tenant_id)

    conversation_history = await db.messages.find(
        {"session_id": request.session_id},
    ).sort("created_at", -1).limit(20).to_list(length=20)
    conversation_history.reverse()

    try:
        reply = await generate_ai_reply(
            tenant=tenant,
            user_message=request.message,
            conversation_history=conversation_history,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    model = tenant.ai_config.model if tenant.ai_config else "gpt-4o"
    provider = (settings.ai_provider or "openai").lower().strip()
    if provider == "groq" and model == settings.openai_default_model:
        model = settings.groq_default_model

    return AIReplyTestResponse(
        success=True,
        reply=reply,
        model=model,
        tenant_id=request.tenant_id,
        session_id=request.session_id,
    )


@router.post(
    "/send-text",
    response_model=WhatsAppTextMessageResponse,
    summary="Send a text message",
)
async def send_text(request: TextMessageRequest):
    to = _normalise_phone(request.phone)
    try:
        response = await whatsapp_service.send_text(to=to, text=request.message)
        return WhatsAppTextMessageResponse(
            success=True,
            whatsapp_message_id=_extract_message_id(response),
        )
    except WhatsAppServiceError as e:
        status_code = e.status_code or status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=e.message)


@router.post(
    "/send-image",
    response_model=WhatsAppTextMessageResponse,
    summary="Send an image message",
)
async def send_image(request: ImageMessageRequest):
    to = _normalise_phone(request.phone)
    try:
        response = await whatsapp_service.send_image(
            to=to,
            image_url=request.image_url,
            caption=request.caption,
        )
        return WhatsAppTextMessageResponse(
            success=True,
            whatsapp_message_id=_extract_message_id(response),
        )
    except WhatsAppServiceError as e:
        status_code = e.status_code or status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=e.message)


@router.post(
    "/send-document",
    response_model=WhatsAppTextMessageResponse,
    summary="Send a document (PDF)",
)
async def send_document(request: DocumentMessageRequest):
    to = _normalise_phone(request.phone)
    try:
        response = await whatsapp_service.send_document(
            to=to,
            document_url=request.document_url,
            filename=request.filename,
        )
        return WhatsAppTextMessageResponse(
            success=True,
            whatsapp_message_id=_extract_message_id(response),
        )
    except WhatsAppServiceError as e:
        status_code = e.status_code or status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=e.message)


@router.post(
    "/typing",
    response_model=WhatsAppStatusResponse,
    summary="Send typing indicator",
)
async def send_typing(request: TypingRequest):
    to = _normalise_phone(request.phone)
    try:
        # await whatsapp_service.typing_on(to=to)
        return WhatsAppStatusResponse(success=True)
    except WhatsAppServiceError as e:
        status_code = e.status_code or status.HTTP_400_BAD_REQUEST
        raise HTTPException(status_code=status_code, detail=e.message)
