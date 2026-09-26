"""
Test script: đăng thử 1 video công khai (Reel) lên Facebook Page bằng Meta Graph API.

Tái sử dụng data layer hiện có của project:
    database.page_manager.get_page(page_id)  -> lấy page_access_token từ bảng `pages` (SQLite).

Không tạo DB connection mới, không hard-code token/page_id.

Cách chạy (từ thư mục gốc project):
    python scripts/test_facebook_reel.py

Chỉnh PAGE_DB_ID, VIDEO_PATH, CAPTION, TITLE ở khối CONFIG bên dưới.
"""

import os
import sys
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import requests

from database.page_manager import get_page

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============================== CONFIG ==============================

# ID page theo model hiện tại của project.
# Bảng `pages` dùng cột `page_id` (Facebook Page ID, TEXT UNIQUE) làm định danh.
# Điền đúng Facebook Page ID đang lưu trong DB, ví dụ: "123456789012345".
PAGE_DB_ID = "1206099119248024"

# Đường dẫn video test.
VIDEO_PATH = r"D:\Project\Project\chatgpt\bot_fb\snaptik.vn_7686035161720376596.mp4"

TITLE = "Video test"

CAPTION = """Caption test đăng video tự động lên Facebook Page.
#test"""

# Project chưa có constant Graph API version trung tâm -> đặt 1 chỗ duy nhất cho dễ đổi.
# (Project hiện dùng rải rác v18.0/v19.0/v25.0; chọn v25.0 là bản mới nhất đang dùng.)
GRAPH_API_VERSION = "v25.0"
GRAPH_BASE = "https://graph.facebook.com"

# Giới hạn thời gian chờ Meta xử lý video.
PROCESSING_TIMEOUT_SECONDS = 300
PROCESSING_POLL_INTERVAL_SECONDS = 5

# ====================================================================


def mask_token(token):
    """Che token khi in ra console: EAAB******xyz"""
    if not token:
        return "(empty)"
    token = str(token)
    if len(token) <= 10:
        return token[:2] + "******" + token[-2:]
    return token[:4] + "******" + token[-4:]


def log(msg):
    print(msg, flush=True)


def graph_error_text(resp):
    """Trích error fields Meta trả về. Không bao giờ chứa access_token."""
    try:
        data = resp.json()
    except Exception:
        return "HTTP %s\nmessage: %s" % (resp.status_code, (resp.text or "")[:500])

    err = (data or {}).get("error") or {}
    return (
        "HTTP Status: %s\n"
        "message: %s\n"
        "type: %s\n"
        "code: %s\n"
        "error_subcode: %s\n"
        "fbtrace_id: %s"
    ) % (
        resp.status_code,
        err.get("message", ""),
        err.get("type", ""),
        err.get("code", ""),
        err.get("error_subcode", ""),
        err.get("fbtrace_id", ""),
    )


def parse_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def load_page():
    if not PAGE_DB_ID or not str(PAGE_DB_ID).strip():
        raise SystemExit(
            "ERROR: chưa cấu hình PAGE_DB_ID. "
            "Điền Facebook Page ID (cột `page_id` trong bảng pages) ở đầu file."
        )

    page_id = str(PAGE_DB_ID).strip()
    log("[1/5] Đọc thông tin Page từ project...")
    page = get_page(page_id)
    if not page:
        raise SystemExit(
            "ERROR: không tìm thấy page_id=%s (active) trong bảng pages." % page_id
        )

    page_access_token = page.get("page_access_token") or ""
    if not page_access_token:
        raise SystemExit("ERROR: page_id=%s không có page_access_token trong DB." % page_id)

    # Project chỉ chạy Facebook (bot_fb), bảng pages không có cột platform.
    log("      - Facebook Page: %s" % page.get("page_name"))
    log("      - Facebook Page ID: %s" % page.get("page_id"))
    log("      - Page Access Token: %s" % mask_token(page_access_token))
    return page, page_access_token


def validate_video():
    if not os.path.isfile(VIDEO_PATH):
        raise SystemExit("ERROR: video không tồn tại: %s" % VIDEO_PATH)
    if not os.access(VIDEO_PATH, os.R_OK):
        raise SystemExit("ERROR: không đọc được video: %s" % VIDEO_PATH)

    ext = os.path.splitext(VIDEO_PATH)[1].lower()
    if ext not in {".mp4", ".mov", ".m4v"}:
        raise SystemExit("ERROR: extension không hợp lệ cho Reel: %s" % ext)

    size = os.path.getsize(VIDEO_PATH)
    if size <= 0:
        raise SystemExit("ERROR: video rỗng: %s" % VIDEO_PATH)
    return size


