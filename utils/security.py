import hmac
import hashlib

from utils.config_service import get_runtime_config

def verify_signature(payload, signature=None, signature256=None, app_secret=None):
    """
    Xác minh chữ ký webhook từ Facebook (hỗ trợ cả SHA1 và SHA256).

    Args:
        payload: Request body
        signature: Giá trị X-Hub-Signature (sha1) sau khi đã bỏ tiền tố 'sha1='
        signature256: Giá trị X-Hub-Signature-256 (sha256) sau khi đã bỏ tiền tố 'sha256='
        app_secret: App secret để verify (None = dùng từ env)

    Returns:
        bool: True nếu một trong hai chữ ký hợp lệ
    """
    if not app_secret:
        return True  # Không có secret để verify, bỏ qua

    if signature:
        expected = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha1
        ).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True

    if signature256:
        expected256 = hmac.new(
            app_secret.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(expected256, signature256):
            return True

    return False

def verify_webhook_token(mode, token, challenge):
    """Legacy single-token webhook verification using DB config."""
    verify_token = get_runtime_config('VERIFY_TOKEN', '')
    if mode and token:
        if mode == 'subscribe' and token == verify_token:
            return True, challenge
        else:
            return False, 'Verification token mismatch'
    return False, 'Bad request'
