import hmac
import hashlib

from utils.config_service import get_runtime_config

def verify_signature(payload, signature, app_secret=None):
    """
    Xác minh chữ ký webhook từ Facebook
    
    Args:
        payload: Request body
        signature: X-Hub-Signature header value
        app_secret: App secret để verify (None = dùng từ env)
    
    Returns:
        bool: True nếu signature hợp lệ
    """
    if not app_secret:
        return True  # Không có secret để verify, bỏ qua
    
    expected = hmac.new(
        app_secret.encode('utf-8'),
        payload,
        hashlib.sha1
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)

def verify_webhook_token(mode, token, challenge):
    """Legacy single-token webhook verification using DB config."""
    verify_token = get_runtime_config('VERIFY_TOKEN', '')
    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return True, challenge
        else:
            return False, 'Verification token mismatch'
    return False, 'Bad request'
