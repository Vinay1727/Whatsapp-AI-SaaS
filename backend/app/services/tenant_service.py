import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import TenantNotFoundError
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


async def get_tenant_by_phone_number_id(
    db: AsyncIOMotorDatabase,
    phone_number_id: str,
) -> Tenant:
    logger.info(
        "[TENANT_LOOKUP] phone_number_id=%r type=%s len=%d",
        phone_number_id, type(phone_number_id).__name__,
        len(phone_number_id) if isinstance(phone_number_id, str) else -1,
    )

    doc = await db.tenants.find_one(
        {"whatsapp.phone_number_id": phone_number_id, "status": "active"}
    )
    if not doc:
        pipeline = [
            {"$match": {"status": "active"}},
            {"$project": {
                "tenant_id": 1,
                "pnid": "$whatsapp.phone_number_id",
                "pnid_type": {"$type": "$whatsapp.phone_number_id"},
            }}
        ]
        type_check = await db.tenants.aggregate(pipeline).to_list(length=10)
        logger.error(
            "[TENANT_LOOKUP_MISS] queried=%r active_tenants=%s",
            phone_number_id, type_check,
        )

        alt_doc = await db.tenants.find_one({
            "$expr": {"$eq": [{"$toString": "$whatsapp.phone_number_id"}, phone_number_id]},
            "status": "active",
        })
        if alt_doc:
            logger.error(
                "[TENANT_LOOKUP_TYPE_MISMATCH] found via $toString! "
                "phone_number_id=%r stored_doc=%s",
                phone_number_id, alt_doc,
            )

        raise TenantNotFoundError(phone_number_id)

    logger.info(
        "[TENANT_LOOKUP_HIT] phone_number_id=%s tenant_id=%s",
        phone_number_id, doc.get("tenant_id"),
    )
    return Tenant(**doc)


async def get_tenant_by_id(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> Tenant:
    doc = await db.tenants.find_one({"tenant_id": tenant_id, "status": "active"})
    if not doc:
        raise TenantNotFoundError(tenant_id)
    return Tenant(**doc)
