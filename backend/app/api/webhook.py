import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.core.exceptions import (
    AppException,
    TenantNotFoundError,
    WebhookValidationError,
)
from app.db.mongodb import get_db
from app.models.message import MessageContent
from app.models.webhook import (
    WhatsAppWebhookPayload,
)
from app.services.ai_service import generate_ai_reply
from app.services.logger_service import (
    log_error,
    log_message_status,
    log_tenant_identified,
    log_webhook_received,
)
from app.services.message_service import (
    save_incoming_message,
    save_outgoing_message,
    update_message_status,
)
from app.services.session_service import get_or_create_session
from app.services.tenant_service import get_tenant_by_phone_number_id
from app.services.whatsapp_service import WhatsAppServiceError, whatsapp_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])


def validate_signature(raw_body: bytes, signature_header: str) -> bool:
    if not settings.meta_app_secret:
        logger.warning("[WEBHOOK] META_APP_SECRET not set — skipping signature validation")
        return True
    if not signature_header:
        raise WebhookValidationError("Missing x-hub-signature-256 header")

    expected_signature = hmac.new(
        settings.meta_app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    expected = f"sha256={expected_signature}"

    return hmac.compare_digest(expected, signature_header)


def extract_message_info(payload: WhatsAppWebhookPayload) -> list[dict]:
    messages = []
    for entry in payload.entry:
        for change in entry.changes:
            value = change.value
            if not value.messages:
                continue
            phone_number_id = value.metadata.phone_number_id
            logger.info(
                "[WEBHOOK_PNID] phone_number_id=%r type=%s len=%d",
                phone_number_id, type(phone_number_id).__name__,
                len(phone_number_id) if isinstance(phone_number_id, str) else -1,
            )
            contacts_map = {
                c.wa_id: c.profile.name for c in value.contacts
            }
            for msg in value.messages:
                sender_wa_id = msg.from_
                sender_name = contacts_map.get(sender_wa_id, "")

                message_type = msg.type
                message_text = None
                content = MessageContent()

                if msg.text:
                    message_text = msg.text.body
                    content.text = msg.text.body
                elif msg.image:
                    message_type = "image"
                    content.media_url = msg.image.id
                    content.mime_type = msg.image.mime_type
                    content.caption = msg.image.caption
                    message_text = msg.image.caption or "[Image]"
                elif msg.document:
                    message_type = "document"
                    content.media_url = msg.document.id
                    content.mime_type = msg.document.mime_type
                    content.caption = msg.document.caption
                    message_text = msg.document.caption or f"[Document: {msg.document.filename}]"
                elif msg.audio:
                    message_type = "audio"
                    content.media_url = msg.audio.id
                    content.mime_type = msg.audio.mime_type
                    message_text = "[Audio]"
                elif msg.location:
                    message_type = "location"
                    content.latitude = msg.location.latitude
                    content.longitude = msg.location.longitude
                    content.location_name = msg.location.name
                    content.location_address = msg.location.address
                    message_text = f"[Location: {msg.location.latitude},{msg.location.longitude}]"

                messages.append({
                    "phone_number_id": phone_number_id,
                    "sender_wa_id": sender_wa_id,
                    "sender_name": sender_name,
                    "whatsapp_message_id": msg.id,
                    "timestamp": msg.timestamp,
                    "message_type": message_type,
                    "message_text": message_text,
                    "content": content,
                })
    return messages


async def process_whatsapp_message(
    db: AsyncIOMotorDatabase,
    msg_info: dict,
) -> dict:
    phone_number_id = msg_info["phone_number_id"]
    sender_wa_id = msg_info["sender_wa_id"]
    sender_name = msg_info["sender_name"]
    whatsapp_message_id = msg_info["whatsapp_message_id"]
    message_type = msg_info["message_type"]
    message_text = msg_info["message_text"]
    content = msg_info["content"]

    tenant = await get_tenant_by_phone_number_id(db, phone_number_id)
    log_tenant_identified(phone_number_id, tenant.tenant_id, tenant.name)

    session = await get_or_create_session(
        db,
        tenant_id=tenant.tenant_id,
        customer_wa_id=sender_wa_id,
        customer_name=sender_name,
    )

    await save_incoming_message(
        db=db,
        tenant_id=tenant.tenant_id,
        session_id=session.session_id,
        whatsapp_message_id=whatsapp_message_id,
        sender_number=sender_wa_id,
        sender_name=sender_name,
        message_type=message_type,
        message_text=message_text,
        content=content,
    )

    tenant_token = None
    tenant_pid = None
    if tenant.whatsapp:
        tenant_token = tenant.whatsapp.access_token or None
        tenant_pid = tenant.whatsapp.phone_number_id or None

    try:
        await whatsapp_service.mark_as_read(
            whatsapp_message_id,
            phone_number_id=tenant_pid,
            access_token=tenant_token,
        )
    except WhatsAppServiceError:
        pass

    # TODO: Re-enable after WhatsApp API compatible implementation
    # try:
    #     await whatsapp_service.typing_on(
    #         sender_wa_id,
    #         phone_number_id=tenant_pid,
    #         access_token=tenant_token,
    #     )
    # except WhatsAppServiceError:
    #     pass

    if message_type != "text":
        logger.info("[WEBHOOK] Non-text message (type=%s) — sending acknowledgment", message_type)
        ack_text = f"Received your {message_type}. A human agent will review it shortly."
        if message_type == "image":
            ack_text = "Thanks for the image! Our team will review it."
        elif message_type == "document":
            ack_text = "Thanks for the document! We'll take a look."
        elif message_type == "audio":
            ack_text = "Thanks for the audio message!"
        elif message_type == "location":
            ack_text = "Thanks for sharing your location!"

        try:
            resp = await whatsapp_service.send_text(
                to=sender_wa_id,
                text=ack_text,
                phone_number_id=tenant_pid,
                access_token=tenant_token,
            )
            wamid = resp.get("messages", [{}])[0].get("id")
            await save_outgoing_message(
                db=db,
                tenant_id=tenant.tenant_id,
                session_id=session.session_id,
                whatsapp_message_id=wamid,
                recipient_number=sender_wa_id,
                recipient_name=sender_name,
                message_type="text",
                message_text=ack_text,
            )
        except WhatsAppServiceError as e:
            log_error("SEND_ACK", str(e))

        return {
            "tenant_id": tenant.tenant_id,
            "tenant_name": tenant.name,
            "session_id": session.session_id,
            "ai_reply": ack_text,
            "ai_reply_sent": True,
        }

    conversation_history = await db.messages.find(
        {"session_id": session.session_id},
    ).sort("created_at", -1).limit(20).to_list(length=20)
    conversation_history.reverse()

    try:
        ai_reply = await generate_ai_reply(
            tenant=tenant,
            user_message=message_text or "",
            conversation_history=conversation_history,
        )
    except AppException:
        ai_reply = "I'm sorry, I'm having trouble processing your request right now. Please try again later."

    try:
        resp = await whatsapp_service.send_text(
            to=sender_wa_id,
            text=ai_reply,
            phone_number_id=tenant_pid,
            access_token=tenant_token,
        )
        wamid = resp.get("messages", [{}])[0].get("id")

        await save_outgoing_message(
            db=db,
            tenant_id=tenant.tenant_id,
            session_id=session.session_id,
            whatsapp_message_id=wamid,
            recipient_number=sender_wa_id,
            recipient_name=sender_name,
            message_type="text",
            message_text=ai_reply,
        )
        ai_reply_sent = True
    except WhatsAppServiceError as e:
        log_error("SEND_AI_REPLY", str(e))
        ai_reply_sent = False

    return {
        "tenant_id": tenant.tenant_id,
        "tenant_name": tenant.name,
        "session_id": session.session_id,
        "ai_reply": ai_reply,
        "ai_reply_sent": ai_reply_sent,
    }


def extract_status_info(payload: WhatsAppWebhookPayload) -> list[dict]:
    statuses = []
    for entry in payload.entry:
        for change in entry.changes:
            value = change.value
            for s in value.statuses:
                statuses.append({
                    "whatsapp_message_id": s.id,
                    "status": s.status,
                    "recipient_id": s.recipient_id,
                    "timestamp": s.timestamp,
                })
    return statuses


async def process_status_update(
    db: AsyncIOMotorDatabase,
    status_info: dict,
) -> dict:
    wamid = status_info["whatsapp_message_id"]
    status = status_info["status"]
    recipient_id = status_info["recipient_id"]

    log_message_status(wamid, status, recipient_id)
    await update_message_status(db, wamid, status)

    return {
        "whatsapp_message_id": wamid,
        "status": status,
        "updated": True,
    }


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.webhook_verify_token:
        logger.info("[WEBHOOK_VERIFIED] challenge=%s", hub_challenge)
        return Response(content=hub_challenge, media_type="text/plain")
    logger.warning(
        "[WEBHOOK_VERIFY_FAILED] mode=%s token=%s",
        hub_mode, hub_verify_token,
    )
    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("")
async def receive_webhook(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    raw_body = await request.body()
    signature = request.headers.get("x-hub-signature-256", "")

    log_webhook_received(len(raw_body))

    is_valid = validate_signature(raw_body, signature)
    if not is_valid:
        log_error("WEBHOOK_SIGNATURE", "Signature mismatch")
        raise HTTPException(status_code=400, detail="Invalid signature")

    try:
        payload_dict = json.loads(raw_body)
    except json.JSONDecodeError:
        log_error("WEBHOOK_PARSE", "Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    payload = WhatsAppWebhookPayload.model_validate(payload_dict)

    if payload.object != "whatsapp_business_account":
        logger.info("[WEBHOOK] Ignoring non-whatsapp event: %s", payload.object)
        return {"status": "ignored"}

    if not payload.entry:
        return {"status": "ok", "processed": 0}

    results = []
    for msg_info in extract_message_info(payload):
        try:
            result = await process_whatsapp_message(db, msg_info)
            results.append(result)
        except TenantNotFoundError as e:
            log_error("TENANT_NOT_FOUND", str(e))
            results.append({
                "error": str(e.message),
                "phone_number_id": msg_info["phone_number_id"],
            })
        except AppException as e:
            log_error("PROCESSING_ERROR", str(e))
            results.append({
                "error": str(e.message),
                "code": e.code,
            })
        except Exception as e:
            log_error("UNEXPECTED", str(e))
            results.append({
                "error": f"Unexpected error: {str(e)}",
            })

    for status_info in extract_status_info(payload):
        try:
            result = await process_status_update(db, status_info)
            results.append(result)
        except Exception as e:
            log_error("STATUS_UPDATE", str(e))
            results.append({
                "error": f"Status update error: {str(e)}",
            })

    logger.info("[WEBHOOK_PROCESSED] messages=%d", len(results))
    return {"status": "ok", "processed": len(results), "results": results}
