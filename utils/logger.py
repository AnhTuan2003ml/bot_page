"""Application logger."""

import traceback
from datetime import datetime
from threading import Lock

from utils.runtime_paths import APP_LOG_FILE, ensure_runtime_dirs
from utils.config_service import get_runtime_bool

ensure_runtime_dirs()

_file_lock = Lock()


def _get_log_file():
    return APP_LOG_FILE


def log(level, message, print_console=True):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] [{level}] {message}\n"

    if get_runtime_bool("ENABLE_RUNTIME_FILE_LOG", False):
        with _file_lock:
            try:
                with open(_get_log_file(), "a", encoding="utf-8") as handle:
                    handle.write(log_entry)
            except Exception as exc:
                print(f"[LOGGER ERROR] Cannot write to file: {exc}")

    if print_console:
        try:
            print(log_entry.rstrip())
        except UnicodeEncodeError:
            safe_entry = log_entry.rstrip().encode("ascii", "backslashreplace").decode("ascii")
            print(safe_entry)


def debug(message, print_console=True):
    log("DEBUG", message, print_console)


def info(message, print_console=True):
    log("INFO", message, print_console)


def warning(message, print_console=True):
    log("WARNING", message, print_console)


def error(message, print_console=True):
    log("ERROR", message, print_console)


def exception(exc, print_console=True):
    message = f"{str(exc)}\n{traceback.format_exc()}"
    log("ERROR", message, print_console)
