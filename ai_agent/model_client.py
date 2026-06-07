from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int

from .providers import groq_provider, ollama_provider, openai_provider


def normalize_provider(provider=None):
    selected = (provider or "").strip().lower()
    if selected in {"", "default"}:
        selected = get_runtime_config("AI_PROVIDER", get_runtime_config("DEFAULT_AI_PROVIDER", "ollama"))
    if selected in {"local", "local_llm", "local-llm", "ollama_local"}:
        return "ollama"
    if selected in {"groq", "ollama", "openai"}:
        return selected
    print(f"[MODEL_CLIENT] Unsupported provider={selected}, fallback ollama")
    return "ollama"


def model_looks_incompatible(provider, model):
    provider = normalize_provider(provider)
    m = (model or "").strip().lower()
    if not m:
        return False
    if provider == "groq":
        return m.startswith("qwen") or ":" in m
    if provider == "openai":
        return m.startswith("qwen") or ":" in m or m.startswith("llama-")
    return False


def _writer_default_model(provider, page_config=None):
    page_model = get_runtime_config("AI_MODEL", "", page_config)
    if page_model:
        return page_model
    if provider == "groq":
        return get_runtime_config("GROQ_MODEL", "llama-3.3-70b-versatile", page_config)
    if provider == "openai":
        return get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini", page_config)
    return get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct", page_config)


def _intent_default_model(provider, page_config=None):
    if provider == "groq":
        return get_runtime_config(
            "GROQ_INTENT_MODEL",
            get_runtime_config("GROQ_MODEL", "llama-3.1-8b-instant", page_config),
            page_config,
        )
    if provider == "openai":
        return get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini", page_config)
    return get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct", page_config)


def _page_value(page_config, key, default=None):
    if page_config and page_config.get(key) not in (None, ""):
        return page_config.get(key)
    return default


def _page_float(page_config, key, config_key, default):
    value = _page_value(page_config, key, None)
    if value is not None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return get_runtime_float(config_key, default, page_config)


def _page_int(page_config, key, config_key, default):
    value = _page_value(page_config, key, None)
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return get_runtime_int(config_key, default, page_config)


def call_model(messages, provider=None, model=None, temperature=None, max_tokens=None, page_config=None, **kwargs) -> str:
    selected = normalize_provider(provider or get_runtime_config("AI_PROVIDER", "ollama", page_config))
    selected_model = model or _writer_default_model(selected, page_config)
    if model_looks_incompatible(selected, selected_model):
        print(f"[MODEL_CLIENT] incompatible writer model={selected_model} provider={selected}, using provider default")
        selected_model = _writer_default_model(selected, page_config)

    if selected == "groq":
        temperature = temperature if temperature is not None else _page_float(page_config, "groq_temperature", "GROQ_TEMPERATURE", 0.25)
        max_tokens = max_tokens if max_tokens is not None else _page_int(page_config, "groq_max_tokens", "GROQ_MAX_TOKENS", 300)
    elif selected == "ollama":
        temperature = temperature if temperature is not None else _page_float(page_config, "ollama_temperature", "OLLAMA_TEMPERATURE", 0.25)
        max_tokens = max_tokens if max_tokens is not None else _page_int(page_config, "ollama_max_tokens", "OLLAMA_MAX_TOKENS", 300)
        kwargs.setdefault("timeout", _page_int(page_config, "ollama_timeout", "OLLAMA_TIMEOUT", 60))
    elif selected == "openai":
        temperature = temperature if temperature is not None else _page_float(page_config, "openai_temperature", "OPENAI_TEMPERATURE", 0.25)
        max_tokens = max_tokens if max_tokens is not None else _page_int(page_config, "openai_max_tokens", "OPENAI_MAX_TOKENS", 300)

    provider_token = get_runtime_config("AI_PROVIDER_TOKEN", "", page_config)
    if provider_token and selected in {"groq", "openai"}:
        kwargs.setdefault("api_key", provider_token)

    print(f"[MODEL_CLIENT] role=writer provider={selected} model={selected_model}")
    if selected == "groq":
        return groq_provider.chat(messages, model=selected_model, temperature=temperature, max_tokens=max_tokens, **kwargs)
    if selected == "ollama":
        return ollama_provider.chat(messages, model=selected_model, temperature=temperature, max_tokens=max_tokens, **kwargs)
    if selected == "openai":
        return openai_provider.chat(messages, model=selected_model, temperature=temperature, max_tokens=max_tokens, **kwargs)
    raise ValueError(f"Unsupported provider: {selected}")


def call_intent_model(messages, provider=None, model=None, temperature=None, max_tokens=None, timeout=None, page_config=None, **kwargs) -> str:
    selected = normalize_provider(provider or get_runtime_config("INTENT_PARSER_PROVIDER", "ollama", page_config))
    selected_model = model or get_runtime_config("INTENT_PARSER_MODEL", "", page_config)
    if not selected_model or model_looks_incompatible(selected, selected_model):
        if selected_model:
            print(f"[MODEL_CLIENT] incompatible intent model={selected_model} provider={selected}, using provider default")
        selected_model = _intent_default_model(selected, page_config)

    selected_temperature = temperature if temperature is not None else _page_float(page_config, "intent_parser_temperature", "INTENT_PARSER_TEMPERATURE", 0)
    selected_max_tokens = max_tokens if max_tokens is not None else _page_int(page_config, "intent_parser_max_tokens", "INTENT_PARSER_MAX_TOKENS", 160)
    selected_timeout = timeout if timeout is not None else _page_int(page_config, "intent_parser_timeout", "INTENT_PARSER_TIMEOUT", 45)
    kwargs.setdefault("timeout", selected_timeout)

    parser_token = get_runtime_config("INTENT_PARSER_TOKEN", "", page_config)
    if parser_token and selected in {"groq", "openai"}:
        kwargs.setdefault("api_key", parser_token)

    print(f"[MODEL_CLIENT] role=intent provider={selected} model={selected_model}")
    if selected == "groq":
        return groq_provider.chat(messages, model=selected_model, temperature=selected_temperature, max_tokens=selected_max_tokens, **kwargs)
    if selected == "ollama":
        return ollama_provider.chat(messages, model=selected_model, temperature=selected_temperature, max_tokens=selected_max_tokens, **kwargs)
    if selected == "openai":
        return openai_provider.chat(messages, model=selected_model, temperature=selected_temperature, max_tokens=selected_max_tokens, **kwargs)
    raise ValueError(f"Unsupported provider: {selected}")
