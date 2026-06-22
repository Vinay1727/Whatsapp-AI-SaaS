"""
Run: python -m migrations.create_indexes

Creates all required indexes for Phase 1-3 collections.
Safe to run multiple times — create_indexes() is idempotent.
"""
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings


async def create_indexes():
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]

    # --- tenants ---
    await db.tenants.create_index("tenant_id", unique=True)
    await db.tenants.create_index("slug", unique=True)
    await db.tenants.create_index("whatsapp.phone_number_id")
    await db.tenants.create_index(
        [("status", 1), ("whatsapp.phone_number_id", 1)],
        partialFilterExpression={"status": "active"},
    )

    # --- chat_sessions ---
    await db.chat_sessions.create_index("session_id", unique=True)
    await db.chat_sessions.create_index([("tenant_id", 1), ("status", 1), ("updated_at", -1)])
    await db.chat_sessions.create_index([("tenant_id", 1), ("customer_wa_id", 1), ("status", 1)])
    await db.chat_sessions.create_index(
        [("tenant_id", 1), ("escalation.is_escalated", 1), ("updated_at", -1)]
    )

    # --- messages ---
    await db.messages.create_index("message_id", unique=True)
    await db.messages.create_index([("session_id", 1), ("created_at", 1)])
    await db.messages.create_index([("tenant_id", 1), ("session_id", 1), ("created_at", -1)])
    await db.messages.create_index(
        "whatsapp_message_id",
        unique=True,
        sparse=True,
    )
    await db.messages.create_index([("session_id", 1), ("direction", 1), ("created_at", -1)])
    await db.messages.create_index([("sender_number", 1), ("created_at", -1)])

    print("All indexes created successfully.")
    client.close()


if __name__ == "__main__":
    asyncio.run(create_indexes())
