import logging

logger = logging.getLogger("whatsapp_saas")


def log_webhook_received(payload_size: int, num_entries: int = 0):
    logger.info("[WEBHOOK_RECEIVED] payload_size=%d entries=%d", payload_size, num_entries)


def log_tenant_identified(phone_number_id: str, tenant_id: str, tenant_name: str):
    logger.info(
        "[TENANT_IDENTIFIED] phone_number_id=%s tenant_id=%s name=%s",
        phone_number_id, tenant_id, tenant_name,
    )


def log_session_created(session_id: str, customer_wa_id: str):
    logger.info("[SESSION_CREATED] session_id=%s customer=%s", session_id, customer_wa_id)


def log_session_updated(session_id: str):
    logger.info("[SESSION_UPDATED] session_id=%s", session_id)


def log_message_saved(whatsapp_message_id: str, direction: str, message_type: str):
    logger.info(
        "[MESSAGE_SAVED] wamid=%s direction=%s type=%s",
        whatsapp_message_id, direction, message_type,
    )


def log_ai_response_generated(session_id: str, model: str, completion_tokens: int):
    logger.info(
        "[AI_RESPONSE_GENERATED] session_id=%s model=%s tokens=%d",
        session_id, model, completion_tokens,
    )


def log_message_sent(whatsapp_message_id: str, to: str):
    logger.info("[MESSAGE_SENT] wamid=%s to=%s", whatsapp_message_id, to)


def log_error(context: str, detail: str):
    logger.error("[ERROR] context=%s detail=%s", context, detail)
