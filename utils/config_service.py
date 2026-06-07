import threading
import time

from database.config_manager import DEFAULT_CONFIGS, get_configs, set_config, set_configs


_CONFIG_CACHE = {}
_CONFIG_META = {}
_CONFIG_CACHE_LOADED = False
_CONFIG_CACHE_UPDATED_AT = 0
_CONFIG_CACHE_TTL_SECONDS = 300
_CONFIG_LOCK = threading.RLock()


PAGE_CONFIG_MAP = {
    "AI_PROVIDER": "ai_provider",
    "AI_MODEL": "ai_model",
    "AI_PROVIDER_TOKEN": "ai_provider_token",
    "BUSINESS_DOMAIN": "business_domain",
    "INTENT_PARSER_PROVIDER": "intent_parser_provider",
    "INTENT_PARSER_MODEL": "intent_parser_model",
    "INTENT_PARSER_TOKEN": "intent_parser_token",
    "USE_LLM_INTENT_PARSER": "use_llm_intent_parser",
    "RAG_ENABLED": "rag_enabled",
}


def load_config_cache(force: bool = False):
    global _CONFIG_CACHE_LOADED, _CONFIG_CACHE_UPDATED_AT
    with _CONFIG_LOCK:
        now = time.time()
        fresh = _CONFIG_CACHE_LOADED and (now - _CONFIG_CACHE_UPDATED_AT) < _CONFIG_CACHE_TTL_SECONDS
        if fresh and not force:
            return _CONFIG_CACHE

        configs = get_configs(include_secret=True)
        _CONFIG_CACHE.clear()
        _CONFIG_META.clear()
        for key, meta in configs.items():
            _CONFIG_CACHE[key] = "" if meta.get("value") is None else str(meta.get("value"))
            _CONFIG_META[key] = {
                "value_type": meta.get("value_type") or "string",
                "is_secret": bool(meta.get("is_secret")),
            }
        _CONFIG_CACHE_LOADED = True
        _CONFIG_CACHE_UPDATED_AT = now
        print(f"[CONFIG_CACHE] loaded count={len(_CONFIG_CACHE)}")
        return _CONFIG_CACHE


def get_cached_config(key, default=None):
    cache = load_config_cache()
    return cache.get(key, default)


def clear_config_cache():
    global _CONFIG_CACHE_LOADED, _CONFIG_CACHE_UPDATED_AT
    with _CONFIG_LOCK:
        _CONFIG_CACHE.clear()
        _CONFIG_META.clear()
        _CONFIG_CACHE_LOADED = False
        _CONFIG_CACHE_UPDATED_AT = 0
    try:
        from services.runtime_context import clear_runtime_config_context
        clear_runtime_config_context()
    except Exception:
        pass


def refresh_config_cache():
    return load_config_cache(force=True)


def set_global_config(key, value, value_type=None, description="", is_secret=None):
    meta = DEFAULT_CONFIGS.get(key, {})
    if value_type is None:
        value_type = meta.get("type", "string")
    if is_secret is None:
        is_secret = meta.get("secret", False)
    set_config(key, value, value_type=value_type, description=description, is_secret=bool(is_secret))
    with _CONFIG_LOCK:
        _CONFIG_CACHE[key] = "" if value is None else str(value)
        _CONFIG_META[key] = {"value_type": value_type, "is_secret": bool(is_secret)}
        global _CONFIG_CACHE_LOADED, _CONFIG_CACHE_UPDATED_AT
        _CONFIG_CACHE_LOADED = True
        _CONFIG_CACHE_UPDATED_AT = time.time()
    print(f"[CONFIG_CACHE] set key={key}")
    try:
        from services.runtime_context import clear_runtime_config_context
        clear_runtime_config_context(key)
    except Exception:
        pass
    return True


def set_global_configs(config_dict):
    normalized = {}
    for key, value in (config_dict or {}).items():
        meta = DEFAULT_CONFIGS.get(key, {})
        if isinstance(value, dict):
            normalized[key] = value
        else:
            normalized[key] = {
                "value": value,
                "value_type": meta.get("type", "string"),
                "is_secret": meta.get("secret", False),
            }
    set_configs(normalized)
    with _CONFIG_LOCK:
        for key, meta in normalized.items():
            value = meta.get("value", "")
            _CONFIG_CACHE[key] = "" if value is None else str(value)
            _CONFIG_META[key] = {
                "value_type": meta.get("value_type") or meta.get("type") or DEFAULT_CONFIGS.get(key, {}).get("type", "string"),
                "is_secret": bool(meta.get("is_secret", meta.get("secret", DEFAULT_CONFIGS.get(key, {}).get("secret", False)))),
            }
        global _CONFIG_CACHE_LOADED, _CONFIG_CACHE_UPDATED_AT
        _CONFIG_CACHE_LOADED = True
        _CONFIG_CACHE_UPDATED_AT = time.time()
    print(f"[CONFIG_CACHE] set keys={list(normalized.keys())}")
    try:
        from services.runtime_context import clear_runtime_config_context
        for key in normalized:
            clear_runtime_config_context(key)
    except Exception:
        pass
    return True


def get_default_config_value(key, default=None):
    if key in DEFAULT_CONFIGS:
        return DEFAULT_CONFIGS[key]["value"]
    return default


def get_page_config_value(page_config, key):
    if not page_config:
        return None
    field = PAGE_CONFIG_MAP.get(key)
    if not field:
        return None
    value = page_config.get(field)
    if value is None or value == "":
        return None
    return value


def get_runtime_config(key, default=None, page_config=None):
    page_value = get_page_config_value(page_config, key)
    if page_value is not None:
        return page_value
    value = get_cached_config(key, None)
    if value is not None and value != "":
        return value
    default_value = get_default_config_value(key, None)
    if default_value is not None:
        return default_value
    return default


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def get_runtime_bool(key, default=False, page_config=None):
    return _to_bool(get_runtime_config(key, default, page_config), default)


def get_runtime_int(key, default=0, page_config=None):
    try:
        return int(get_runtime_config(key, default, page_config))
    except (TypeError, ValueError):
        return default


def get_runtime_float(key, default=0.0, page_config=None):
    try:
        return float(get_runtime_config(key, default, page_config))
    except (TypeError, ValueError):
        return default
