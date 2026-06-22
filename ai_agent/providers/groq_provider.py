import time

try:
    from groq import Groq
except Exception:  # pragma: no cover
    Groq = None

try:
    from utils.api_logger import log_groq_call
except Exception:  # pragma: no cover
    def log_groq_call(*args, **kwargs):
        return None

from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int


def chat(messages, model=None, temperature=None, max_tokens=None, **kwargs) -> str:
    api_key = (kwargs.get("api_key") or get_runtime_config("GROQ_API_KEY", "")).strip()
    model = model or get_runtime_config("GROQ_MODEL", "llama-3.3-70b-versatile")
    temperature = temperature if temperature is not None else get_runtime_float("GROQ_TEMPERATURE", 0.25)
    max_tokens = max_tokens if max_tokens is not None else get_runtime_int("GROQ_MAX_TOKENS", 300)
    print(f"[GROQ] model={model}")

    if not api_key or Groq is None:
        print("[GROQ] missing GROQ_API_KEY in DB config")
        log_groq_call(0, error="Groq unavailable or missing key", model=model)
        return ""

    started = time.time()
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model=model,
            messages=messages or [],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )
        log_groq_call(200, duration_ms=int((time.time() - started) * 1000), model=model)
        return (completion.choices[0].message.content or "").strip()
    except Exception as exc:
        print(f"[MODEL_ERROR] Groq: {exc}")
        log_groq_call(0, duration_ms=int((time.time() - started) * 1000), error=str(exc), model=model)
        return ""
