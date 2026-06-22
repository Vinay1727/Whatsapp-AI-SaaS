import logging

import httpx

from app.core.config import settings
from app.services.logger_service import log_message_sent, log_error

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"
HTTP_TIMEOUT_SECONDS = 30.0


class WhatsAppServiceError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class WhatsAppService:
    def __init__(self) -> None:
        self.access_token = settings.whatsapp_access_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.api_base = WHATSAPP_API_BASE

    def _get_credentials(self, phone_number_id: str | None = None, access_token: str | None = None):
        pid = phone_number_id or self.phone_number_id
        token = access_token or self.access_token
        if not token:
            raise WhatsAppServiceError(
                "WHATSAPP_ACCESS_TOKEN is not configured. "
                "Set it in backend/.env or as an environment variable."
            )
        if not pid:
            raise WhatsAppServiceError(
                "WHATSAPP_PHONE_NUMBER_ID is not configured. "
                "Set it in backend/.env or as an environment variable."
            )
        return pid, token

    async def _post(
        self,
        payload: dict,
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        pid, token = self._get_credentials(phone_number_id, access_token)
        url = f"{self.api_base}/{pid}/messages"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code in (200, 201):
                data = response.json()
                wamid = data.get("messages", [{}])[0].get("id", "?")
                logger.info(
                    "WhatsApp API 200 | wamid=%s | to=%s",
                    wamid, payload.get("to", "?"),
                )
                log_message_sent(wamid, payload.get("to", "?"))
                return data

            logger.error(
                "WhatsApp API error [%s] | payload=%s | body=%s",
                response.status_code, payload, response.text,
            )

            try:
                error_body = response.json()
                error_detail = error_body.get("error", {}).get("message", response.text)
            except Exception:
                error_detail = response.text

            raise WhatsAppServiceError(
                message=error_detail,
                status_code=response.status_code,
            )

    async def send_text(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text,
            },
        }
        return await self._post(payload, phone_number_id, access_token)

    async def send_image(
        self,
        to: str,
        image_url: str,
        caption: str = "",
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        if not image_url:
            raise WhatsAppServiceError("image_url is required to send an image.")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"link": image_url},
        }
        if caption:
            payload["image"]["caption"] = caption

        return await self._post(payload, phone_number_id, access_token)

    async def send_document(
        self,
        to: str,
        document_url: str,
        filename: str = "document.pdf",
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        if not document_url:
            raise WhatsAppServiceError("document_url is required to send a document.")

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {
                "link": document_url,
                "filename": filename,
            },
        }
        return await self._post(payload, phone_number_id, access_token)

    async def mark_as_read(
        self,
        message_id: str,
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post(payload, phone_number_id, access_token)

    async def typing_on(
        self,
        to: str,
        phone_number_id: str | None = None,
        access_token: str | None = None,
    ) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "action",
            "action": {"name": "typing_on"},
        }
        return await self._post(payload, phone_number_id, access_token)


whatsapp_service = WhatsAppService()
