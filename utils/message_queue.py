"""
Message queue system.

Multiple workers may process different conversations in parallel, but messages
from the same page/customer conversation are serialized with a per-conversation
lock so memory, pending state and history stay in order.
"""

import os
import queue
import sys
import threading
import time
from typing import Any, Callable, Dict

# Add parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config_service import get_runtime_config
from utils.logger import debug, error, exception, info


_message_queue = queue.Queue()
_worker_threads = []
_is_running = False
_workers_guard = threading.Lock()

_conversation_locks = {}
_conversation_last_used = {}
_conversation_conditions = {}
_conversation_next_ticket = {}
_conversation_serving_ticket = {}
_locks_guard = threading.Lock()
_LOCK_TTL_SECONDS = 30 * 60

_message_handler: Callable[[Dict[str, Any]], None] = None


def _get_worker_count() -> int:
    try:
        value = int(get_runtime_config("MESSAGE_QUEUE_WORKERS", 3))
        return max(1, min(value, 20))
    except Exception:
        return 3


def _get_conversation_key(message_data):
    message_data = message_data or {}
    page = message_data.get("page") or {}
    page_id = (
        message_data.get("page_id")
        or page.get("page_id")
        or page.get("id")
        or page.get("facebook_page_id")
        or ""
    )

    sender_psid = (
        message_data.get("sender_psid")
        or message_data.get("sender_id")
        or message_data.get("psid")
        or ""
    )

    if page_id and sender_psid:
        return f"{page_id}:{sender_psid}"
    if sender_psid:
        return str(sender_psid)
    return "unknown"


def _get_conversation_lock(conversation_key):
    now = time.time()

    with _locks_guard:
        lock = _conversation_locks.get(conversation_key)
        if lock is None:
            lock = threading.Lock()
            _conversation_locks[conversation_key] = lock
            _conversation_conditions[conversation_key] = threading.Condition()
            _conversation_next_ticket[conversation_key] = 0
            _conversation_serving_ticket[conversation_key] = 0

        _conversation_last_used[conversation_key] = now
        return lock


def _get_conversation_ticket(conversation_key):
    with _locks_guard:
        condition = _conversation_conditions.setdefault(conversation_key, threading.Condition())
        ticket = _conversation_next_ticket.get(conversation_key, 0)
        _conversation_next_ticket[conversation_key] = ticket + 1
        _conversation_serving_ticket.setdefault(conversation_key, 0)
        _conversation_last_used[conversation_key] = time.time()
        return condition, ticket


def _cleanup_conversation_locks():
    now = time.time()

    with _locks_guard:
        stale_keys = [
            key
            for key, last_used in _conversation_last_used.items()
            if now - last_used > _LOCK_TTL_SECONDS
        ]

        for key in stale_keys:
            lock = _conversation_locks.get(key)
            if lock and lock.locked():
                continue

            _conversation_locks.pop(key, None)
            _conversation_last_used.pop(key, None)
            _conversation_conditions.pop(key, None)
            _conversation_next_ticket.pop(key, None)
            _conversation_serving_ticket.pop(key, None)


def start_queue_worker(handler: Callable[[Dict[str, Any]], None]):
    """Start message queue workers once."""
    global _is_running, _message_handler

    with _workers_guard:
        if _is_running:
            return

        _message_handler = handler
        _is_running = True
        worker_count = _get_worker_count()

        for i in range(worker_count):
            worker = threading.Thread(
                target=_process_queue,
                daemon=True,
                name=f"message-worker-{i + 1}",
            )
            worker.start()
            _worker_threads.append(worker)

        info(f"✅ Message queue workers started ({worker_count} workers)")


def _process_queue():
    """Process messages from the global queue."""
    global _is_running

    while _is_running:
        message_data = None
        conversation_key = "unknown"
        try:
            message_data = _message_queue.get(timeout=1)
            conversation_key = _get_conversation_key(message_data)
            lock = _get_conversation_lock(conversation_key)
            condition, ticket = _get_conversation_ticket(conversation_key)

            try:
                debug(f"[QUEUE] conversation_key={conversation_key} waiting_lock")
                with condition:
                    while _conversation_serving_ticket.get(conversation_key, 0) != ticket:
                        condition.wait()

                try:
                    with lock:
                        debug(f"[QUEUE] conversation_key={conversation_key} locked")
                        try:
                            if _message_handler:
                                _message_handler(message_data)
                        finally:
                            debug(f"[QUEUE] conversation_key={conversation_key} released")
                finally:
                    with condition:
                        _conversation_serving_ticket[conversation_key] = ticket + 1
                        condition.notify_all()
            except Exception as exc:
                error(f"[QUEUE] error conversation_key={conversation_key}: {exc}")
            finally:
                _message_queue.task_done()
                debug(f"[QUEUE] Queue size: {_message_queue.qsize()} remaining")
                _cleanup_conversation_locks()
                time.sleep(0.5)

        except queue.Empty:
            continue
        except Exception as exc:
            exception(exc)
            if message_data is not None:
                try:
                    _message_queue.task_done()
                except ValueError:
                    pass


def add_to_queue(message_data: Dict[str, Any]) -> int:
    """
    Add a message to the queue.

    Returns the current approximate queue position.
    """
    _message_queue.put(message_data)
    position = _message_queue.qsize()
    conversation_key = _get_conversation_key(message_data)
    info(f"[QUEUE] Added message conversation_key={conversation_key} position={position}")
    return position


def get_queue_status() -> Dict[str, Any]:
    """Return queue status."""
    alive_count = sum(1 for worker in _worker_threads if worker.is_alive()) if _worker_threads else 0
    return {
        "queue_size": _message_queue.qsize(),
        "is_running": _is_running,
        "num_workers": _get_worker_count(),
        "workers_alive": alive_count,
    }


def stop_queue_worker():
    """Stop all worker threads."""
    global _is_running

    with _workers_guard:
        _is_running = False
        stopped_count = len(_worker_threads)
        for worker in _worker_threads:
            worker.join(timeout=2)
        _worker_threads.clear()

    info(f"🛑 Message queue workers stopped ({stopped_count} workers)")
