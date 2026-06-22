from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import TenantNotFoundError
from app.models.tenant import Tenant


async def get_tenant_by_phone_number_id(
    db: AsyncIOMotorDatabase,
    phone_number_id: str,
) -> Tenant:
    doc = await db.tenants.find_one(
        {"whatsapp.phone_number_id": phone_number_id, "status": "active"}
    )
    if not doc:
        raise TenantNotFoundError(phone_number_id)
    return Tenant(**doc)


async def get_tenant_by_id(
    db: AsyncIOMotorDatabase,
    tenant_id: str,
) -> Tenant:
    doc = await db.tenants.find_one({"tenant_id": tenant_id, "status": "active"})
    if not doc:
        raise TenantNotFoundError(tenant_id)
    return Tenant(**doc)
