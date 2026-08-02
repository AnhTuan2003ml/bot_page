import sqlite3

import requests

from services.runtime_context import clear_page_context
from utils.config_service import get_runtime_config
from utils.message_queue import clear_queue_for_page
from web.services.common_admin_service import (
    get_current_intent_model,
    get_current_intent_provider,
    get_current_provider,
    get_intent_parser_enabled,
    normalize_ai_provider,
    normalize_ai_skill,
    provider_options,
)


def list_pages():
    from database.page_manager import get_all_pages

    try:
        pages = get_all_pages()
        return {"success": True, "pages": pages}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def add_page(data):
    from database.page_manager import add_page as db_add_page

    data = data or {}
    for field in ["page_id", "page_name", "page_access_token"]:
        if not data.get(field):
            return {"success": False, "error": f"{field} required"}, 400

    try:
        success = db_add_page(
            page_id=data["page_id"],
            page_name=data["page_name"],
            page_access_token=data["page_access_token"],
            ai_skill=normalize_ai_skill(data.get("ai_skill", "plate_sales")),
            ai_provider=normalize_ai_provider(data.get("ai_provider", get_current_provider())),
            intent_parser_provider=normalize_ai_provider(data.get("intent_parser_provider") or get_current_intent_provider()),
            intent_parser_model=str(data.get("intent_parser_model", "") or "").strip(),
            ai_model=str(data.get("ai_model", "") or "").strip(),
            ai_provider_token=str(data.get("ai_provider_token", "") or "").strip(),
            intent_parser_token=str(data.get("intent_parser_token", "") or "").strip(),
            uid_nguoi_phu_trach=data.get("uid_nguoi_phu_trach", ""),
            app_id=data.get("app_id", ""),
            app_secret=data.get("app_secret", ""),
        )
        if success:
            clear_page_context(data["page_id"])
            return {"success": True, "message": "Page added successfully"}, 200
        return {"success": False, "error": "Page ID already exists"}, 409
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def get_page(page_id):
    from database.page_manager import get_page as db_get_page

    try:
        page = db_get_page(page_id)
        if page:
            return {"success": True, "page": page}, 200
        return {"success": False, "error": "Page not found"}, 404
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def update_page(page_id, data):
    from database.page_manager import update_page as db_update_page

    data = data or {}
    if isinstance(data, dict) and "ai_provider" in data:
        data["ai_provider"] = normalize_ai_provider(data.get("ai_provider"))
    if isinstance(data, dict) and data.get("intent_parser_provider"):
        data["intent_parser_provider"] = normalize_ai_provider(data.get("intent_parser_provider"))
    if isinstance(data, dict) and "ai_skill" in data:
        data["ai_skill"] = normalize_ai_skill(data.get("ai_skill"))

    try:
        success = db_update_page(page_id, **data)
        if success:
            clear_page_context(page_id)
            return {"success": True, "message": "Page updated successfully"}, 200
        return {"success": False, "error": "Page not found or no changes"}, 404
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def delete_page(page_id):
    from database.page_manager import delete_page as db_delete_page

    try:
        success = db_delete_page(page_id)
        if success:
            clear_page_context(page_id)
            clear_queue_for_page(page_id)
            return {"success": True, "message": "Page deleted successfully"}, 200
        return {"success": False, "error": "Page not found"}, 404
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def toggle_page(page_id):
    from database.page_manager import DB_PATH, get_page as db_get_page, update_page as db_update_page

    try:
        page = db_get_page(page_id)
        if not page:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM pages WHERE page_id = ?", (page_id,))
            row = cursor.fetchone()
            conn.close()

            if row:
                current_status = row[0]
                new_status = 1 if current_status == 0 else 0
                success = db_update_page(page_id, is_active=new_status)
                if success:
                    clear_page_context(page_id)
                    if new_status == 0:
                        clear_queue_for_page(page_id)
                    status_text = "enabled" if new_status == 1 else "disabled"
                    return {"success": True, "message": f"Page {status_text}", "is_active": new_status == 1}, 200

            return {"success": False, "error": "Page not found"}, 404

        current_status = page.get("is_active", 1)
        new_status = 0 if current_status == 1 else 1
        success = db_update_page(page_id, is_active=new_status)
        if success:
            clear_page_context(page_id)
            if new_status == 0:
                clear_queue_for_page(page_id)
            status_text = "disabled" if new_status == 0 else "enabled"
            return {"success": True, "message": f"Page {status_text}", "is_active": new_status == 1}, 200
        return {"success": False, "error": "Failed to update page"}, 500
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def ai_config():
    try:
        from database.skill_manager import get_all_skills

        skills = get_all_skills()
        skills_by_id = {}
        canonical_names = {
            "plate_sales": "Tư vấn biển số",
            "sales": "Bán hàng chung",
            "companion": "Người bạn đồng hành",
            "friendly": "Friendly",
            "fashion_sales": "Tư vấn bán quần áo",
        }
        legacy_skill_ids = {
            "t_v_n_bi_n_s": "plate_sales",
            "b_n_h_ng_chung": "sales",
        }
        for skill in skills:
            skill_id = skill.get("skill_id") or skill["name"]
            skill_id = legacy_skill_ids.get(skill_id, skill_id)
            item = {
                "id": skill_id,
                "name": canonical_names.get(skill_id, skill["name"]),
                "description": skill.get("description", ""),
                "skill_id": skill_id,
                "character_name": skill.get("character_name", ""),
                "personality": skill.get("personality", ""),
                "business_domain": skill.get("business_domain", "generic_chat"),
                "target_description": skill.get("target_description", ""),
                "use_plates": skill.get("use_plates", 0),
                "use_products": skill.get("use_products", 0),
                "use_rag": skill.get("use_rag", 0),
            }
            if skill_id not in skills_by_id or skill.get("name") in canonical_names.values():
                skills_by_id[skill_id] = item

        preferred_order = ["plate_sales", "fashion_sales", "companion", "friendly", "sales"]
        skills_list = [skills_by_id.pop(key) for key in preferred_order if key in skills_by_id]
        skills_list.extend(skills_by_id.values())
        writer_provider = get_current_provider()
        provider_models = {
            "groq": get_runtime_config("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "ollama": get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct"),
            "openai": get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini"),
            "gemini": get_runtime_config("GEMINI_MODEL", "gemini-2.5-flash"),
        }
        intent_provider_models = {
            "groq": get_runtime_config("GROQ_INTENT_MODEL", "llama-3.1-8b-instant"),
            "ollama": get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct"),
            "openai": get_runtime_config("OPENAI_MODEL", "gpt-4.1-mini"),
            "gemini": get_runtime_config("GEMINI_INTENT_MODEL", get_runtime_config("GEMINI_MODEL", "gemini-2.5-flash")),
        }
        writer_model = provider_models.get(writer_provider, get_runtime_config("OLLAMA_MODEL", "qwen3:4b-instruct"))

        return {
            "success": True,
            "skills": skills_list,
            "providers": provider_options(),
            "writer_provider": writer_provider,
            "writer_model": writer_model,
            "intent_provider": get_current_intent_provider(),
            "intent_model": get_current_intent_model(),
            "provider_models": provider_models,
            "intent_provider_models": intent_provider_models,
            "intent_parser_enabled": get_intent_parser_enabled(),
        }, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def verify_page_token(data):
    data = data or {}
    short_token = data.get("token")
    if not short_token:
        return {"success": False, "error": "Token is required"}, 400

    app_id = data.get("app_id", "").strip()
    app_secret = data.get("app_secret", "").strip()
    if not app_id or not app_secret:
        return {"success": False, "error": "APP_ID và APP_SECRET bắt buộc phải nhập cho mỗi page"}, 400

    try:
        exchange_url = "https://graph.facebook.com/v25.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        }
        resp1 = requests.get(exchange_url, params=params, timeout=30)
        if resp1.status_code != 200:
            error_data = resp1.json() if resp1.text else {"error": "Unknown error"}
            return {"success": False, "error": f"Token exchange failed: {error_data.get('error', {}).get('message', resp1.text)}"}, 400

        long_lived_token = resp1.json().get("access_token")
        if not long_lived_token:
            return {"success": False, "error": "No access_token in exchange response"}, 400

        accounts_url = "https://graph.facebook.com/v25.0/me/accounts"
        resp2 = requests.get(accounts_url, params={"access_token": long_lived_token}, timeout=30)
        if resp2.status_code != 200:
            error_data = resp2.json() if resp2.text else {"error": "Unknown error"}
            return {"success": False, "error": f"Get accounts failed: {error_data.get('error', {}).get('message', resp2.text)}"}, 400

        pages = resp2.json().get("data", [])
        if not pages:
            return {"success": False, "error": "No pages found for this user. Please make sure you have admin access to a Facebook Page."}, 400

        first_page = pages[0]
        page_access_token = first_page.get("access_token")
        page_id = first_page.get("id")
        page_name = first_page.get("name", "Unknown")
        if not page_access_token:
            return {"success": False, "error": "No access_token in page data"}, 400

        subscribe_resp = requests.post(
            f"https://graph.facebook.com/v18.0/{page_id}/subscribed_apps",
            params={"access_token": page_access_token},
            data={"subscribed_fields": "messages,messaging_postbacks,messaging_optins,message_deliveries,message_reads,message_echoes,message_reactions,message_edits"},
            timeout=10,
        )
        subscribed = subscribe_resp.json().get("success", False)

        from database.page_manager import add_page as db_add_page, get_page as db_get_page, update_page as db_update_page
        from database.skill_manager import get_all_skills

        ai_skill = normalize_ai_skill(data.get("ai_skill", ""))
        ai_provider = normalize_ai_provider(data.get("ai_provider", get_current_provider()))
        intent_parser_provider = normalize_ai_provider(data.get("intent_parser_provider") or get_current_intent_provider())
        intent_parser_model = str(data.get("intent_parser_model", "") or "").strip()
        ai_model = str(data.get("ai_model", "") or "").strip()
        ai_provider_token = str(data.get("ai_provider_token", "") or "").strip()
        intent_parser_token = str(data.get("intent_parser_token", "") or "").strip()
        if not ai_skill:
            skills = get_all_skills()
            ai_skill = normalize_ai_skill(skills[0].get("skill_id") or skills[0]["name"]) if skills else "plate_sales"

        if db_get_page(page_id):
            db_update_page(
                page_id,
                page_name=page_name,
                page_access_token=page_access_token,
                app_id=app_id,
                app_secret=app_secret,
                ai_skill=ai_skill,
                ai_provider=ai_provider,
                intent_parser_provider=intent_parser_provider,
                intent_parser_model=intent_parser_model,
                ai_model=ai_model,
                ai_provider_token=ai_provider_token,
                intent_parser_token=intent_parser_token,
            )
        else:
            db_add_page(
                page_id=page_id,
                page_name=page_name,
                page_access_token=page_access_token,
                ai_skill=ai_skill,
                ai_provider=ai_provider,
                intent_parser_provider=intent_parser_provider,
                intent_parser_model=intent_parser_model,
                ai_model=ai_model,
                ai_provider_token=ai_provider_token,
                intent_parser_token=intent_parser_token,
                app_id=app_id,
                app_secret=app_secret,
                is_active=True,
            )
        clear_page_context(page_id)

        page_response = {
            "id": page_id,
            "name": page_name,
            "access_token": page_access_token,
            "app_id": app_id,
            "app_secret": app_secret,
            "page_id": page_id,
        }
        if len(pages) > 1:
            return {
                "success": True,
                "subscribed": subscribed,
                "multiple_pages": True,
                "pages": [
                    {
                        "id": str(page.get("id")),
                        "name": page.get("name"),
                        "access_token": page.get("access_token"),
                        "app_id": app_id,
                        "app_secret": app_secret,
                    }
                    for page in pages if page.get("access_token")
                ],
                "page": page_response,
            }, 200
        return {"success": True, "subscribed": subscribed, "multiple_pages": False, "page": page_response}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500

