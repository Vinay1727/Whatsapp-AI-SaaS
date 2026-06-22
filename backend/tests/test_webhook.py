import hashlib
import hmac
import json

import pytest
from httpx import AsyncClient, ASGITransport

from app.core.config import settings
from app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _sign_body(body: dict) -> str:
    raw = json.dumps(body).encode()
    sig = hmac.new(
        settings.meta_app_secret.encode("utf-8"),
        raw,
        hashlib.sha256,
    ).hexdigest()
    return f"sha256={sig}"


def _build_whatsapp_payload(
    phone_number_id: str = "123456789",
    from_number: str = "919999999999",
    sender_name: str = "Test User",
    msg_type: str = "text",
    msg_body: str = "Hello",
):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "phone_number_id": phone_number_id,
                                "display_phone_number": "15550471234",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": sender_name},
                                    "wa_id": from_number,
                                }
                            ],
                            "messages": [
                                {
                                    "from": from_number,
                                    "id": f"wamid.test.{phone_number_id}",
                                    "timestamp": "1712345678",
                                    "type": msg_type,
                                    "text": {"body": msg_body},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    return payload


@pytest.mark.asyncio
async def test_webhook_verify_get(client):
    """Test webhook verification (GET) - Meta's challenge"""
    response = await client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.webhook_verify_token,
            "hub.challenge": "123456789",
        },
    )
    assert response.status_code == 200
    assert response.text == "123456789"


@pytest.mark.asyncio
async def test_webhook_verify_fail(client):
    """Test webhook verification with wrong token"""
    response = await client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "123456789",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_webhook_receive_text(client):
    """Test receiving a text message webhook"""
    payload = _build_whatsapp_payload(
        phone_number_id="123456789",
        from_number="919999999999",
        sender_name="Test User",
        msg_type="text",
        msg_body="Hello",
    )
    signature = _sign_body(payload)

    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"x-hub-signature-256": signature},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["processed"] >= 1


@pytest.mark.asyncio
async def test_webhook_receive_unknown_tenant(client):
    """Test webhook from unknown phone_number_id"""
    payload = _build_whatsapp_payload(
        phone_number_id="unknown_phone_id",
        from_number="919999999999",
        sender_name="Test",
        msg_type="text",
        msg_body="Hello",
    )
    signature = _sign_body(payload)

    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"x-hub-signature-256": signature},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["processed"] == 1
    assert "error" in data["results"][0]


@pytest.mark.asyncio
async def test_webhook_receive_invalid_signature(client):
    """Test webhook with invalid signature"""
    payload = _build_whatsapp_payload()
    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"x-hub-signature-256": "sha256=invalidsignature"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_webhook_receive_non_whatsapp(client):
    """Test webhook with non-whatsapp event"""
    payload = {
        "object": "not_whatsapp",
        "entry": [],
    }
    signature = _sign_body(payload)
    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"x-hub-signature-256": signature},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}


@pytest.mark.asyncio
async def test_webhook_receive_image(client):
    """Test receiving an image webhook"""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "phone_number_id": "123456789",
                                "display_phone_number": "15550471234",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Test User"},
                                    "wa_id": "919999999999",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "919999999999",
                                    "id": "wamid.test.image.001",
                                    "timestamp": "1712345678",
                                    "type": "image",
                                    "image": {
                                        "id": "media_id_001",
                                        "mime_type": "image/jpeg",
                                        "sha256": "abc123",
                                        "caption": "Test image",
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    signature = _sign_body(payload)
    response = await client.post(
        "/api/v1/webhook",
        json=payload,
        headers={"x-hub-signature-256": signature},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["processed"] == 1


@pytest.mark.asyncio
async def test_webhook_simulation_endpoint(client):
    """Test the webhook simulation endpoint"""
    payload = {
        "phone_number_id": "123456789",
        "from_number": "+919999999999",
        "sender_name": "Test User",
        "message_type": "text",
        "message_body": "Hello, this is a test",
    }
    response = await client.post("/api/v1/test/webhook-simulation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["tenant_name"] == "Furniture Store"
    assert len(data["session_id"]) > 0
    assert len(data["message_id"]) > 0
