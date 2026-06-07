import threading
import time
from typing import Any, Callable, Optional

try:
    from utils.logger import debug
except Exception:  # pragma: no cover
    def debug(message):
        print(message)


_CACHE = {}
_LOCK = threading.RLock()


def get_or_set(key: str, loader: Callable[[], Any], ttl: int = 300) -> Any:
    now = time.time()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry:
            value, expires_at = entry
            if now < expires_at:
                debug(f"[CACHE_SERVICE] hit key={key}")
                return value
            _CACHE.pop(key, None)

    debug(f"[CACHE_SERVICE] miss key={key}")
    value = loader()
    with _LOCK:
        _CACHE[key] = (value, now + max(1, int(ttl or 1)))
    return value


def get(key: str, default: Optional[Any] = None) -> Any:
    now = time.time()
    with _LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return default
        value, expires_at = entry
        if now < expires_at:
            debug(f"[CACHE_SERVICE] hit key={key}")
            return value
        _CACHE.pop(key, None)
    return default


def set(key: str, value: Any, ttl: int = 300) -> bool:
    with _LOCK:
        _CACHE[key] = (value, time.time() + max(1, int(ttl or 1)))
    return True


def delete(key: str) -> bool:
    with _LOCK:
        _CACHE.pop(key, None)
    debug(f"[CACHE_SERVICE] delete key={key}")
    return True


def delete_prefix(prefix: str) -> bool:
    with _LOCK:
        keys = [key for key in _CACHE if str(key).startswith(prefix)]
        for key in keys:
            _CACHE.pop(key, None)
    debug(f"[CACHE_SERVICE] delete_prefix prefix={prefix} count={len(keys)}")
    return True


def clear_all() -> bool:
    with _LOCK:
        count = len(_CACHE)
        _CACHE.clear()
    debug(f"[CACHE_SERVICE] clear_all count={count}")
    return True