def subscribe_and_save_page(data):
    """
    Subscribe webhook + lưu DB cho 1 page cụ thể đã được chọn từ danh sách.
    Nhận page_id, page_name, page_access_token, app_id, app_secret, ai_skill, ...
    """
    data = data or {}
    page_id = str(data.get("page_id", "")).strip()
    page_name = data.get("page_name", "Unknown")
    page_access_token = data.get("page_access_token", "").strip()
    app_id = data.get("app_id", "").strip()
    app_secret = data.get("app_secret", "").strip()

    if not page_id or not page_access_token:
        return {"success": False, "error": "page_id và page_access_token bắt buộc"}, 400

    try:
        # Subscribe webhook cho page này
        subscribed = False
        try:
            subscribe_resp = requests.post(
                f"https://graph.facebook.com/v25.0/{page_id}/subscribed_apps",
                params={"access_token": page_access_token},
                data={
                    "subscribed_fields": "messages,messaging_postbacks,messaging_optins,"
                    "message_deliveries,message_reads,message_echoes,message_reactions,message_edits"
                },
                timeout=10,
            )
            subscribed = subscribe_resp.json().get("success", False)
        except Exception as sub_err:
            print(f"[SUBSCRIBE] Warning: subscribe failed for {page_id}: {sub_err}")

        # Lưu hoặc cập nhật page trong DB
        from database.page_manager import add_page as db_add_page, get_page as db_get_page, update_page as db_update_page
        from database.skill_manager import get_all_skills

        ai_skill = normalize_ai_skill(data.get("ai_skill", ""))
        ai_provider = normalize_ai_provider(data.get("ai_provider", get_current_provider()))
        intent_parser_provider = normalize_ai_provider(data.get("intent_parser_provider") or get_current_intent_provider())
        intent_parser_model = str(data.get("intent_parser_model", "") or "").strip()
        ai_model = str(data.get("ai_model", "") or "").strip()
        ai_provider_token = str(data.get("ai_provider_token", "") or "").strip()
        intent_parser_token = str(data.get("intent_parser_token", "") or "").strip()

        if not ai_skill:
            skills = get_all_skills()
            ai_skill = normalize_ai_skill(skills[0].get("skill_id") or skills[0]["name"]) if skills else "plate_sales"

        if db_get_page(page_id):
            db_update_page(
                page_id,
                page_name=page_name,
                page_access_token=page_access_token,
                app_id=app_id,
                app_secret=app_secret,
                ai_skill=ai_skill,
                ai_provider=ai_provider,
                intent_parser_provider=intent_parser_provider,
                intent_parser_model=intent_parser_model,
                ai_model=ai_model,
                ai_provider_token=ai_provider_token,
                intent_parser_token=intent_parser_token,
            )
        else:
            db_add_page(
                page_id=page_id,
                page_name=page_name,
                page_access_token=page_access_token,
                ai_skill=ai_skill,
                ai_provider=ai_provider,
                intent_parser_provider=intent_parser_provider,
                intent_parser_model=intent_parser_model,
                ai_model=ai_model,
                ai_provider_token=ai_provider_token,
                intent_parser_token=intent_parser_token,
                app_id=app_id,
                app_secret=app_secret,
                is_active=True,
            )

        clear_page_context(page_id)

        return {
            "success": True,
            "subscribed": subscribed,
            "message": f"Page {page_name} đã được thêm thành công",
            "page": {
                "id": page_id,
                "name": page_name,
            },
        }, 200

    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def refresh_page_token(page_id, data):
    """
    Cấp lại token Page cho 1 page cụ thể - giống luồng "Thêm Page mới":
    - Nếu token dán vào là User Access Token: đổi sang token dài hạn (gia hạn thời gian),
      rồi lấy Page Access Token mới từ /me/accounts.
    - Nếu token dán vào đã là Page Access Token: dùng luôn.
    - Sau đó cập nhật DB, subscribe webhook (cho phép app) và clear cache runtime.
    """
    data = data or {}
    pasted_token = str(data.get("token") or "").strip()
    if not pasted_token:
        return {"success": False, "error": "Vui lòng dán User Access Token (hoặc Page Access Token) của tài khoản"}, 400

    from database.page_manager import get_all_pages as db_get_all_pages, update_page as db_update_page

    page = None
    for item in db_get_all_pages():
        if str(item.get("page_id")) == str(page_id):
            page = item
            break
    if not page:
        return {"success": False, "error": "Page không tồn tại"}, 404

    app_id = str(data.get("app_id", "") or page.get("app_id") or "").strip()
    app_secret = str(data.get("app_secret", "") or page.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        return {"success": False, "error": "Thiếu APP_ID / APP_SECRET. Hãy nhập App ID và App Secret của Page trong form này."}, 400

    try:
        # Bước 1: Exchange User token -> token dài hạn (nếu là user token)
        long_lived_token = None
        exchange_error = None
        try:
            exchange_url = "https://graph.facebook.com/v25.0/oauth/access_token"
            params = {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": pasted_token,
            }
            resp1 = requests.get(exchange_url, params=params, timeout=30)
            if resp1.status_code == 200:
                long_lived_token = resp1.json().get("access_token")
            else:
                err1 = resp1.json() if resp1.text else {}
                exchange_error = err1.get("error", {}).get("message", resp1.text)
        except Exception as exc:
            exchange_error = str(exc)

        # Bước 2: Tìm Page token trong tài khoản (thử token dài hạn trước, rồi token dán vào)
        candidate_tokens = [long_lived_token, pasted_token]
        target_page = None
        used_token = None
        base_url = "https://graph.facebook.com/v25.0/me/accounts"
        for cand in candidate_tokens:
            if not cand or cand == used_token:
                continue
            url = base_url
            params2 = {"access_token": cand, "limit": 100, "fields": "id,name,access_token"}
            request_count = 0
            while url and request_count < 20:
                request_count += 1
                try:
                    resp2 = requests.get(url, params=params2 if url == base_url else {}, timeout=30)
                except Exception:
                    break
                if resp2.status_code != 200:
                    break
                result = resp2.json()
                for p in result.get("data", []):
                    if str(p.get("id")) == str(page_id):
                        target_page = p
                        used_token = cand
                        break
                if target_page:
                    break
                url = result.get("paging", {}).get("next")

        if not target_page:
            if exchange_error and not long_lived_token:
                return {"success": False, "error": f"Exchange token thất bại: {exchange_error}"}, 400
            return {"success": False, "error": "Không tìm thấy Page này trong tài khoản. Hãy chắc chắn tài khoản có quyền admin của Page (hoặc token dán vào thuộc đúng Page này)."}, 400

        page_access_token = target_page.get("access_token")
        if not page_access_token:
            return {"success": False, "error": "Không lấy được access_token của Page"}, 400

        page_name = target_page.get("name") or page.get("page_name") or "Unknown"

        # Bước 3: Subscribe webhook cho Page (cho phép app nhận tin nhắn)
        subscribed = False
        try:
            subscribe_resp = requests.post(
                f"https://graph.facebook.com/v25.0/{page_id}/subscribed_apps",
                params={"access_token": page_access_token},
                data={
                    "subscribed_fields": "messages,messaging_postbacks,messaging_optins,"
                    "message_deliveries,message_reads,message_echoes,message_reactions,message_edits"
                },
                timeout=10,
            )
            subscribed = subscribe_resp.json().get("success", False)
        except Exception as sub_err:
            print(f"[REFRESH_TOKEN] Subscribe warning for {page_id}: {sub_err}")

        # Bước 4: Lưu token Page mới vào DB + clear runtime cache
        db_update_page(
            page_id,
            page_access_token=page_access_token,
            page_name=page_name,
            app_id=app_id,
            app_secret=app_secret,
        )
        clear_page_context(page_id)

        # Thời hạn hết hạn token Page
        expires_at = None
        try:
            dbg = requests.get(
                "https://graph.facebook.com/v25.0/debug_token",
                params={"input_token": page_access_token, "access_token": page_access_token},
                timeout=15,
            )
            expires_at = dbg.json().get("data", {}).get("expires_at")
        except Exception:
            pass

        return {
            "success": True,
            "subscribed": subscribed,
            "message": f"Đã cấp lại token Page cho '{page_name}'",
            "expires_at": expires_at,
            "page": {"id": page_id, "name": page_name, "page_access_token": page_access_token},
        }, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def verify_and_list_pages(data):
    """
    Lấy HẾT tất cả Page Facebook (tự động phân trang) - Phiên bản hoàn chỉnh
    """
    data = data or {}
    short_token = data.get("token")
    if not short_token:
        return {"success": False, "error": "Token is required"}, 400

    app_id = data.get("app_id", "").strip()
    app_secret = data.get("app_secret", "").strip()
    if not app_id or not app_secret:
        return {"success": False, "error": "APP_ID và APP_SECRET bắt buộc phải nhập"}, 400

    try:
        # Exchange token
        exchange_url = "https://graph.facebook.com/v25.0/oauth/access_token"
        exchange_params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        }
        resp1 = requests.get(exchange_url, params=exchange_params, timeout=30)
        if resp1.status_code != 200:
            return {"success": False, "error": f"Token exchange failed: {resp1.text}"}, 400

        long_lived_token = resp1.json().get("access_token")
        if not long_lived_token:
            return {"success": False, "error": "No access_token in exchange response"}, 400

        # ==================== LẤY HẾT PAGE ====================
        all_pages = []
        url = "https://graph.facebook.com/v25.0/me/accounts"
        params = {
            "access_token": long_lived_token,
            "limit": 100,
            "fields": "id,name,access_token,category"
        }
        request_count = 0

        while url and request_count < 20:
            request_count += 1
            print(f"[FB_PAGINATION] Request #{request_count}")

            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code != 200:
                print(f"[FB_PAGINATION] Error: {resp.text}")
                break

            result = resp.json()
            current_data = result.get("data", [])
            all_pages.extend(current_data)
            print(f"[FB_PAGINATION] +{len(current_data)} | Total: {len(all_pages)}")

            paging = result.get("paging", {})
            next_url = paging.get("next")

            if next_url:
                url = next_url
                params = {}
            else:
                url = None
                print("[FB_PAGINATION] Đã lấy hết.")

        if not all_pages:
            return {"success": False, "error": "No pages found for this user."}, 400

        formatted = []
        for p in all_pages:
            if p.get("access_token"):
                formatted.append({
                    "id": str(p.get("id")),
                    "name": p.get("name", "Unknown Page"),
                    "access_token": p.get("access_token"),
                    "category": p.get("category", ""),
                })

        print(f"[FB_PAGINATION] FINAL TOTAL: {len(formatted)} pages")
        return {
            "success": True,
            "message": f"Tìm thấy {len(formatted)} Page",
            "total": len(formatted),
            "pages": formatted
        }, 200

    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500
