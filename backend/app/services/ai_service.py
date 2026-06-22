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


IMAGE_KEYWORDS = {"image", "images", "photo", "photos", "picture", "pictures", "pic", "pics", "design", "designs"}
CATALOG_KEYWORDS = {"catalog", "catalogue", "brochure", "pdf", "document", "price list", "company profile"}
REQUEST_WORDS = {"show", "send", "share", "see", "view", "display", "look", "want", "give", "need"}


def _keyword_preclassify(message: str) -> dict | None:
    """Quick keyword check to catch obvious media requests."""
    msg_lower = message.lower().strip()
    words = set(msg_lower.split())

    wants_image = bool(words & IMAGE_KEYWORDS) and bool(words & REQUEST_WORDS)
    if wants_image:
        return {"intent": "image_request", "source": "keyword"}

    has_catalog = any(kw in msg_lower for kw in CATALOG_KEYWORDS)
    if has_catalog:
        return {"intent": "catalog_request", "source": "keyword"}

    return None


def _extract_product_from_message(message: str, intent: str) -> str:
    """Naively extract a likely product name for keyword-based intent."""
    msg_lower = message.lower().strip()
    stopwords = IMAGE_KEYWORDS | CATALOG_KEYWORDS | REQUEST_WORDS | \
        {"me", "a", "an", "the", "some", "please", "can", "you", "your", "i", "my", "of", "for", "and", "to", "in", "is", "it", "that", "this", "with", "at", "on"}
    words = [w for w in msg_lower.split() if w not in stopwords and len(w) > 2]
    return " ".join(words[:2]) if words else ""


async def detect_intent(message: str, tenant: Tenant) -> dict:
    keyword_hint = _keyword_preclassify(message)
    if keyword_hint and not settings.groq_api_key:
        product = _extract_product_from_message(message, keyword_hint["intent"])
        logger.info("[INTENT_KEYWORD_FALLBACK] intent=%s product=%s", keyword_hint["intent"], product)
        return {"intent": keyword_hint["intent"], "product": product}

    key = settings.groq_api_key
    if not key:
        logger.warning("[INTENT] No Groq API key — skipping intent detection")
        return {"intent": "general_chat", "product": ""}

    client = AsyncOpenAI(api_key=key, base_url=GROQ_BASE_URL)
    product_hints = _build_product_hints(tenant)
    hint_note = ""
    if keyword_hint:
        hint_note = f"\nNote: This message may be a {keyword_hint['intent']} — confirm or override."

    system_prompt = (
        "You are an intent classifier for a business WhatsApp assistant."
        f"{product_hints}\n{hint_note}\n\n"
        "Classify the user's message into one of these intents:\n"
        "- image_request: User asks to SEE or RECEIVE pictures of products. "
        "Trigger words: image, images, photo, photos, picture, pictures, pic, pics, design, designs "
        "combined with show, send, share, see, view\n"
        "- catalog_request: User asks for a catalog, brochure, price list, or company document. "
        "Trigger words: catalog, catalogue, brochure, pdf, document, price list, company profile\n"
        "- product_question: User asks about product details, features, materials, or availability\n"
        "- pricing_question: User asks about prices, costs, rates, or fees\n"
        "- general_chat: Everything else — greetings, small talk, thanks, help, complaints\n\n"
        "Examples:\n"
        '- "show me sofa pictures" → image_request, product=sofa\n'
        '- "send me some catalogue" → catalog_request, product=\n'
        '- "can you send sofa photos" → image_request, product=sofa\n'
        '- "share furniture brochure" → catalog_request, product=furniture\n'
        '- "i want to see sofa designs" → image_request, product=sofa\n'
        '- "do you have a company profile" → catalog_request, product=\n'
        '- "send product images" → image_request, product=\n'
        '- "how much is this sofa" → pricing_question, product=sofa\n'
        '- "what material is this made of" → product_question, product=\n'
        '- "hello" → general_chat, product=\n'
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
            max_tokens=100,
        )
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        result = json.loads(content)
        intent_val = result.get("intent", "")
        valid = ("image_request", "catalog_request", "product_question", "pricing_question", "general_chat")
        if intent_val not in valid:
            logger.warning("[INTENT_INVALID] message=%s response=%s", message, content)
            if keyword_hint:
                product = _extract_product_from_message(message, keyword_hint["intent"])
                logger.info("[INTENT_KEYWORD_OVERRIDE] intent=%s product=%s", keyword_hint["intent"], product)
                return {"intent": keyword_hint["intent"], "product": product}
            return {"intent": "general_chat", "product": ""}
        product = result.get("product", "") or ""
        return {"intent": intent_val, "product": product}
    except json.JSONDecodeError:
        logger.warning("[INTENT_PARSE_FAIL] message=%s raw=%s", message, content if 'content' in dir() else "N/A")
        if keyword_hint:
            product = _extract_product_from_message(message, keyword_hint["intent"])
            logger.info("[INTENT_KEYWORD_OVERRIDE] intent=%s product=%s", keyword_hint["intent"], product)
            return {"intent": keyword_hint["intent"], "product": product}
        return {"intent": "general_chat", "product": ""}
    except Exception:
        logger.warning("[INTENT_API_FAIL] message=%s", message, exc_info=True)
        if keyword_hint:
            product = _extract_product_from_message(message, keyword_hint["intent"])
            logger.info("[INTENT_KEYWORD_OVERRIDE] intent=%s product=%s", keyword_hint["intent"], product)
            return {"intent": keyword_hint["intent"], "product": product}
        return {"intent": "general_chat", "product": ""}
