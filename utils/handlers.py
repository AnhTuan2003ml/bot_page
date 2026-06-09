import os
import time
from datetime import datetime

import requests

from brain.pipeline import process_message
from utils.config_service import get_runtime_bool, get_runtime_config
from services.runtime_context import build_runtime_context
from .api_logger import log_facebook_get_name, log_facebook_send_message
from .logger import debug, error, exception, info, warning
from .message_queue import add_to_queue, start_queue_worker
from .runtime_paths import RECEIVED_MESSAGE_LOG_DIR, SENT_MESSAGE_LOG_DIR, ensure_runtime_dirs

_queue_started = False
_sender_first_message = {}

ensure_runtime_dirs()


def get_page_token(page=None):
    debug(f"[FACEBOOK] get_page_token called, page_id={page.get('page_id') if page else 'None'}")
    if page and page.get("page_access_token"):
        return page["page_access_token"]
    return None


def get_page_skill(page=None):
    if page and page.get("ai_skill"):
        return page["ai_skill"]
    return get_runtime_config("AI_SKILL", "friendly")


def get_page_id(page=None):
    if page and page.get("page_id"):
        return str(page["page_id"])
    return "default_page"


def is_first_message(sender_id):
    if sender_id not in _sender_first_message:
        _sender_first_message[sender_id] = True
        return True
    return False


def get_sender_name_from_db(sender_id, page_id=None):
    try:
        from database.message_stats_manager import get_sender_stat
        if page_id:
            sender = get_sender_stat(page_id, sender_id)
            if sender and sender.get("sender_name") and sender["sender_name"] != "Unknown":
                return sender["sender_name"]
    except Exception as exc:
        debug(f"[DB] Error getting sender name from DB: {exc}")
    return None


def get_sender_name(sender_id, page=None):
    page_id = page.get("page_id") if page else None
    cached_name = get_sender_name_from_db(sender_id, page_id)
    if cached_name:
        return cached_name

    token = get_page_token(page)
    if not token:
        warning(f"[FACEBOOK] PAGE_ACCESS_TOKEN not found for page {page_id}")
        return None

    urls = [
        f"https://graph.facebook.com/v19.0/{sender_id}?fields=name&access_token={token}",
        f"https://graph.facebook.com/v19.0/{sender_id}?fields=first_name,last_name&access_token={token}",
    ]
    for url in urls:
        started = time.time()
        try:
            response = requests.get(url, timeout=10)
            duration_ms = int((time.time() - started) * 1000)
            if response.status_code != 200:
                log_facebook_get_name(sender_id, response.status_code, duration_ms, error=response.text[:200])
                continue
            data = response.json()
            name = (data.get("name") or f"{data.get('first_name', '')} {data.get('last_name', '')}").strip()
            if name:
                log_facebook_get_name(sender_id, 200, duration_ms)
                return name
        except requests.exceptions.Timeout:
            log_facebook_get_name(sender_id, 0, int((time.time() - started) * 1000), error="Timeout")
        except Exception as exc:
            log_facebook_get_name(sender_id, 0, int((time.time() - started) * 1000), error=str(exc))
    return None


def get_log_file_path(message_type="received"):
    today = datetime.now().strftime("%Y-%m-%d")
    folder = RECEIVED_MESSAGE_LOG_DIR if message_type == "received" else SENT_MESSAGE_LOG_DIR
    return os.path.join(folder, f"{today}.txt")


def log_message(sender_id, sender_name, message_text, message_type="received"):
    if not get_runtime_bool("ENABLE_FILE_CONVERSATION_LOG", False):
        return
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    name = sender_name if sender_name else sender_id
    clean_text = str(message_text or "").replace("\n", " | ").replace("\r", "")
    with open(get_log_file_path(message_type), "a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {name} | {clean_text}\n")


def _page_config(page):
    return build_runtime_context(page=page, page_id=get_page_id(page))


def _process_message_from_queue(message_data):
    sender_psid = message_data["sender_psid"]
    message_text = message_data["message_text"]
    sender_name = message_data.get("sender_name")
    first_msg = message_data.get("is_first_message", False)
    postback_payload = message_data.get("postback_payload")
    page = message_data.get("page")
    runtime_context = message_data.get("runtime_context")
    if not runtime_context:
        runtime_context = build_runtime_context(
            page=page,
            page_id=message_data.get("page_id"),
            sender_psid=sender_psid,
        )
    page_config = runtime_context

    raw_context = {
        "sender_name": sender_name,
        "runtime_context": runtime_context,
        "is_first_message": first_msg,
        "sender_psid": sender_psid,
        "page_id": page_config["page_id"],
        "page_name": page_config["page_name"],
        "page": runtime_context.get("page") or page,
    }
    if postback_payload:
        raw_context["postback_payload"] = postback_payload

    reply = process_message(
        chat_id=f"{page_config['page_id']}:{sender_psid}",
        user_message=message_text,
        page_config=page_config,
        sender_name=sender_name,
        raw_context=raw_context,
        runtime_context=runtime_context,
    )
    if reply is None:
        warning(f"[QUEUE] Pipeline returned None for {sender_name or sender_psid}")
        return

    info(f"Processed from {sender_name or sender_psid}: {message_text[:50]}...")
    # New Chuyên môn AI flow may return multiple messages separated by persona delimiter.
    delimiter = '---MSG---'
    try:
        import json
        persona = json.loads((runtime_context or {}).get('persona_json') or '{}')
        delimiter = ((persona.get('tach_tin_nhan') or {}).get('delimiter') or delimiter)
    except Exception:
        pass
    parts = [p.strip() for p in str(reply or '').split(delimiter) if p.strip()] if delimiter and delimiter in str(reply or '') else [reply]
    for part in parts:
        send_message(sender_psid, part, sender_name, page=runtime_context.get("page") or page, runtime_context=runtime_context)


