from ai_agent.model_client import model_looks_incompatible, normalize_provider
from database.config_manager import DEFAULT_CONFIGS, get_admin_configs, get_config
from utils.config_service import get_runtime_bool, get_runtime_config


AI_CONFIG_KEYS = {
    "AI_PROVIDER", "DEFAULT_AI_PROVIDER", "AI_PROVIDER_TOKEN", "AI_MODEL",
    "GROQ_API_KEY", "GROQ_MODEL", "GROQ_INTENT_MODEL", "GROQ_TEMPERATURE", "GROQ_MAX_TOKENS",
    "LOCAL_LLM_URL", "OLLAMA_MODEL", "OLLAMA_TEMPERATURE", "OLLAMA_MAX_TOKENS", "OLLAMA_TIMEOUT",
    "OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_TEMPERATURE", "OPENAI_MAX_TOKENS",
    "USE_LLM_INTENT_PARSER", "INTENT_PARSER_PROVIDER", "INTENT_PARSER_TOKEN", "INTENT_PARSER_MODEL",
    "INTENT_PARSER_TEMPERATURE", "INTENT_PARSER_MAX_TOKENS", "INTENT_PARSER_TIMEOUT",
    "INTENT_PARSER_MIN_CONFIDENCE",
}
GENERAL_CONFIG_KEYS = AI_CONFIG_KEYS | {
    "VERIFY_TOKEN", "FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET", "BUSINESS_DOMAIN",
    "PORT", "FLASK_DEBUG", "MESSAGE_QUEUE_WORKERS",
    "RAG_ENABLED", "RAG_KB_MODE", "RAG_TOP_K", "RAG_MIN_SCORE",
    "AI_SKILL", "DEFAULT_SKILL",
}
SECRET_CONFIG_KEYS = {"GROQ_API_KEY", "OPENAI_API_KEY", "VERIFY_TOKEN", "FACEBOOK_APP_SECRET"}


def normalize_ai_provider(provider):
    return normalize_provider(provider)


def normalize_ai_skill(skill):
    skill = str(skill or "").strip()
    if not skill:
        return "plate_sales"
    legacy = {
        "t_v_n_bi_n_s": "plate_sales",
        "Tư vấn biển số": "plate_sales",
        "Plate Sales": "plate_sales",
        "b_n_h_ng_chung": "sales",
        "Bán hàng chung": "sales",
        "Sales": "sales",
        "Tư vấn bán quần áo": "fashion_sales",
        "Fashion Sales": "fashion_sales",
    }
    if skill in legacy:
        return legacy[skill]
    try:
        from database.skill_manager import get_skill_by_name
        skill_config = get_skill_by_name(skill)
        if skill_config:
            return skill_config.get("skill_id") or skill_config.get("name") or skill
    except Exception:
        pass
    return skill


def get_current_provider():
    return normalize_ai_provider(get_runtime_config("AI_PROVIDER", "ollama"))


def get_current_intent_provider():
    return normalize_ai_provider(get_runtime_config("INTENT_PARSER_PROVIDER", "ollama"))


def get_current_intent_model():
    return get_runtime_config("INTENT_PARSER_MODEL", "")


def get_intent_parser_enabled():
    return get_runtime_bool("USE_LLM_INTENT_PARSER", True)


def get_current_skill():
    return get_runtime_config("AI_SKILL", "plate_sales")


def provider_options():
    return [
        {"id": "groq", "name": "☁️ Groq Cloud"},
        {"id": "ollama", "name": "🦙 Ollama Local"},
        {"id": "openai", "name": "🤖 OpenAI"},
    ]


def get_common_context():
    from database.page_manager import get_all_pages

    current_skill = get_current_skill()
    all_pages = get_all_pages()
    token_preview = "Chưa cấu hình"
    app_id = ""
    app_secret = ""
    if all_pages:
        first_page = all_pages[0]
        token = first_page.get("page_access_token", "")
        if token:
            token_preview = token[:20] + "..."
        app_id = first_page.get("app_id", "")
        app_secret = first_page.get("app_secret", "")

    return {
        "current_skill": current_skill,
        "current_provider": get_current_provider(),
        "current_intent_provider": get_current_intent_provider(),
        "current_intent_model": get_current_intent_model(),
        "intent_parser_enabled": get_intent_parser_enabled(),
        "page_token": token_preview,
        "verify_token": get_runtime_config("VERIFY_TOKEN", "your_verify_token"),
        "app_id": app_id[:10] + "..." if app_id else "Chưa cấu hình",
        "app_secret": app_secret[:10] + "..." if app_secret else "Chưa cấu hình",
        "debug": get_runtime_bool("FLASK_DEBUG", False),
        "all_pages": all_pages,
    }


def _default_for(key):
    return DEFAULT_CONFIGS.get(key, {}).get("value", "")


def _coerce_bool_string(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    return "true" if text in {"1", "true", "yes", "on"} else "false"


def safe_ai_settings(public=True):
    settings = get_admin_configs() if public else {k: get_config(k, _default_for(k)) for k in AI_CONFIG_KEYS}
    for key in AI_CONFIG_KEYS:
        settings.setdefault(key, _default_for(key))
    for key in SECRET_CONFIG_KEYS & AI_CONFIG_KEYS:
        settings.setdefault(f"{key}_SET", bool(get_config(key, "")))
    return settings


def sanitize_ai_config_payload(data, whitelist=AI_CONFIG_KEYS):
    data = data or {}
    updates = {}

    for key, value in data.items():
        if key not in whitelist:
            continue
        if key in {"AI_PROVIDER", "DEFAULT_AI_PROVIDER", "INTENT_PARSER_PROVIDER"}:
            value = normalize_ai_provider(value)
        if key == "USE_LLM_INTENT_PARSER":
            value = _coerce_bool_string(value)
        updates[key] = "" if value is None else str(value).strip()

    if "AI_PROVIDER" in updates:
        updates["DEFAULT_AI_PROVIDER"] = updates["AI_PROVIDER"]

    intent_provider = normalize_ai_provider(
        updates.get("INTENT_PARSER_PROVIDER") or get_runtime_config("INTENT_PARSER_PROVIDER", "ollama")
    )
    intent_model = updates.get("INTENT_PARSER_MODEL")
    if intent_model and model_looks_incompatible(intent_provider, intent_model):
        if intent_provider == "groq":
            updates["INTENT_PARSER_MODEL"] = get_runtime_config("GROQ_INTENT_MODEL", "llama-3.1-8b-instant")
        elif intent_provider == "openai":
            updates["INTENT_PARSER_MODEL"] = get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini")
        elif intent_provider == "ollama":
            updates["INTENT_PARSER_MODEL"] = get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct")

    writer_provider = normalize_ai_provider(updates.get("AI_PROVIDER") or get_runtime_config("AI_PROVIDER", "ollama"))
    writer_key = {"groq": "GROQ_MODEL", "ollama": "OLLAMA_MODEL", "openai": "OPENAI_MODEL"}[writer_provider]
    if "AI_MODEL" in updates and model_looks_incompatible(writer_provider, updates["AI_MODEL"]):
        updates["AI_MODEL"] = {
            "groq": "llama-3.3-70b-versatile",
            "ollama": "qwen3:4b-instruct",
            "openai": "gpt-4.1-mini",
        }[writer_provider]
    if writer_key in updates and model_looks_incompatible(writer_provider, updates[writer_key]):
        updates[writer_key] = {
            "groq": "llama-3.3-70b-versatile",
            "ollama": "qwen3:4b-instruct",
            "openai": "gpt-4.1-mini",
        }[writer_provider]

    return updates
