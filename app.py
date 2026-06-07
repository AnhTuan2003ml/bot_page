import sys
import os
import webbrowser
from flask import Flask, request

try:
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from utils.runtime_paths import ensure_runtime_dirs
from utils.security import verify_signature
from utils.handlers import handle_message, handle_postback
from utils.logger import debug
from utils.api_logger import log_facebook_incoming
from database.config_manager import init_config_table, seed_default_configs
from utils.config_service import load_config_cache, get_runtime_config, get_runtime_bool, get_runtime_int

# Ensure runtime dirs (data, debug, database, etc.) exist next to exe/source
ensure_runtime_dirs()
init_config_table()
print("Config table initialized")
seed_default_configs(overwrite=False)
print("Default configs seeded")
load_config_cache(force=True)
print("Config cache ready")

# Create Flask app with template and static folders
app = Flask(__name__, template_folder='templates', static_folder='static', static_url_path='/static')

# Tắt Flask/Werkzeug logs để console chỉ hiện app logs
import logging

# === TÙY CHỌN 1: TẮT HOÀN TOÀN - chỉ hiện app logs (khuyên dùng) ===
logging.getLogger('werkzeug').disabled = True

# === TÙY CHỌN 2: Chỉ ẩn access log, giữ lại "Running on http://..." ===
# logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Import và khởi tạo database tables
from database.page_manager import init_pages_table
from database.skill_manager import init_skills_table
from database.expertise_manager import init_expertises_table, migrate_old_skills_to_expertises
from database.customer_profile_manager import init_customer_profiles_table
from database.conversation_state_manager import init_conversation_states_table
from database.conversation_manager import init_conversations_table
from database.message_stats_manager import init_message_stats_table
init_pages_table()  # Giữ nguyên logic Page hiện tại
init_expertises_table()
init_skills_table()  # compatibility facade, không seed skill mặc định
migrate_old_skills_to_expertises()
init_customer_profiles_table()
init_conversation_states_table()
init_conversations_table()
init_message_stats_table()  # Khởi tạo bảng thống kê tin nhắn

# Register admin blueprint
from controls import admin_bp
app.register_blueprint(admin_bp)


def verify_webhook_token_multi(mode: str, token: str, challenge: str):
    """
    Xác minh webhook token với multi-page support
    Tìm page có verify_token khớp
    """
    from database.page_manager import get_page_by_verify_token
    
    if mode != 'subscribe':
        return False, 'Invalid mode'
    
    if not token:
        return False, 'Missing verify_token'
    
    # Tìm page có verify_token này
    page = get_page_by_verify_token(token)
    if page:
        return True, challenge
    
    # Fallback: kiểm tra với env (backward compatibility)
    env_token = get_runtime_config("VERIFY_TOKEN", "")
    if token == env_token:
        return True, challenge
    
    return False, 'Token mismatch'


@app.route('/webhook', methods=['GET'])
def verify_webhook():
    """
    Xác minh webhook với Facebook - Multi-page support
    Facebook sẽ gửi GET request với các params:
    - hub.mode: subscribe
    - hub.verify_token: token bạn cung cấp
    - hub.challenge: chuá»—i ngáº«u nhiÃªn cáº§n tráº£ vá»
    """
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    success, result = verify_webhook_token_multi(mode, token, challenge)
    
    if success:
        return result, 200
    else:
        return result, 403 if 'mismatch' in result else 400


@app.route('/webhook', methods=['POST'])
def receive_message():
    """
    Nhận và xử lý tin nhắn từ Messenger - Multi-page support
    Xác định page từ entry['id'] và route đúng page config
    """
    from services.runtime_context import get_cached_app_secrets, get_cached_page
    
    signature = request.headers.get('X-Hub-Signature', '').replace('sha1=', '')
    payload = request.get_data()
    
    # Xác minh chữ ký với tất cả app secrets trong database (multi-app support)
    # Không còn dùng global app secret từ env file - chỉ dùng database
    app_secrets = get_cached_app_secrets()
    
    # Thử verify với tất cả app secrets
    verified = False
    for secret in app_secrets:
        if secret and verify_signature(payload, signature, secret):
            verified = True
            break
    
    if app_secrets and not verified:
        return 'Signature mismatch', 403

    data = request.get_json()
    
    # Log incoming webhook
    sender_id = None
    if data.get('entry'):
        for entry in data.get('entry', []):
            for event in entry.get('messaging', []):
                sender_id = event.get('sender', {}).get('id')
                break
            if sender_id:
                break
    log_facebook_incoming(data, sender_id)
    
    if data.get('object') == 'page':
        for entry in data.get('entry', []):
            # Xác định page_id từ entry
            page_id = str(entry.get('id', ''))
            webhook_event = entry.get('messaging', [])
            
            debug(f"[WEBHOOK] Received event for page_id: {page_id}")
            
            # Lấy page config - chỉ xử lý nếu page đang active
            page = get_cached_page(page_id) if page_id else None
            
            if not page:
                # Page khÃ´ng tá»“n táº¡i hoáº·c inactive - bá» qua
                debug(f"[WEBHOOK] Page {page_id} not found or inactive, skipping messages")
                continue
            
            for event in webhook_event:
                sender_psid = str(event.get('sender', {}).get('id', ''))
                recipient_id = str(event.get('recipient', {}).get('id', ''))
                page_id = str(entry.get('id', ''))
                message = event.get('message')
                
                # Xử lý tin nhắn văn bản với page context
                if message:
                    if message.get('is_echo'):
                        debug(f"[WEBHOOK] Skip echo message from page {page_id}")
                        continue

                    if sender_psid == page_id:
                        debug(f"[WEBHOOK] Skip page self-message sender={sender_psid} page={page_id}")
                        continue

                    if sender_psid == recipient_id:
                        debug(f"[WEBHOOK] Skip invalid self recipient event sender={sender_psid}")
                        continue

                    handle_message(sender_psid, message, page)
                
                # Xử lý postback với page context
                elif event.get('postback'):
                    handle_postback(sender_psid, event['postback'], page)

        return 'EVENT_RECEIVED', 200
    
    return 'Not Found', 404


if __name__ == '__main__':
    # Mở browser tự động sau 2 giây
    def open_browser():
        import time
        time.sleep(2)
        webbrowser.open('http://localhost:5000/admin/pages')
    
    import threading
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("="*60)
    print("AutoBotPanel đang khởi động...")
    print("Mở http://localhost:5000/admin/pages sau 2 giây...")
    print("Hoặc truy cập thủ công: http://localhost:5000/admin/pages")
    print("="*60)
    
    app.run(
        debug=get_runtime_bool("FLASK_DEBUG", True),
        port=get_runtime_int("PORT", 5000),
        use_reloader=False,
    )

