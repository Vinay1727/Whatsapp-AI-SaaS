"""
Run: python -m migrations.seed_tenants

Inserts sample tenant data for development.
Safe to run multiple times — uses upsert on slug.
"""
import asyncio

from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings
from app.models.tenant import Tenant

SEED_TENANTS = [
    Tenant(
        name="Furniture Store",
        slug="furniture-store",
        whatsapp={
            "phone_number_id": "123456789",
            "business_account_id": "ba_furniture_001",
            "access_token": "EAAT...furniture_dev_token",
            "webhook_secret": "whsec_furniture_dev",
            "api_version": "v21.0",
        },
        ai_config={
            "system_prompt": (
                "You are a friendly and knowledgeable sales assistant for a furniture store. "
                "You help customers with product inquiries, order status, delivery scheduling, "
                "and interior design advice. You know our catalog includes sofas, tables, chairs, "
                "beds, cabinets, and home decor. Always be helpful and suggest relevant products. "
                "If a customer is unhappy, apologize and offer a solution. "
                "If they ask for a human, transfer them immediately."
            ),
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1024,
            "confidence_threshold": 0.8,
            "human_handover_threshold": 0.6,
        },
        settings={
            "timezone": "America/New_York",
            "business_name": "Furniture Store",
        },
        media_library=[
            {
                "media_id": "media_sofa_001",
                "type": "image",
                "url": "https://storage.example.com/furniture/sofa-collection.jpg",
                "caption": "Modern Sofa Collection — 40% off this weekend",
                "tags": ["sofa", "promo", "summer"],
                "active": True,
            },
            {
                "media_id": "media_table_001",
                "type": "image",
                "url": "https://storage.example.com/furniture/dining-table-set.jpg",
                "caption": "Oak Dining Table Set — seats 6",
                "tags": ["table", "dining"],
                "active": True,
            },
            {
                "media_id": "media_catalog_001",
                "type": "document",
                "url": "https://storage.example.com/furniture/catalog-2026.pdf",
                "caption": "Full Product Catalog 2026",
                "tags": ["catalog"],
                "active": True,
            },
        ],
    ),
    Tenant(
        name="Car Service Center",
        slug="car-service-center",
        whatsapp={
            "phone_number_id": "987654321",
            "business_account_id": "ba_car_001",
            "access_token": "EAAT...car_dev_token",
            "webhook_secret": "whsec_car_dev",
            "api_version": "v21.0",
        },
        ai_config={
            "system_prompt": (
                "You are a professional automotive service advisor for a car service center. "
                "You help customers book service appointments, check repair status, "
                "provide maintenance tips, and explain service packages. "
                "Services offered: oil change, tire rotation, brake inspection, AC repair, "
                "engine diagnostics, and annual maintenance. "
                "Always confirm vehicle make, model, and year before booking. "
                "Be clear about pricing and estimated completion times. "
                "If a customer is frustrated about a repair, be empathetic and escalate to a human."
            ),
            "model": "gpt-4o",
            "temperature": 0.6,
            "max_tokens": 1024,
            "confidence_threshold": 0.85,
            "human_handover_threshold": 0.65,
        },
        settings={
            "timezone": "America/Chicago",
            "business_name": "Car Service Center",
        },
        media_library=[
            {
                "media_id": "media_service_pkg_001",
                "type": "image",
                "url": "https://storage.example.com/car/service-packages.jpg",
                "caption": "Our Service Packages — Oil Change starting at $39.99",
                "tags": ["service", "promo"],
                "active": True,
            },
            {
                "media_id": "media_tips_001",
                "type": "document",
                "url": "https://storage.example.com/car/maintenance-tips.pdf",
                "caption": "10 Essential Car Maintenance Tips",
                "tags": ["tips", "educational"],
                "active": True,
            },
        ],
    ),
    Tenant(
        name="Mobile Store",
        slug="mobile-store",
        whatsapp={
            "phone_number_id": "5551234567",
            "business_account_id": "ba_mobile_001",
            "access_token": "EAAT...mobile_dev_token",
            "webhook_secret": "whsec_mobile_dev",
            "api_version": "v21.0",
        },
        ai_config={
            "system_prompt": (
                "You are a tech-savvy sales assistant for a mobile phone store. "
                "You help customers choose the right smartphone, compare models, "
                "check stock availability, provide pricing, and assist with trade-ins. "
                "Current top models: iPhone 16 Pro, Samsung Galaxy S26, Google Pixel 10, "
                "OnePlus 13. You know specs, prices, and promotions. "
                "You can also help with plan selection (prepaid, postpaid, family plans). "
                "Be enthusiastic and helpful. If a customer reports a defective device, "
                "apologize and explain our return policy, then offer to connect them with support."
            ),
            "model": "gpt-4o",
            "temperature": 0.75,
            "max_tokens": 1024,
            "confidence_threshold": 0.8,
            "human_handover_threshold": 0.6,
        },
        settings={
            "timezone": "America/Los_Angeles",
            "business_name": "Mobile Store",
        },
        media_library=[
            {
                "media_id": "media_iphone_001",
                "type": "image",
                "url": "https://storage.example.com/mobile/iphone-16-pro.jpg",
                "caption": "iPhone 16 Pro — starting at $999",
                "tags": ["iphone", "apple", "flagship"],
                "active": True,
            },
            {
                "media_id": "media_samsung_001",
                "type": "image",
                "url": "https://storage.example.com/mobile/galaxy-s26.jpg",
                "caption": "Samsung Galaxy S26 — pre-order now and save $200",
                "tags": ["samsung", "android", "flagship"],
                "active": True,
            },
            {
                "media_id": "media_accessories_001",
                "type": "image",
                "url": "https://storage.example.com/mobile/accessories-bundle.jpg",
                "caption": "Accessory Bundle — case, screen protector, charger",
                "tags": ["accessories", "bundle"],
                "active": True,
            },
            {
                "media_id": "media_tradein_001",
                "type": "document",
                "url": "https://storage.example.com/mobile/trade-in-program.pdf",
                "caption": "Trade-In Program — Get up to $600 off your next phone",
                "tags": ["trade-in", "promo"],
                "active": True,
            },
        ],
    ),
]


async def seed():
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.mongodb_db_name]

    for tenant in SEED_TENANTS:
        doc = tenant.model_dump()
        result = await db.tenants.update_one(
            {"slug": tenant.slug},
            {"$setOnInsert": doc},
            upsert=True,
        )
        if result.upserted_id:
            print(f"  Created: {tenant.name} ({tenant.slug})")
        else:
            print(f"  Already exists: {tenant.name} ({tenant.slug})")

    print(f"\nSeeded {len(SEED_TENANTS)} tenants.")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
