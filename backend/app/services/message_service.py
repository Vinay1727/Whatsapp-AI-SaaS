from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.message import Message, MessageContent
from app.services.logger_service import log_message_saved


async def save_incoming_message(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    session_id: str,
    whatsapp_message_id: str,
    sender_number: str,
    sender_name: str,
    message_type: str,
    message_text: str | None = None,
    content: MessageContent | None = None,
) -> Message:
    now = datetime.now(timezone.utc)

    message = Message(
        tenant_id=tenant_id,
        session_id=session_id,
        whatsapp_message_id=whatsapp_message_id,
        sender_number=sender_number,
        sender_name=sender_name,
        direction="incoming",
        message_type=message_type,
        message_text=message_text,
        content=content or MessageContent(text=message_text),
        whatsapp_status="received",
        created_at=now,
    )

    await db.messages.insert_one(message.model_dump())

    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "last_message_at": now,
                "last_message_preview": (message_text or f"[{message_type} media]")[:200],
                "updated_at": now,
            },
            "$inc": {"message_count": 1},
        },
    )

    log_message_saved(whatsapp_message_id, "incoming", message_type)
    return message


async def save_outgoing_message(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    session_id: str,
    whatsapp_message_id: str | None,
    recipient_number: str,
    recipient_name: str,
    message_type: str,
    message_text: str | None = None,
    content: MessageContent | None = None,
) -> Message:
    now = datetime.now(timezone.utc)

    message = Message(
        tenant_id=tenant_id,
        session_id=session_id,
        whatsapp_message_id=whatsapp_message_id,
        sender_number=recipient_number,
        sender_name=recipient_name,
        direction="outgoing",
        message_type=message_type,
        message_text=message_text,
        content=content or MessageContent(text=message_text),
        whatsapp_status="sent",
        created_at=now,
    )

    await db.messages.insert_one(message.model_dump())

    await db.chat_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "last_message_at": now,
                "last_message_preview": (message_text or f"[{message_type} media]")[:200],
                "updated_at": now,
            },
            "$inc": {"message_count": 1},
        },
    )

    log_message_saved(whatsapp_message_id or "pending", "outgoing", message_type)
    return message
