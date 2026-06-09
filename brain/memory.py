import json
import os
import re
import shutil
from datetime import datetime

try:
    from utils.runtime_paths import get_base_dir
except Exception:  # pragma: no cover
    def get_base_dir():
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from utils.config_service import get_runtime_bool, get_runtime_int

from .common_intents import normalize_text

MAX_HISTORY_PER_USER = 100
_MEMORY_CACHE = {}


def _file_memory_enabled():
    return get_runtime_bool("ENABLE_FILE_CONVERSATION_LOG", False)


def _now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def get_conversations_dir():
    # Legacy file-memory path is intentionally disabled.
    # Runtime conversation history is stored in SQLite table `conversations`.
    return os.path.join(get_base_dir(), "database")


def safe_chat_id(chat_id):
    value = re.sub(r"[^A-Za-z0-9_-]", "_", str(chat_id or "__global__")).strip("_")
    return value or "__global__"


def get_chat_memory_path(chat_id):
    return os.path.join(get_conversations_dir(), f"{safe_chat_id(chat_id)}.json")


def default_chat_memory(chat_id):
    now = _now_iso()
    return {
        "chat_id": str(chat_id or "__global__"),
        "customer": {
            "name": "",
            "gender": "unknown",
            "gender_confidence": 0.0,
            "pronoun": "mình",
            "first_seen": now,
            "last_seen": now,
            "notes": [],
        },
        "messages": [],
        "state": {"current_domain": "plate_sales", "plate_sales": {}, "generic_sales": {}},
        "pending": {},
    }


def _normalize_memory(chat_id, memory):
    base = default_chat_memory(chat_id)
    if not isinstance(memory, dict):
        return base
    base.update({k: v for k, v in memory.items() if k in {"chat_id", "customer", "messages", "state", "pending"}})
    if "pending_search" in memory and not base.get("pending"):
        base["pending"] = memory.get("pending_search") or {}
    if not isinstance(base.get("messages"), list):
        base["messages"] = []
    if not isinstance(base.get("customer"), dict):
        base["customer"] = default_chat_memory(chat_id)["customer"]
    else:
        merged = default_chat_memory(chat_id)["customer"]
        merged.update(base["customer"])
        base["customer"] = merged
    if not isinstance(base.get("state"), dict):
        base["state"] = default_chat_memory(chat_id)["state"]
    else:
        state = default_chat_memory(chat_id)["state"]
        state.update(base["state"])
        base["state"] = state
    if not isinstance(base.get("pending"), dict):
        base["pending"] = {}
    return base


def load_memory(chat_id):
    if not _file_memory_enabled():
        return _normalize_memory(chat_id, _MEMORY_CACHE.get(str(chat_id or "__global__")))
    path = get_chat_memory_path(chat_id)
    if not os.path.exists(path):
        return default_chat_memory(chat_id)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return _normalize_memory(chat_id, json.load(handle))
    except json.JSONDecodeError:
        try:
            shutil.move(path, path + ".corrupt")
        except Exception:
            pass
        return default_chat_memory(chat_id)
    except Exception as exc:
        print(f"[MEMORY] load error={exc}")
        return default_chat_memory(chat_id)


