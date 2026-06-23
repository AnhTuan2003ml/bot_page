import time

import requests

from utils.config_service import get_runtime_config, get_runtime_float, get_runtime_int


def _split_messages(messages):
    """Convert OpenAI-style chat messages to Gemini generateContent payload parts."""
    system_parts = []
    contents = []

    for item in messages or []:
        role = str((item or {}).get("role") or "user").strip().lower()
        text = str((item or {}).get("content") or "").strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
            continue
        gemini_role = "model" if role in {"assistant", "model"} else "user"
        if contents and contents[-1].get("role") == gemini_role:
            contents[-1]["parts"].append({"text": text})
        else:
            contents.append({"role": gemini_role, "parts": [{"text": text}]})

    if not contents and system_parts:
        contents.append({"role": "user", "parts": [{"text": "Hãy phản hồi theo system instruction."}]})

    return "\n\n".join(system_parts).strip(), contents


def _extract_text(data):
    texts = []
    for candidate in (data or {}).get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            text = part.get("text")
            if text:
                texts.append(text)
    return "\n".join(texts).strip()


def chat(messages, model=None, temperature=None, max_tokens=None, **kwargs) -> str:
    api_key = (kwargs.get("api_key") or get_runtime_config("GEMINI_API_KEY", "")).strip()
    model = model or get_runtime_config("GEMINI_MODEL", "gemini-2.5-flash")
    temperature = temperature if temperature is not None else get_runtime_float("GEMINI_TEMPERATURE", 0.25)
    max_tokens = max_tokens if max_tokens is not None else get_runtime_int("GEMINI_MAX_TOKENS", 300)
    timeout = int(kwargs.get("timeout") or get_runtime_int("GEMINI_TIMEOUT", 60))
    base_url = (kwargs.get("base_url") or get_runtime_config("GEMINI_API_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")).rstrip("/")

    print(f"[GEMINI] model={model}")
    if not api_key:
        print("[GEMINI] missing GEMINI_API_KEY in DB config")
        return ""

    system_text, contents = _split_messages(messages)
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_tokens),
        },
    }
    if system_text:
        payload["systemInstruction"] = {"parts": [{"text": system_text}]}

    url = f"{base_url}/models/{model}:generateContent"
    started = time.time()
    try:
        response = requests.post(
            url,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            json=payload,
            timeout=timeout,
        )
        duration_ms = int((time.time() - started) * 1000)
        if response.status_code >= 400:
            print(f"[MODEL_ERROR] Gemini status={response.status_code} duration_ms={duration_ms} body={response.text[:500]}")
            return ""
        text = _extract_text(response.json())
        print(f"[GEMINI] status=200 duration_ms={duration_ms} chars={len(text)}")
        return text
    except Exception as exc:
        print(f"[MODEL_ERROR] Gemini: {exc}")
        return ""
