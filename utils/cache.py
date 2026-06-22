import os
import sys
import time
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logger import debug, info


class Cache:
    """Small in-memory cache kept for backward compatibility."""

    def __init__(self):
        self._memory_cache = {}
        info("In-memory cache ready")

    def get(self, key: str) -> Optional[Any]:
        entry = self._memory_cache.get(key)
        if not entry:
            return None
        value, expiry = entry
        if time.time() < expiry:
            return value
        self._memory_cache.pop(key, None)
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> bool:
        try:
            self._memory_cache[key] = (value, time.time() + ttl_seconds)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            self._memory_cache.pop(key, None)
            return True
        except Exception:
            return False

    def clear(self) -> bool:
        try:
            self._memory_cache.clear()
            return True
        except Exception:
            return False


cache = Cache()

