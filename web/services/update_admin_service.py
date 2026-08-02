"""Cập nhật ứng dụng từ GitHub Release qua web UI.

Tải zip release mới nhất, giải nén, ghi đè exe hiện tại và khởi động lại app.
"""

import threading

import updater
from utils.logger import debug

_state = {
    "running": False,
    "status": "idle",  # idle | downloading | extracting | restarting | done | error
    "message": "",
}
_state_lock = threading.Lock()


def _set_state(status, message):
    with _state_lock:
        _state["status"] = status
        _state["message"] = message


def get_state():
    with _state_lock:
        return dict(_state)


def _log(msg):
    debug(msg)
    _set_state(_state["status"], msg)


def check_update():
    """Kiểm tra release mới nhất trên GitHub."""
    release = updater.get_latest_release()
    if not release:
        return {"success": False, "error": "Không lấy được thông tin release từ GitHub."}, 400

    asset = updater.get_zip_asset(release)
    if not asset:
        return {"success": False, "error": "Release không có file .zip để tải."}, 400

    current = updater.get_current_version()
    latest = release.get("tag_name") or release.get("name") or ""
    has_update = bool(latest) and updater.is_newer(latest, current)

    return {
        "success": True,
        "current_version": current,
        "latest_version": latest,
        "has_update": has_update,
        "tag": latest,
        "name": release.get("name"),
        "published_at": release.get("published_at"),
        "asset_name": asset.get("name"),
        "size": asset.get("size"),
        "html_url": release.get("html_url"),
        "zip_url": asset.get("browser_download_url"),
        "body": (release.get("body") or "")[:2000],
    }, 200


def apply_update():
    """Chạy cập nhật trong thread nền, trả về ngay."""
    with _state_lock:
        if _state["running"]:
            return {"success": False, "error": "Đang có tiến trình cập nhật khác."}, 409
        _state["running"] = True
    _set_state("downloading", "Bắt đầu cập nhật...")

    threading.Thread(target=_run_update, daemon=True).start()
    return {"success": True, "message": "Đã bắt đầu cập nhật. App sẽ tự khởi động lại khi xong."}, 200


def _run_update():
    try:
        release = updater.get_latest_release()
        if not release:
            raise RuntimeError("Không lấy được thông tin release từ GitHub.")

        _set_state("downloading", "Đang tải release...")
        target_dir, mode = updater.stage_update(release)
        _set_state("restarting", "Cập nhật xong, khởi động lại app...")

        if mode == "restart":
            updater.launch_update_and_exit()
        else:
            updater.launch_source_update_and_exit()
    except Exception as e:
        debug(f"[UPDATE] Error: {e}")
        _set_state("error", f"Lỗi: {e}")
    finally:
        with _state_lock:
            _state["running"] = False
