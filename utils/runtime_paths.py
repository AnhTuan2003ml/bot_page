import os
import sys
import shutil


def get_base_dir():
    """
    Khi cháº¡y source: tráº£ vá» thÆ° má»¥c root project.
    Khi cháº¡y exe PyInstaller: tráº£ vá» thÆ° má»¥c chá»©a file .exe.
    TUYá»†T Äá»I khÃ´ng tráº£ vá» thÆ° má»¥c _MEI táº¡m.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_bundle_dir():
    """
    Thư mục chứa resource được PyInstaller giải nén (_MEI...) nếu chạy onefile.
    Chỉ dùng để COPY file mẫu ra ngoài runtime, không ghi config vào đây.
    """
    return getattr(sys, "_MEIPASS", get_base_dir())


def get_runtime_path(*parts):
    """Path ngoài runtime, cùng cấp exe/source."""
    return os.path.join(get_base_dir(), *parts)


def get_bundled_path(*parts):
    """Path resource trong bundle PyInstaller/source."""
    return os.path.join(get_bundle_dir(), *parts)


def _copy_if_missing(src, dst):
    try:
        if os.path.exists(dst):
            return False
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            print(f"[RUNTIME] Copied default resource: {src} -> {dst}")
            return True
    except Exception as e:
        print(f"[RUNTIME] Failed to copy resource {src} -> {dst}: {e}")
    return False


DEBUG_DIR = get_runtime_path("debug")
APP_LOG_FILE = os.path.join(DEBUG_DIR, "app.log")
API_LOG_DIR = os.path.join(DEBUG_DIR, "api")
INCOMING_API_LOG_DIR = os.path.join(API_LOG_DIR, "incoming")
OUTGOING_API_LOG_DIR = os.path.join(API_LOG_DIR, "outgoing")
MESSAGE_LOG_DIR = os.path.join(DEBUG_DIR, "messages")
RECEIVED_MESSAGE_LOG_DIR = os.path.join(MESSAGE_LOG_DIR, "received")
SENT_MESSAGE_LOG_DIR = os.path.join(MESSAGE_LOG_DIR, "sent")
ERROR_LOG_DIR = os.path.join(DEBUG_DIR, "errors")
QUEUE_LOG_DIR = os.path.join(DEBUG_DIR, "queue")


def ensure_runtime_dirs():
    """
    Tạo các thư mục runtime ngoài exe nếu cần.
    """
    for path in [
        get_runtime_path("database"),
        DEBUG_DIR,
        API_LOG_DIR,
        INCOMING_API_LOG_DIR,
        OUTGOING_API_LOG_DIR,
        MESSAGE_LOG_DIR,
        RECEIVED_MESSAGE_LOG_DIR,
        SENT_MESSAGE_LOG_DIR,
        ERROR_LOG_DIR,
        QUEUE_LOG_DIR,
    ]:
        os.makedirs(path, exist_ok=True)


def ensure_domain_knowledge_base(domain_name):
    # Legacy domain knowledge files are no longer part of runtime.
    return None

