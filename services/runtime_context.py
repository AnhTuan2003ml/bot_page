from typing import Any, Dict, Optional

from services import cache_service
from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int
from utils.logger import debug

PAGE_TTL_SECONDS = 120
EXPERTISE_TTL_SECONDS = 300
RUNTIME_TTL_SECONDS = 300
APP_SECRET_TTL_SECONDS = 180


def _page_cache_key(page_id: str) -> str:
    return f"page:{page_id}"

def _expertise_cache_key(expertise_id: str) -> str:
    return f"expertise:{expertise_id}"

def _runtime_cache_key(key: str) -> str:
    return f"runtime_config:{key}"

def _app_secret_cache_key() -> str:
    return "app_secret:list"


def get_cached_runtime_config(key: str, default: Any = None, page_config: Optional[Dict] = None) -> Any:
    if page_config:
        value = get_runtime_config(key, None, page_config)
        if value not in (None, ""):
            return value
    return cache_service.get_or_set(_runtime_cache_key(key), lambda: get_runtime_config(key, default), RUNTIME_TTL_SECONDS)


def get_cached_page(page_id: Optional[str]) -> Dict:
    if not page_id:
        return {}
    def _load():
        from database.page_manager import get_page
        return get_page(str(page_id)) or {}
    return cache_service.get_or_set(_page_cache_key(str(page_id)), _load, PAGE_TTL_SECONDS) or {}


def get_cached_app_secrets() -> list:
    def _load():
        from database.page_manager import get_all_pages
        secrets, seen = [], set()
        for page in get_all_pages():
            secret = (page.get("app_secret") or "").strip()
            if secret and secret not in seen:
                secrets.append(secret); seen.add(secret)
        return secrets
    return cache_service.get_or_set(_app_secret_cache_key(), _load, APP_SECRET_TTL_SECONDS) or []


def get_cached_expertise(expertise_key: Optional[str]) -> Dict:
    if not expertise_key:
        return {}
    def _load():
        from database.expertise_manager import get_expertise
        return get_expertise(expertise_key) or {}
    return cache_service.get_or_set(_expertise_cache_key(str(expertise_key)), _load, EXPERTISE_TTL_SECONDS) or {}


def get_cached_skill(skill_name: Optional[str]) -> Dict:
    # Compatibility for existing page service/dropdowns. It now resolves Chuyên môn AI.
    return get_cached_expertise(skill_name)


def get_cached_skill_fields(skill_name: Optional[str]) -> list:
    exp = get_cached_expertise(skill_name)
    if not exp:
        return []
    import json
    try:
        fields = json.loads(exp.get("data_fields_json") or "[]")
    except Exception:
        fields = []
    return fields if isinstance(fields, list) else []


def _provider_default_model(provider: str, role: str = "writer") -> str:
    provider = (provider or "").strip().lower()
    if role == "intent" and provider == "groq":
        return str(get_cached_runtime_config("GROQ_INTENT_MODEL", "llama-3.1-8b-instant") or "")
    if provider == "groq":
        return str(get_cached_runtime_config("GROQ_MODEL", "llama-3.3-70b-versatile") or "")
    if provider == "openai":
        return str(get_cached_runtime_config("OPENAI_MODEL", "gpt-4.1-mini") or "")
    return str(get_cached_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct") or "")


def _cached_int(key: str, default: int) -> int:
    try:
        return int(get_cached_runtime_config(key, default))
    except (TypeError, ValueError):
        return default


def _cached_float(key: str, default: float) -> float:
    try:
        return float(get_cached_runtime_config(key, default))
    except (TypeError, ValueError):
        return default


def build_runtime_context(page: Optional[Dict] = None, page_id: Optional[str] = None, sender_psid: Optional[str] = None) -> Dict:
    page = dict(page or {})
    page_id = str(page_id or page.get("page_id") or "default_page")
    if not page and page_id != "default_page":
        page = dict(get_cached_page(page_id) or {})

    # IMPORTANT: keep Page schema/logic unchanged. Existing pages.ai_skill now points to Chuyên môn AI.
    expertise_key = page.get("ai_skill") or ""
    expertise = get_cached_expertise(expertise_key) if expertise_key else {}

    ai_provider = page.get("ai_provider") or get_cached_runtime_config("AI_PROVIDER", "ollama")
    ai_model = page.get("ai_model") or _provider_default_model(ai_provider, "writer")
    intent_provider = page.get("intent_parser_provider") or get_cached_runtime_config("INTENT_PARSER_PROVIDER", "ollama")
    intent_model = page.get("intent_parser_model") or _provider_default_model(intent_provider, "intent")

    context = {
        "page": page,
        "page_id": page_id,
        "page_name": page.get("page_name", "Unknown"),
        "page_access_token": page.get("page_access_token") or "",
        "ai_skill": expertise_key,
        "skill": expertise_key,
        "expertise_id": expertise.get("id"),
        "expertise": expertise,
        "skill_config": expertise,
        "persona_json": expertise.get("persona_json") or "{}",
        "training_content": expertise.get("training_content") or "",
        "data_table": expertise.get("data_table") or "",
        "data_fields_json": expertise.get("data_fields_json") or "[]",
        "ai_provider": ai_provider,
        "ai_model": ai_model,
        "ai_provider_token": page.get("ai_provider_token") or "",
        "intent_parser_provider": intent_provider,
        "intent_parser_model": intent_model,
        "intent_parser_token": page.get("intent_parser_token") or "",
        "use_llm_intent_parser": page.get("use_llm_intent_parser") or "",
        "groq_temperature": _cached_float("GROQ_TEMPERATURE", 0.25),
        "groq_max_tokens": _cached_int("GROQ_MAX_TOKENS", 300),
        "ollama_temperature": _cached_float("OLLAMA_TEMPERATURE", 0.25),
        "ollama_max_tokens": _cached_int("OLLAMA_MAX_TOKENS", 300),
        "ollama_timeout": _cached_int("OLLAMA_TIMEOUT", 60),
        "openai_temperature": _cached_float("OPENAI_TEMPERATURE", 0.25),
        "openai_max_tokens": _cached_int("OPENAI_MAX_TOKENS", 300),
        "sender_psid": sender_psid,
    }
    debug(f"[RUNTIME_CONTEXT] page_id={page_id} expertise_key={expertise_key} expertise_id={expertise.get('id')} data_table={expertise.get('data_table') or ''}")
    return context


def clear_page_context(page_id: Optional[str] = None) -> None:
    if page_id:
        cache_service.delete(_page_cache_key(str(page_id)))
    else:
        cache_service.delete_prefix("page:")
    clear_app_secret_context()


def clear_skill_context(skill_name: Optional[str] = None) -> None:
    if skill_name:
        cache_service.delete(_expertise_cache_key(str(skill_name)))
    else:
        cache_service.delete_prefix("expertise:")


def clear_runtime_config_context(key: Optional[str] = None) -> None:
    if key:
        cache_service.delete(_runtime_cache_key(str(key)))
    else:
        cache_service.delete_prefix("runtime_config:")
    if key in (None, "FACEBOOK_APP_SECRET"):
        clear_app_secret_context()


def clear_inventory_context() -> None:
    cache_service.delete_prefix("inventory:")
    cache_service.delete_prefix("data_table:")


def clear_app_secret_context() -> None:
    cache_service.delete(_app_secret_cache_key())