def save_memory(chat_id, memory):
    if not _file_memory_enabled():
        _MEMORY_CACHE[str(chat_id or "__global__")] = _normalize_memory(chat_id, memory)
        return True
    path = get_chat_memory_path(chat_id)
    memory = _normalize_memory(chat_id, memory)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(memory, handle, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def update_customer_in_memory(memory, chat_id, name=None, pronoun=None, gender=None, **kwargs):
    customer = memory.setdefault("customer", default_chat_memory(chat_id)["customer"])
    customer.pop("name", None)
    customer.pop("pronoun", None)
    customer.pop("gender", None)
    customer.pop("gender_confidence", None)
    customer.pop("notes", None)
    customer["last_seen"] = _now_iso()
    return dict(customer)
    if name:
        customer["name"] = name
        customer["pronoun"] = pronoun or customer.get("pronoun") or _infer_pronoun(name)
    if pronoun:
        customer["pronoun"] = pronoun
    if gender:
        customer["gender"] = gender
    customer.update({k: v for k, v in kwargs.items() if v is not None})
    customer["last_seen"] = _now_iso()
    return dict(customer)


def append_message_to_memory(memory, chat_id, role, content):
    if role not in {"user", "assistant"} or not content:
        return False
    messages = memory.setdefault("messages", [])
    if messages and messages[-1].get("role") == role and messages[-1].get("content") == content:
        return False
    messages.append({"role": role, "content": content, "timestamp": _now_iso()})
    max_messages = get_runtime_int("CONVERSATION_MAX_MESSAGES", MAX_HISTORY_PER_USER)
    memory["messages"] = messages[-max_messages:]
    memory.setdefault("customer", default_chat_memory(chat_id)["customer"])["last_seen"] = _now_iso()
    return True


def update_state_in_memory(memory, domain_name, state_update):
    state = memory.setdefault("state", {})
    state["current_domain"] = domain_name
    domain_state = state.setdefault(domain_name, {})
    if isinstance(state_update, dict):
        for key, value in state_update.items():
            if value not in (None, "", [], {}, 0):
                domain_state[key] = value
    return dict(domain_state)


def set_pending_in_memory(memory, key, value=None):
    pending = memory.setdefault("pending", {})
    if isinstance(key, dict) and value is None:
        pending.update(key)
    else:
        pending[key] = value
    return pending


def clear_pending_in_memory(memory, key=None):
    if key is None:
        memory["pending"] = {}
    else:
        memory.setdefault("pending", {}).pop(key, None)
    return memory.setdefault("pending", {})


def append_message(chat_id, role, content, page_id=None):
    if role not in {"user", "assistant"} or not content:
        return
    memory = load_memory(chat_id)
    changed = append_message_to_memory(memory, chat_id, role, content)
    if not changed:
        return
    save_memory(chat_id, memory)


def get_history(chat_id, page_id=None, limit=12):
    messages = load_memory(chat_id).get("messages", [])
    return messages[-limit:] if limit and len(messages) > limit else list(messages)


def format_history_for_prompt(chat_id, page_id=None, limit=12):
    lines = []
    for item in get_history(chat_id, limit=limit):
        role = "Khách" if item.get("role") == "user" else "Bot"
        content = (item.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(chưa có lịch sử)"


def _infer_pronoun(name):
    norm = normalize_text(name or "")
    if any(w in norm.split() for w in ["thi", "ngoc", "thu", "huong", "trang", "linh", "mai", "lan", "vy"]):
        return "chị"
    if any(w in norm.split() for w in ["van", "huu", "duc", "minh", "tuan", "hung", "nam", "long"]):
        return "anh"
    return "mình"


def update_customer(chat_id, name=None, pronoun=None, gender=None, **kwargs):
    memory = load_memory(chat_id)
    customer = update_customer_in_memory(memory, chat_id, name=name, pronoun=pronoun, gender=gender, **kwargs)
    save_memory(chat_id, memory)
    return dict(customer)


def get_customer(chat_id):
    return dict(load_memory(chat_id).get("customer") or {})


def update_state(chat_id, domain_name, state_update):
    memory = load_memory(chat_id)
    domain_state = update_state_in_memory(memory, domain_name, state_update)
    save_memory(chat_id, memory)
    return dict(domain_state)


def get_domain_state(chat_id, domain_name):
    return dict(load_memory(chat_id).get("state", {}).get(domain_name, {}) or {})


def set_pending(chat_id, key, value=None, page_id=None):
    memory = load_memory(chat_id)
    set_pending_in_memory(memory, key, value)
    save_memory(chat_id, memory)


def get_pending(chat_id, key=None, page_id=None):
    pending = dict(load_memory(chat_id).get("pending") or {})
    return pending.get(key) if key else pending


def clear_pending(chat_id, key=None, page_id=None):
    memory = load_memory(chat_id)
    clear_pending_in_memory(memory, key)
    save_memory(chat_id, memory)


def load_chat_memory(chat_id):
    return load_memory(chat_id)


def save_chat_memory(chat_id, memory):
    return save_memory(chat_id, memory)


def get_customer_profile(chat_id):
    return get_customer(chat_id)


def update_customer_profile(chat_id, **kwargs):
    return update_customer(chat_id, **kwargs)


def get_pending_search(chat_id, page_id=None):
    return get_pending(chat_id)


def set_pending_search(chat_id, pending, page_id=None):
    return set_pending(chat_id, pending)


def clear_pending_search(chat_id, page_id=None):
    return clear_pending(chat_id)


def migrate_legacy_memory():
    if not _file_memory_enabled():
        return 0
    legacy_path = os.path.join(get_base_dir(), "data", "conversation_memory.json")
    if not os.path.exists(legacy_path):
        return 0
    try:
        with open(legacy_path, "r", encoding="utf-8") as handle:
            legacy = json.load(handle)
    except Exception:
        return 0
    count = 0
    if isinstance(legacy, dict):
        for chat_id, entry in legacy.items():
            memory = default_chat_memory(chat_id)
            if isinstance(entry, list):
                memory["messages"] = [m for m in entry if isinstance(m, dict)]
            elif isinstance(entry, dict):
                memory["messages"] = [m for m in (entry.get("messages") or entry.get("history") or []) if isinstance(m, dict)]
                if isinstance(entry.get("customer"), dict):
                    memory["customer"].update(entry["customer"])
                if isinstance(entry.get("state"), dict):
                    memory["state"]["plate_sales"].update(entry["state"])
                pending = entry.get("pending") or entry.get("pending_search")
                if isinstance(pending, dict):
                    memory["pending"].update(pending)
            save_memory(chat_id, memory)
            count += 1
    if count:
        try:
            os.replace(legacy_path, legacy_path + ".migrated")
        except Exception:
            pass
    return count


try:
    migrate_legacy_memory()
except Exception as exc:
    print(f"[MEMORY_MIGRATE] error={exc}")