def verify_page_token(fb_page_id, token):
    log("[2/5] Kiểm tra Page Access Token...")
    url = "%s/%s/%s" % (GRAPH_BASE, GRAPH_API_VERSION, fb_page_id)
    resp = requests.get(
        url,
        params={"fields": "id,name", "access_token": token},
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit("ERROR: verify page token thất bại:\n%s" % graph_error_text(resp))

    data = parse_json(resp)
    returned_id = str(data.get("id", ""))
    if returned_id != str(fb_page_id):
        raise SystemExit(
            "ERROR: Facebook Page ID không khớp. DB=%s, API=%s" % (fb_page_id, returned_id)
        )
    log("      - Token hợp lệ cho Page: %s (%s)" % (data.get("name"), returned_id))
    return data


def start_upload(token):
    log("[3/5] Khởi tạo upload...")
    url = "%s/%s/me/video_reels" % (GRAPH_BASE, GRAPH_API_VERSION)
    resp = requests.post(
        url,
        params={"access_token": token, "upload_phase": "start"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit("ERROR: start upload thất bại:\n%s" % graph_error_text(resp))

    data = parse_json(resp)
    video_id = data.get("video_id")
    upload_url = data.get("upload_url")
    if not video_id or not upload_url:
        raise SystemExit("ERROR: start response thiếu video_id/upload_url: %s" % json.dumps(data))
    log("      - video_id: %s" % video_id)
    return video_id, upload_url


def upload_video(upload_url, token, file_size):
    log("[4/5] Upload video...")
    with open(VIDEO_PATH, "rb") as f:
        resp = requests.post(
            upload_url,
            headers={
                "Authorization": "OAuth %s" % token,
                "offset": "0",
                "file_size": str(file_size),
                "Content-Type": "application/octet-stream",
            },
            data=f,
            timeout=600,
        )
    if resp.status_code != 200:
        raise SystemExit("ERROR: upload video thất bại:\n%s" % graph_error_text(resp))

    data = parse_json(resp)
    if data.get("success") is False:
        raise SystemExit("ERROR: upload video thất bại: %s" % json.dumps(data))
    log("      - Upload xong (%s bytes)" % file_size)
    return data


def finish_publish(video_id, token):
    log("[5/5] Publish video...")
    url = "%s/%s/me/video_reels" % (GRAPH_BASE, GRAPH_API_VERSION)
    resp = requests.post(
        url,
        params={
            "access_token": token,
            "video_id": video_id,
            "upload_phase": "finish",
            "video_state": "PUBLISHED",
            "description": CAPTION,
            "title": TITLE,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise SystemExit("ERROR: publish thất bại:\n%s" % graph_error_text(resp))

    data = parse_json(resp)
    if data.get("success") is False:
        raise SystemExit("ERROR: publish thất bại: %s" % json.dumps(data))
    return data


def wait_for_processing(video_id, token):
    """Chờ Meta xử lý video, tối đa PROCESSING_TIMEOUT_SECONDS."""
    url = "%s/%s/%s" % (GRAPH_BASE, GRAPH_API_VERSION, video_id)
    deadline = time.time() + PROCESSING_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            resp = requests.get(
                url,
                params={"fields": "status,permalink_url", "access_token": token},
                timeout=30,
            )
        except Exception as exc:
            log("      - Poll trạng thái lỗi tạm thời: %s" % exc)
            time.sleep(PROCESSING_POLL_INTERVAL_SECONDS)
            continue

        data = parse_json(resp)
        status = data.get("status") or {}
        video_status = status.get("video_status")
        log("      - video_status: %s" % video_status)

        if video_status == "ready":
            return data
        if video_status == "error":
            raise SystemExit(
                "ERROR: Meta xử lý video lỗi: %s" % json.dumps(status, ensure_ascii=False)
            )
        time.sleep(PROCESSING_POLL_INTERVAL_SECONDS)

    log("      - Hết thời gian chờ xử lý; video có thể vẫn đang processing.")
    return {}


def main():
    page, token = load_page()
    file_size = validate_video()
    log("      - Video: %s (%s bytes)" % (VIDEO_PATH, file_size))

    verify_page_token(page.get("page_id"), token)

    video_id, upload_url = start_upload(token)
    upload_video(upload_url, token, file_size)
    finish_publish(video_id, token)

    status_data = wait_for_processing(video_id, token)
    permalink = status_data.get("permalink_url") or ""
    if permalink.startswith("/"):
        permalink = "https://www.facebook.com" + permalink
    if not permalink:
        permalink = "https://www.facebook.com/reel/%s" % video_id

    print("")
    print("========================================")
    print("FACEBOOK REEL PUBLISHED")
    print("========================================")
    print("Database Page ID: %s" % page.get("page_id"))
    print("Facebook Page: %s" % page.get("page_name"))
    print("Facebook Page ID: %s" % page.get("page_id"))
    print("Video ID: %s" % video_id)
    print("Caption: %s" % CAPTION)
    print("Status: PUBLISHED")
    print("URL: %s" % permalink)
    print("========================================")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except requests.exceptions.RequestException as exc:
        raise SystemExit("ERROR: lỗi network khi gọi Meta Graph API: %s" % exc)
    except Exception as exc:
        raise SystemExit("ERROR: %s: %s" % (type(exc).__name__, exc))
