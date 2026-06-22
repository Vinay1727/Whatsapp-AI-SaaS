from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import APIRouter, Depends, HTTPException, status

from app.db.mongodb import get_db
from app.models.tenant import Tenant, TenantResponse
from app.core.exceptions import TenantNotFoundError

router = APIRouter(prefix="/api/v1/tenants", tags=["tenants"])


@router.get("", response_model=list[TenantResponse])
async def list_tenants(db: AsyncIOMotorDatabase = Depends(get_db)):
    cursor = db.tenants.find(
        {"status": "active"},
        {"name": 1, "slug": 1, "status": 1, "settings": 1,
         "tenant_id": 1, "created_at": 1, "updated_at": 1},
    ).sort("created_at", -1)
    return await cursor.to_list(length=100)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await db.tenants.find_one({"tenant_id": tenant_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(**doc)


@router.get("/lookup/{phone_number_id}", response_model=Tenant)
async def lookup_tenant(
    phone_number_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    doc = await db.tenants.find_one(
        {"whatsapp.phone_number_id": phone_number_id, "status": "active"}
    )
    if not doc:
        raise TenantNotFoundError(phone_number_id)
    return Tenant(**doc)


@router.post("", response_model=Tenant, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant: Tenant,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    existing = await db.tenants.find_one({"slug": tenant.slug})
    if existing:
        raise HTTPException(status_code=409, detail="Tenant with this slug already exists")
    doc = tenant.model_dump()
    await db.tenants.insert_one(doc)
    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    updates: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await db.tenants.find_one_and_update(
        {"tenant_id": tenant_id},
        {"$set": {**updates, "updated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}},
        return_document=True,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantResponse(**result)
