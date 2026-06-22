"""API logger for incoming and outgoing calls."""

import json
import os
import re
import time
from datetime import datetime
from threading import Lock

from utils.runtime_paths import INCOMING_API_LOG_DIR, OUTGOING_API_LOG_DIR, ensure_runtime_dirs
from utils.config_service import get_runtime_bool

ensure_runtime_dirs()

_recent_calls = []
_max_recent = 1000
_lock = Lock()


def get_log_file_path(direction="INCOMING"):
    today = datetime.now().strftime("%Y-%m-%d")
    folder = INCOMING_API_LOG_DIR if str(direction).upper() == "INCOMING" else OUTGOING_API_LOG_DIR
    return os.path.join(folder, f"api_{today}.jsonl")


def log_api_call(direction, api_type, endpoint, method="GET", payload=None, response_status=None,
                 response_data=None, duration_ms=None, error=None, extra=None):
    timestamp = datetime.now().isoformat()
    safe_payload = _mask_sensitive_data(payload) if payload else None
    safe_response = _truncate_response(response_data) if response_data else None
    log_entry = {
        "timestamp": timestamp,
        "direction": direction,
        "api_type": api_type,
        "endpoint": endpoint,
        "method": method,
        "payload": safe_payload,
        "response_status": response_status,
        "response_data": safe_response,
        "duration_ms": duration_ms,
        "error": error,
        "extra": extra,
    }

    with _lock:
        _recent_calls.insert(0, log_entry)
        if len(_recent_calls) > _max_recent:
            _recent_calls.pop()

    if get_runtime_bool("ENABLE_RUNTIME_FILE_LOG", False):
        try:
            with open(get_log_file_path(direction), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            print(f"[API_LOGGER] Error writing log: {exc}")

    _print_api_log(log_entry)
    return log_entry


def _mask_sensitive_data(data):
    if not data:
        return None
    if isinstance(data, dict):
        masked = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in ["token", "key", "secret", "password", "auth"]):
                masked[key] = "***MASKED***"
            elif isinstance(value, (dict, list)):
                masked[key] = _mask_sensitive_data(value)
            else:
                masked[key] = value
        return masked
    if isinstance(data, list):
        return [_mask_sensitive_data(item) for item in data]
    if isinstance(data, str):
        return re.sub(r"access_token=[^&\s]*", "access_token=***MASKED***", data)
    return data


def _truncate_response(data, max_length=500):
    if not data:
        return None
    if isinstance(data, str):
        return data[:max_length] + "... [truncated]" if len(data) > max_length else data
    if isinstance(data, dict):
        important_keys = ["id", "name", "choices", "message", "text", "status", "error"]
        truncated = {key: value for key, value in data.items() if key in important_keys}
        if len(truncated) < len(data):
            truncated["_note"] = f"Truncated from {len(data)} fields"
        return truncated
    return data


def _print_api_log(entry):
    direction = entry["direction"]
    api_type = entry["api_type"]
    endpoint = entry["endpoint"]
    method = entry.get("method", "GET")
    status = entry.get("response_status", "-")
    duration = entry.get("duration_ms")
    error = entry.get("error")
    duration_str = f" ({duration}ms)" if duration else ""
    error_str = f" error={error}" if error else ""
    print(f"[API] [{direction}] {method} {api_type} {endpoint} {status}{duration_str}{error_str}")


def get_recent_calls(direction=None, api_type=None, limit=100):
    with _lock:
        calls = _recent_calls.copy()
    if direction:
        calls = [call for call in calls if call["direction"] == direction]
    if api_type:
        calls = [call for call in calls if call["api_type"] == api_type]
    return calls[:limit]


def get_api_stats(time_range_hours=24):
    with _lock:
        calls = _recent_calls.copy()
    stats = {
        "total": len(calls),
        "incoming": len([call for call in calls if call["direction"] == "INCOMING"]),
        "outgoing": len([call for call in calls if call["direction"] == "OUTGOING"]),
        "by_type": {},
        "by_status": {},
        "avg_duration_ms": 0,
        "errors": 0,
    }
    total_duration = 0
    duration_count = 0
    for call in calls:
        api_type = call.get("api_type", "unknown")
        stats["by_type"][api_type] = stats["by_type"].get(api_type, 0) + 1
        status = call.get("response_status", "unknown")
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        duration = call.get("duration_ms")
        if duration:
            total_duration += duration
            duration_count += 1
        if call.get("error") or (status and isinstance(status, int) and status >= 400):
            stats["errors"] += 1
    if duration_count > 0:
        stats["avg_duration_ms"] = round(total_duration / duration_count, 2)
    return stats


def clear_recent_calls():
    with _lock:
        _recent_calls.clear()
    return True


def log_facebook_incoming(payload, sender_id=None):
    return log_api_call("INCOMING", "facebook_webhook", "/webhook", "POST", payload=payload, extra={"sender_id": sender_id})


def log_facebook_get_name(sender_id, status, duration_ms=None, error=None):
    return log_api_call("OUTGOING", "facebook_graph", f"/v19.0/{sender_id}", "GET", response_status=status, duration_ms=duration_ms, error=error, extra={"sender_id": sender_id, "fields": "name"})


def log_facebook_send_message(recipient_id, status, duration_ms=None, error=None):
    return log_api_call("OUTGOING", "facebook_graph", "/v18.0/me/messages", "POST", response_status=status, duration_ms=duration_ms, error=error, extra={"recipient_id": recipient_id})


def log_groq_call(status, duration_ms=None, error=None, model=None):
    return log_api_call("OUTGOING", "groq", "/chat/completions", "POST", response_status=status, duration_ms=duration_ms, error=error, extra={"model": model})


def log_local_llm(endpoint, status, duration_ms=None, error=None, sender_id=None):
    return log_api_call("OUTGOING", "local_llm", endpoint, "POST", response_status=status, duration_ms=duration_ms, error=error, extra={"sender_id": sender_id})
