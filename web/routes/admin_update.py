from flask import jsonify

from web.routes import admin_bp
from web.services import update_admin_service


@admin_bp.route("/api/app/update/check", methods=["GET"])
def api_app_update_check():
    result, status = update_admin_service.check_update()
    return jsonify(result), status


@admin_bp.route("/api/app/update", methods=["POST"])
def api_app_update_apply():
    result, status = update_admin_service.apply_update()
    return jsonify(result), status


@admin_bp.route("/api/app/update/status", methods=["GET"])
def api_app_update_status():
    return jsonify(update_admin_service.get_state()), 200
