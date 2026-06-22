import requests

from database.config_manager import get_admin_configs
from services.runtime_context import clear_page_context
from utils.config_service import get_runtime_config, set_global_config, set_global_configs
from web.services.common_admin_service import (
    GENERAL_CONFIG_KEYS,
    SECRET_CONFIG_KEYS,
    get_current_provider,
    sanitize_ai_config_payload,
)


def token_info():
    token = get_runtime_config("VERIFY_TOKEN", "")
    return {
        "success": True,
        "token_set": bool(token),
        "token_preview": token[:20] + "..." if token else "",
    }, 200


def update_token(data):
    data = data or {}
    token = data.get("token")
    app_id = data.get("app_id")
    app_secret = data.get("app_secret")
    if not token and not app_id and not app_secret:
        return {"success": False, "error": "At least one credential required"}, 400

    updated = []
    final_page_token = None
    try:
        current_app_id = app_id or ""
        current_app_secret = app_secret or ""
        if app_id:
            updated.append("app_id (request)")
        if app_secret:
            updated.append("app_secret (request)")

        if token:
            if not current_app_id or not current_app_secret:
                return {"success": False, "error": "APP_ID và APP_SECRET cần được cấu hình trước khi exchange token"}, 400

            resp1 = requests.get(
                "https://graph.facebook.com/v19.0/oauth/access_token",
                params={
                    "grant_type": "fb_exchange_token",
                    "client_id": current_app_id,
                    "client_secret": current_app_secret,
                    "fb_exchange_token": token,
                },
                timeout=30,
            )
            if resp1.status_code != 200:
                error_data = resp1.json() if resp1.text else {"error": "Unknown error"}
                return {"success": False, "error": f"Token exchange failed: {error_data.get('error', {}).get('message', resp1.text)}"}, 400

            long_lived_token = resp1.json().get("access_token")
            if not long_lived_token:
                return {"success": False, "error": "No access_token in exchange response"}, 400

            resp2 = requests.get(
                "https://graph.facebook.com/v19.0/me/accounts",
                params={"access_token": long_lived_token},
                timeout=30,
            )
            if resp2.status_code != 200:
                error_data = resp2.json() if resp2.text else {"error": "Unknown error"}
                return {"success": False, "error": f"Get accounts failed: {error_data.get('error', {}).get('message', resp2.text)}"}, 400

            pages = resp2.json().get("data", [])
            if not pages:
                return {"success": False, "error": "No pages found for this user. Please make sure you have admin access to a Facebook Page."}, 400

            first_page = pages[0]
            final_page_token = first_page.get("access_token")
            page_name = first_page.get("name", "Unknown")
            page_id = first_page.get("id", "")
            if not final_page_token:
                return {"success": False, "error": "No access_token in page data"}, 400

            from database.page_manager import add_page, get_page, update_page

            if get_page(page_id):
                update_page(page_id, page_access_token=final_page_token, page_name=page_name)
            else:
                from database.skill_manager import get_all_skills

                skills = get_all_skills()
                default_skill = skills[0]["name"] if skills else "Tư vấn biển số"
                add_page(
                    page_id=page_id,
                    page_name=page_name,
                    page_access_token=final_page_token,
                    ai_skill=default_skill,
                    ai_provider=get_current_provider(),
                    is_active=True,
                )
            clear_page_context(page_id)
            updated.append(f"page_token ({len(final_page_token)} chars) -> database")

        response = {"success": True, "message": f"Credentials updated - Active immediately: {', '.join(updated)}"}
        if final_page_token and "first_page" in locals():
            response["page_name"] = first_page.get("name")
            response["page_id"] = first_page.get("id")
        return response, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def update_app_id(data):
    data = data or {}
    app_id = data.get("app_id")
    if not app_id:
        return {"success": False, "error": "App ID required"}, 400
    try:
        set_global_config("FACEBOOK_APP_ID", app_id)
        return {"success": True, "message": "App ID updated"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def update_app_secret(data):
    data = data or {}
    try:
        app_secret = data.get("app_secret")
        if not app_secret:
            return {"success": False, "error": "Missing app_secret"}, 400
        set_global_config("FACEBOOK_APP_SECRET", app_secret, is_secret=True)
        return {"success": True, "message": "APP_SECRET updated"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def full_config():
    try:
        return {"success": True, "config": get_admin_configs()}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def update_full_config(data, content_type=None):
    data = data or {}
    try:
        print(f"[CONFIG_SAVE] content_type={content_type}")
        print(f"[CONFIG_SAVE] incoming_keys={list(data.keys())}")
        updates = sanitize_ai_config_payload(data, GENERAL_CONFIG_KEYS)
        for key, value in data.items():
            if key in GENERAL_CONFIG_KEYS and key not in updates and key not in SECRET_CONFIG_KEYS:
                updates[key] = "" if value is None else str(value).strip()
        if updates:
            set_global_configs(updates)
        print(f"[CONFIG_DB] UI saved keys={list(updates.keys())}")

        return {
            "success": True,
            "message": f"Da luu {len(updates)} cau hinh vao database",
            "updated": list(updates.keys()),
            "config": get_admin_configs(),
            "verify_token": get_runtime_config("VERIFY_TOKEN", ""),
            "groq_key_set": bool(get_runtime_config("GROQ_API_KEY", "").strip()),
        }, 200
    except Exception as exc:
        print(f"[CONFIG_SAVE] ERROR: {exc}")
        return {"success": False, "error": str(exc)}, 500
