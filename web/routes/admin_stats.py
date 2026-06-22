from flask import jsonify, render_template, request

from web.routes import admin_bp
from web.services import stats_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/message-stats")
def admin_message_stats():
    context = get_common_context()
    context["active_page"] = "message_stats"
    return render_template("pages/message_stats.html", **context)


@admin_bp.route("/api/pages/<page_id>/message-stats", methods=["GET"])
def api_get_page_message_stats(page_id):
    result, status = stats_admin_service.page_message_stats(page_id, request.args.get("limit", 100, type=int))
    return jsonify(result), status


@admin_bp.route("/api/message-stats", methods=["GET"])
def api_get_all_message_stats():
    result, status = stats_admin_service.all_message_stats()
    return jsonify(result), status


@admin_bp.route("/api/message-stats/top", methods=["GET"])
def api_get_top_senders():
    result, status = stats_admin_service.top_senders(request.args.get("limit", 10, type=int))
    return jsonify(result), status


@admin_bp.route("/api/message-stats/overview", methods=["GET"])
def api_get_message_overview():
    result, status = stats_admin_service.message_overview(
        date_from=request.args.get("date_from") or None,
        date_to=request.args.get("date_to") or None,
        page_id=request.args.get("page_id") or None,
        skill=request.args.get("skill") or None,
    )
    return jsonify(result), status


@admin_bp.route("/api/message-stats/senders/<page_id>/<sender_psid>", methods=["GET"])
def api_get_sender_interaction_detail(page_id, sender_psid):
    result, status = stats_admin_service.sender_interaction_detail(
        page_id,
        sender_psid,
        limit=request.args.get("limit", 50, type=int),
    )
    return jsonify(result), status
