def list_logs(direction=None, api_type=None, limit=100):
    from utils.api_logger import get_recent_calls

    try:
        calls = get_recent_calls(direction=direction, api_type=api_type, limit=limit)
        return {"success": True, "calls": calls}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def log_stats():
    from utils.api_logger import get_api_stats

    try:
        stats = get_api_stats()
        return {"success": True, "stats": stats}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def clear_logs():
    from utils.api_logger import clear_recent_calls

    try:
        clear_recent_calls()
        return {"success": True, "message": "Logs cache cleared"}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500
