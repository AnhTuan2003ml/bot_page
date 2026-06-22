try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int


def chat(messages, model=None, temperature=None, max_tokens=None, **kwargs) -> str:
    api_key = (kwargs.get("api_key") or get_runtime_config("OPENAI_API_KEY", "")).strip()
    model = model or get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini")
    temperature = temperature if temperature is not None else get_runtime_float("OPENAI_TEMPERATURE", 0.25)
    max_tokens = max_tokens if max_tokens is not None else get_runtime_int("OPENAI_MAX_TOKENS", 300)
    print(f"[OPENAI] model={model}")

    if not api_key or OpenAI is None:
        print("[OPENAI] missing OPENAI_API_KEY in DB config")
        return ""
    try:
        client = OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=messages or [],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"[MODEL_ERROR] OpenAI: {exc}")
        return ""
