from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.chat import ChatSession
from app.services.logger_service import log_session_created, log_session_updated


async def get_or_create_session(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
    customer_wa_id: str,
    customer_name: str = "",
) -> ChatSession:
    now = datetime.now(timezone.utc)

    active_session = await db.chat_sessions.find_one(
        {
            "tenant_id": tenant_id,
            "customer_wa_id": customer_wa_id,
            "status": {"$in": ["active", "waiting_for_bot"]},
        }
    )
    if active_session:
        if customer_name and not active_session.get("customer_name"):
            await db.chat_sessions.update_one(
                {"session_id": active_session["session_id"]},
                {"$set": {"customer_name": customer_name, "updated_at": now}},
            )
            active_session["customer_name"] = customer_name
        return ChatSession(**active_session)

    session = ChatSession(
        tenant_id=tenant_id,
        customer_wa_id=customer_wa_id,
        customer_name=customer_name,
        status="active",
        mode="ai",
        created_at=now,
        updated_at=now,
    )
    await db.chat_sessions.insert_one(session.model_dump())

    log_session_created(session.session_id, customer_wa_id)
    return session


async def close_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> bool:
    now = datetime.now(timezone.utc)
    result = await db.chat_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "closed", "updated_at": now}},
    )
    if result.modified_count:
        log_session_updated(session_id)
    return result.modified_count > 0
