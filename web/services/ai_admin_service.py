from brain.pipeline import process_message
from utils.config_service import get_runtime_config, set_global_configs
from web.services.common_admin_service import (
    AI_CONFIG_KEYS,
    get_current_intent_model,
    get_current_intent_provider,
    get_current_provider,
    get_current_skill,
    get_intent_parser_enabled,
    normalize_ai_provider,
    provider_options,
    safe_ai_settings,
    sanitize_ai_config_payload,
)


def provider_info():
    return {"success": True, "provider": get_current_provider(), "available_providers": provider_options()}, 200


def set_provider(data):
    data = data or {}
    provider = normalize_ai_provider(data.get("provider") or get_current_provider())
    set_global_configs({"AI_PROVIDER": provider, "DEFAULT_AI_PROVIDER": provider})
    print("[CONFIG_DB] UI saved keys=['AI_PROVIDER', 'DEFAULT_AI_PROVIDER']")
    return {"success": True, "provider": provider}, 200


def intent_provider_info():
    return {
        "success": True,
        "intent_provider": get_current_intent_provider(),
        "intent_model": get_current_intent_model(),
        "enabled": get_intent_parser_enabled(),
        "available_providers": provider_options(),
    }, 200


def set_intent_provider(data):
    from ai_agent.model_client import model_looks_incompatible

    data = data or {}
    provider = normalize_ai_provider(data.get("provider") or get_current_intent_provider())
    model = str(data.get("model", "") or "").strip()
    enabled = bool(data.get("enabled", True))
    if model and model_looks_incompatible(provider, model):
        model = {
            "groq": get_runtime_config("GROQ_INTENT_MODEL", "llama-3.1-8b-instant"),
            "ollama": get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct"),
            "openai": get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini"),
        }[provider]

    set_global_configs({
        "USE_LLM_INTENT_PARSER": "true" if enabled else "false",
        "INTENT_PARSER_PROVIDER": provider,
        "INTENT_PARSER_MODEL": model,
    })
    print("[CONFIG_DB] UI saved keys=['USE_LLM_INTENT_PARSER', 'INTENT_PARSER_PROVIDER', 'INTENT_PARSER_MODEL']")
    return {"success": True, "intent_provider": provider, "intent_model": model, "enabled": enabled}, 200


def ai_settings():
    return {"success": True, "settings": safe_ai_settings(public=True), "providers": provider_options()}, 200


def save_ai_settings(data):
    updates = sanitize_ai_config_payload(data or {}, AI_CONFIG_KEYS)
    if updates:
        set_global_configs(updates)
    print(f"[CONFIG_DB] UI saved keys={list(updates.keys())}")
    return {
        "success": True,
        "message": "Da luu cau hinh AI vao database",
        "settings": safe_ai_settings(public=True),
        "updated": list(updates.keys()),
    }, 200


def test_provider(data):
    data = data or {}
    role = str(data.get("role") or "writer").strip().lower()
    provider = normalize_ai_provider(data.get("provider") or (get_current_intent_provider() if role == "intent" else get_current_provider()))
    model = str(data.get("model") or "").strip()
    message = str(data.get("message") or "xin chao").strip()

    try:
        if role == "intent":
            from ai_agent.model_client import call_intent_model
            result = call_intent_model([
                {"role": "system", "content": "Trả JSON ngắn phân tích intent."},
                {"role": "user", "content": message},
            ], provider=provider, model=model or None)
        else:
            from ai_agent.model_client import call_model

            result = call_model(
                [{"role": "user", "content": "Tra loi ngan: xin chao"}],
                provider=provider,
                model=model or None,
            )
        return {"success": True, "role": role, "provider": provider, "model": model, "result": result}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def test_ai(data):
    data = data or {}
    message = data.get("message", "Hello")
    skill = data.get("skill", get_current_skill())
    try:
        from database.skill_manager import get_skill_by_name
        skill_config = get_skill_by_name(skill) or {}
    except Exception:
        skill_config = {}

    provider = normalize_ai_provider(data.get("provider", get_current_provider()))
    intent_provider = normalize_ai_provider(data.get("intent_provider", get_current_intent_provider()))
    intent_model = str(data.get("intent_model", get_current_intent_model()) or "").strip()
    test_mode = data.get("test_mode", "reply")

    try:
        if test_mode == "intent":
            from brain.pipeline import analyze_message
            parsed_intent = analyze_message(
                skill_config.get("persona_json") or "{}",
                skill_config.get("training_content") or "",
                None,
                {},
                [],
                message,
                page_config={"intent_parser_provider": intent_provider, "intent_parser_model": intent_model},
            )
            return {"success": True, "parsed_intent": parsed_intent}, 200

        response = process_message(
            chat_id="__admin_test__",
            user_message=message,
            page_config={
                "skill": skill,
                "ai_skill": skill,
                "expertise": skill_config,
                "expertise_id": skill_config.get("id"),
                "persona_json": skill_config.get("persona_json") or "{}",
                "training_content": skill_config.get("training_content") or "",
                "data_table": skill_config.get("data_table") or "",
                                "ai_provider": provider,
                "intent_parser_provider": intent_provider,
                "intent_parser_model": intent_model,
                                                "page_id": "admin_test",
                "page_name": "Admin Test",
            },
            sender_name=data.get("sender_name"),
            raw_context={
                "is_first_message": True,
                "sender_psid": "__admin_test__",
            },
        )
        return {"success": True, "response": response}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500