def _ensure_queue_started():
    global _queue_started
    if not _queue_started:
        start_queue_worker(_process_message_from_queue)
        _queue_started = True
        info("Message queue worker started")


def handle_message(sender_psid, received_message, page=None):
    page_id = get_page_id(page)
    if received_message.get("is_echo"):
        debug("[WEBHOOK] handle_message skip is_echo")
        return
    if str(sender_psid) == str(page_id):
        debug("[WEBHOOK] handle_message skip sender is page_id")
        return

    _ensure_queue_started()
    if not received_message.get("text"):
        return

    message_text = received_message["text"]
    message_mid = received_message.get("mid")
    sender_name = get_sender_name(sender_psid, page)
    first_msg = is_first_message(sender_psid)
    runtime_context = build_runtime_context(page=page, page_id=page_id, sender_psid=sender_psid)

    log_message(sender_psid, sender_name, message_text, "received")
    info(f"Received from {sender_name or sender_psid}: {message_text[:50]}... (first={first_msg}, page={page_id})")

    try:
        from database.message_stats_manager import record_inbound_message
        record_inbound_message(
            page_id,
            sender_psid,
            sender_name,
            message_mid=message_mid,
            text=message_text,
            runtime_context=runtime_context,
        )
    except Exception as exc:
        debug(f"Failed to record message stats: {exc}")

    add_to_queue({
        "page_id": page_id,
        "sender_psid": sender_psid,
        "message_text": message_text,
        "message_mid": message_mid,
        "sender_name": sender_name,
        "is_first_message": first_msg,
        "runtime_context": runtime_context,
        "page": page,
    })


def handle_postback(sender_psid, postback, page=None):
    _ensure_queue_started()
    payload = postback.get("payload")
    sender_name = get_sender_name(sender_psid, page)
    first_msg = is_first_message(sender_psid)
    page_id = get_page_id(page)
    runtime_context = build_runtime_context(page=page, page_id=page_id, sender_psid=sender_psid)

    log_message(sender_psid, sender_name, f"[Postback: {payload}]", "received")
    info(f"Postback from {sender_name or sender_psid}: {payload} (page={page_id})")

    try:
        from database.message_stats_manager import record_postback
        record_postback(page_id, sender_psid, sender_name, payload=payload, runtime_context=runtime_context)
    except Exception as exc:
        debug(f"Failed to record postback stats: {exc}")

    add_to_queue({
        "page_id": page_id,
        "sender_psid": sender_psid,
        "message_text": f"[Postback: {payload}]",
        "sender_name": sender_name,
        "is_first_message": first_msg,
        "runtime_context": runtime_context,
        "postback_payload": payload,
        "page": page,
    })


def send_message(recipient_id, message_text, sender_name=None, page=None, runtime_context=None):
    runtime_context = runtime_context or {}
    token = runtime_context.get("page_access_token") or get_page_token(page)
    page_id = runtime_context.get("page_id") or get_page_id(page)
    if not token:
        error(f"PAGE_ACCESS_TOKEN is empty for page {page_id}! Cannot send message.")
        try:
            from database.message_stats_manager import record_outbound_message
            record_outbound_message(
                page_id,
                recipient_id,
                sender_name,
                text=message_text,
                runtime_context=runtime_context,
                status="failed",
                error_message="PAGE_ACCESS_TOKEN is empty",
            )
        except Exception as exc:
            debug(f"Failed to record outbound stats: {exc}")
        return

    url = f"https://graph.facebook.com/v18.0/me/messages?access_token={token}"
    payload = {"recipient": {"id": recipient_id}, "message": {"text": message_text}}
    started = time.time()
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        duration_ms = int((time.time() - started) * 1000)
        if response.status_code == 200:
            log_message(recipient_id, sender_name, message_text, "sent")
            log_facebook_send_message(recipient_id, 200, duration_ms)
            info(f"Message sent successfully to {sender_name or recipient_id}")
            try:
                from database.message_stats_manager import record_outbound_message
                record_outbound_message(
                    page_id,
                    recipient_id,
                    sender_name,
                    text=message_text,
                    runtime_context=runtime_context,
                    status="success",
                    send_latency_ms=duration_ms,
                )
            except Exception as exc:
                debug(f"Failed to record outbound stats: {exc}")
        else:
            error_msg = response.text[:300]
            error(f"Facebook API Error {response.status_code}: {error_msg}")
            log_facebook_send_message(recipient_id, response.status_code, duration_ms, error=error_msg)
            try:
                from database.message_stats_manager import record_outbound_message
                record_outbound_message(
                    page_id,
                    recipient_id,
                    sender_name,
                    text=message_text,
                    runtime_context=runtime_context,
                    status="failed",
                    send_latency_ms=duration_ms,
                    error_message=error_msg,
                )
            except Exception as exc:
                debug(f"Failed to record outbound stats: {exc}")
    except Exception as exc:
        duration_ms = int((time.time() - started) * 1000)
        exception(exc)
        log_facebook_send_message(recipient_id, 0, duration_ms, error=str(exc))
        try:
            from database.message_stats_manager import record_outbound_message
            record_outbound_message(
                page_id,
                recipient_id,
                sender_name,
                text=message_text,
                runtime_context=runtime_context,
                status="failed",
                send_latency_ms=duration_ms,
                error_message=str(exc),
            )
        except Exception as stats_exc:
            debug(f"Failed to record outbound stats: {stats_exc}")
