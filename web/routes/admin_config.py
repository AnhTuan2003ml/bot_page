from flask import jsonify, render_template, request

from database.config_manager import get_admin_configs
from web.routes import admin_bp
from web.services import config_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/settings")
def admin_settings():
    context = get_common_context()
    context["active_page"] = "settings"
    context["config"] = get_admin_configs()
    return render_template("pages/settings.html", **context)


@admin_bp.route("/api/config/token", methods=["GET"])
def api_get_token():
    result, status = config_admin_service.token_info()
    return jsonify(result), status


@admin_bp.route("/api/config/token", methods=["POST"])
def api_set_token():
    result, status = config_admin_service.update_token(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/config/app-id", methods=["POST"])
def api_set_app_id():
    result, status = config_admin_service.update_app_id(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/config/app-secret", methods=["POST"])
def api_set_app_secret():
    result, status = config_admin_service.update_app_secret(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/config", methods=["GET"])
def api_get_full_config():
    result, status = config_admin_service.full_config()
    return jsonify(result), status


@admin_bp.route("/api/config", methods=["POST"])
def api_update_full_config():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form.to_dict() if request.form else {}
    result, status = config_admin_service.update_full_config(data, request.content_type)
    return jsonify(result), status
