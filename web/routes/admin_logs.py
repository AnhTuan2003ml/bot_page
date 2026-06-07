from flask import jsonify, render_template, request

from web.routes import admin_bp
from web.services import log_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/api-logs")
def admin_api_logs():
    context = get_common_context()
    context["active_page"] = "api_logs"
    return render_template("pages/api_logs.html", **context)


@admin_bp.route("/api/logs", methods=["GET"])
def api_get_logs():
    result, status = log_admin_service.list_logs(
        direction=request.args.get("direction"),
        api_type=request.args.get("api_type"),
        limit=request.args.get("limit", 100, type=int),
    )
    return jsonify(result), status


@admin_bp.route("/api/logs/stats", methods=["GET"])
def api_get_logs_stats():
    result, status = log_admin_service.log_stats()
    return jsonify(result), status


@admin_bp.route("/api/logs/clear", methods=["POST"])
def api_clear_logs():
    result, status = log_admin_service.clear_logs()
    return jsonify(result), status
