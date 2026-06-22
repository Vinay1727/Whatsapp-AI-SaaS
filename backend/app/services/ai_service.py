import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.core.exceptions import AIServiceError
from app.models.tenant import Tenant
from app.services.logger_service import log_ai_response_generated, log_error

logger = logging.getLogger(__name__)

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def _get_provider() -> str:
    return (settings.ai_provider or "openai").lower().strip()


def _build_client(api_key: str | None = None) -> AsyncOpenAI:
    provider = _get_provider()

    if provider == "groq":
        key = api_key or settings.groq_api_key
        if not key:
            raise AIServiceError(
                "Groq API key not configured. Set GROQ_API_KEY in .env "
                "or provide a tenant-level key."
            )
        logger.info("[AI_PROVIDER] provider=groq base_url=%s", GROQ_BASE_URL)
        return AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)

    key = api_key or settings.openai_api_key
    if not key:
        raise AIServiceError(
            "OpenAI API key not configured. Set OPENAI_API_KEY in .env "
            "or provide a tenant-level key."
        )
    logger.info("[AI_PROVIDER] provider=openai")
    return AsyncOpenAI(api_key=key)


def _build_tenant_prompt(tenant: Tenant) -> str:
    if tenant.ai_config and tenant.ai_config.system_prompt:
        return tenant.ai_config.system_prompt

    business_name = (
        tenant.settings.business_name
        or tenant.name
        or "our business"
    )

    prompt = (
        f"You are the official virtual assistant for {business_name}. "
        f"You represent {business_name} and nothing else. "
        f"Your entire identity is that of a {business_name} representative. "
        f"Help customers with products, services, orders, pricing, and inquiries. "
        f"Welcome customers to {business_name} warmly. "
        f"When asked who you are, say: \"I am the virtual assistant for {business_name}.\" "
        f"You are NOT a language model. You are NOT an AI. "
        f"You are a {business_name} representative. "
        f"Never mention OpenAI, Groq, language models, or artificial intelligence. "
        f"Never say you are an AI assistant or large language model. "
        f"Be helpful, professional, and friendly."
    )
    return prompt


def _build_messages(
    system_prompt: str,
    conversation_history: list[dict],
    user_message: str,
) -> list[dict]:
    messages = [{"role": "system", "content": system_prompt}]
    for msg in conversation_history[-10:]:
        role = "assistant" if msg.get("direction") == "outgoing" else "user"
        text = msg.get("message_text") or ""
        if text:
            messages.append({"role": role, "content": text})
    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_ai_reply(
    tenant: Tenant,
    user_message: str,
    conversation_history: list[dict] | None = None,
) -> str:
    api_key = tenant.ai_config.openai_api_key if tenant.ai_config and tenant.ai_config.openai_api_key else None
    client = _build_client(api_key)

    provider = _get_provider()
    default_model = settings.groq_default_model if provider == "groq" else settings.openai_default_model

    model = tenant.ai_config.model if tenant.ai_config else default_model
    if provider == "groq" and model == settings.openai_default_model:
        model = settings.groq_default_model
    temperature = tenant.ai_config.temperature if tenant.ai_config else settings.openai_temperature
    max_tokens = tenant.ai_config.max_tokens if tenant.ai_config else settings.openai_max_tokens

    system_prompt = _build_tenant_prompt(tenant)
    business_name = tenant.settings.business_name or tenant.name or "unknown"
    logger.info(
        "[AI_CONTEXT] tenant_id=%s business=%s",
        tenant.tenant_id, business_name,
    )
    logger.info(
        "[AI_SYSTEM_PROMPT] prompt_length=%d",
        len(system_prompt),
    )

    messages = _build_messages(system_prompt, conversation_history or [], user_message)

    logger.info("[AI_REQUEST] provider=%s model=%s", provider, model)
    logger.info("[AI_SYSTEM_PROMPT_CONTENT] %s", system_prompt)

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        reply = response.choices[0].message.content or ""
        usage = response.usage
        tokens_used = usage.total_tokens if usage else 0

        logger.info(
            "[AI_RESPONSE] provider=%s model=%s tokens=%d success=true",
            provider, model, tokens_used,
        )

        log_ai_response_generated(
            session_id="",
            model=model,
            completion_tokens=tokens_used,
        )
        return reply
    except Exception as e:
        logger.error("[AI_ERROR] provider=%s model=%s error=%s", provider, model, str(e))
        log_error("AI_SERVICE", str(e))
        raise AIServiceError(detail=f"AI API error: {str(e)}")


INTENT_MODEL = "llama3-8b-8192"


def _build_product_hints(tenant: Tenant) -> str:
    seen = set()
    hints = []
    for item in tenant.media_library:
        for tag in item.tags:
            if tag and tag not in seen:
                hints.append(tag)
                seen.add(tag)
        if item.caption and item.caption not in seen:
            hints.append(item.caption)
            seen.add(item.caption)
    if not hints:
        return ""
    return f"\nBusiness product catalog: {', '.join(hints)}"


async def detect_intent(message: str, tenant: Tenant) -> dict:
    key = settings.groq_api_key
    if not key:
        logger.warning("[INTENT] No Groq API key — skipping intent detection")
        return {"intent": "general_chat", "product": ""}

    client = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
    product_hints = _build_product_hints(tenant)

    system_prompt = (
        "You are an intent classifier for a business WhatsApp assistant."
        f"{product_hints}\n\n"
        "Classify the user's message into one of these intents:\n"
        "- image_request: User wants to SEE pictures/photos/images of products\n"
        "- catalog_request: User wants a catalog, brochure, price list (document/PDF)\n"
        "- product_question: User asks about product details, features, or availability\n"
        "- pricing_question: User asks about prices or costs\n"
        "- general_chat: Everything else (greetings, small talk, help, etc.)\n\n"
        "Return ONLY valid JSON. No markdown, no explanation:\n"
        '{"intent": "<intent>", "product": "<specific product name or empty string>"}\n'
        "The product field must be the exact product name the user is asking about."
    )

    try:
        response = await client.chat.completions.create(
            model=INTENT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0,
            max_tokens=80,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        intent_val = result.get("intent", "")
        valid = ("image_request", "catalog_request", "product_question", "pricing_question", "general_chat")
        if intent_val not in valid:
            return {"intent": "general_chat", "product": ""}
        return {
            "intent": intent_val,
            "product": result.get("product", "") or "",
        }
    except Exception:
        logger.warning("[INTENT_PARSE_FAIL] message=%s", message, exc_info=True)
        return {"intent": "general_chat", "product": ""}
