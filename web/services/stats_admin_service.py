def page_message_stats(page_id, limit=100):
    from database.message_stats_manager import get_page_stats

    try:
        stats = get_page_stats(page_id, limit=limit)
        return {"success": True, "stats": stats}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def all_message_stats():
    from database.message_stats_manager import get_all_pages_stats

    try:
        stats = get_all_pages_stats()
        return {"success": True, "stats": stats}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def top_senders(limit=10):
    from database.message_stats_manager import get_top_senders

    try:
        senders = get_top_senders(limit)
        return {"success": True, "senders": senders}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def message_overview(date_from=None, date_to=None, page_id=None, skill=None):
    from database.message_stats_manager import (
        get_message_events,
        get_message_overview,
        get_page_stats_summary,
        get_rag_stats,
        get_top_interactors,
        get_top_actions,
        get_top_intents,
    )

    try:
        page_names = _page_name_map()
        top_interactors = get_top_interactors(date_from, date_to, page_id, skill, limit=50)
        for item in top_interactors:
            item["page_name"] = page_names.get(item.get("page_id"), "")
        page_stats = get_page_stats_summary(date_from, date_to, page_id, skill)
        for item in page_stats:
            item["page_name"] = page_names.get(item.get("page_id"), "")
        return {
            "success": True,
            "overview": get_message_overview(date_from, date_to, page_id, skill),
            "top_interactors": top_interactors,
            "page_stats": page_stats,
            "advanced": {
                "top_actions": get_top_actions(date_from, date_to, page_id, skill, limit=10),
                "top_intents": get_top_intents(date_from, date_to, page_id, skill, limit=10),
                "rag": get_rag_stats(date_from, date_to, page_id, skill),
                "recent_events": get_message_events(date_from, date_to, page_id, skill, limit=50),
            },
        }, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def sender_interaction_detail(page_id, sender_psid, limit=50):
    from database.message_stats_manager import get_sender_interaction_detail

    try:
        detail = get_sender_interaction_detail(page_id, sender_psid, limit=limit)
        detail["page_name"] = _page_name_map().get(page_id, "")
        return {"success": True, "detail": detail}, 200
    except Exception as exc:
        return {"success": False, "error": str(exc)}, 500


def _page_name_map():
    try:
        from database.page_manager import get_all_pages
        return {str(page.get("page_id")): page.get("page_name") or "" for page in get_all_pages()}
    except Exception:
        return {}
