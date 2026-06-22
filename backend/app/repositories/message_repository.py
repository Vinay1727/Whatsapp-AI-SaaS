import logging
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


async def update_message_status(
    db: AsyncIOMotorDatabase,
    whatsapp_message_id: str,
    status: str,
    status_timestamp: str | None = None,
) -> bool:
    now = datetime.now(timezone.utc)
    update = {
        "whatsapp_status": status,
        "updated_at": now,
    }
    if status_timestamp is not None:
        update["status_timestamp"] = status_timestamp

    result = await db.messages.update_one(
        {"whatsapp_message_id": whatsapp_message_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        logger.warning(
            "[MESSAGE_STATUS_SKIP] wamid=%s status=%s reason=not_found",
            whatsapp_message_id, status,
        )
        return False
    return True
