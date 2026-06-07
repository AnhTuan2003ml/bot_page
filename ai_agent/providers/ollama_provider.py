import requests

from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int


def _combined_prompt(messages):
    parts = []
    for message in messages or []:
        role = message.get("role", "user")
        content = (message.get("content") or "").strip()
        if content:
            parts.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(parts)


def chat(messages, model=None, temperature=None, max_tokens=None, **kwargs) -> str:
    base_url = get_runtime_config("LOCAL_LLM_URL", "http://localhost:11434").rstrip("/")
    model = model or get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct")
    temperature = temperature if temperature is not None else get_runtime_float("OLLAMA_TEMPERATURE", 0.25)
    max_tokens = max_tokens if max_tokens is not None else get_runtime_int("OLLAMA_MAX_TOKENS", 300)
    timeout = int(kwargs.get("timeout") or get_runtime_int("OLLAMA_TIMEOUT", 60) or 60)
    print(f"[OLLAMA] base_url={base_url}")
    print(f"[OLLAMA] model={model}")
    print("[OLLAMA] endpoint=/api/chat")

    payload = {
        "model": model,
        "messages": messages or [],
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    try:
        response = requests.post(f"{base_url}/api/chat", json=payload, timeout=timeout)
        response.raise_for_status()
        content = (response.json().get("message", {}).get("content") or "").strip()
        print(f"[OLLAMA] success len={len(content)}")
        return content
    except Exception as exc:
        print(f"[OLLAMA] error={exc}")

    try:
        print("[OLLAMA] endpoint=/api/generate")
        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": _combined_prompt(messages),
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        content = (response.json().get("response") or "").strip()
        print(f"[OLLAMA] success len={len(content)}")
        return content
    except Exception as exc:
        print(f"[OLLAMA] error={exc}")
        return ""
