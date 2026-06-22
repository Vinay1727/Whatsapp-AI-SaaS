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
