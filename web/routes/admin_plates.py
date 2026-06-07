from flask import jsonify, render_template, request

from web.routes import admin_bp
from web.services import plate_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/plates")
def admin_plates():
    context = get_common_context()
    context["active_page"] = "plates"
    return render_template("pages/plates.html", **context)


@admin_bp.route("/api/plates", methods=["GET"])
def api_get_plates():
    result, status = plate_admin_service.list_plates()
    return jsonify(result), status


@admin_bp.route("/api/plates/available", methods=["GET"])
def api_get_available():
    result, status = plate_admin_service.list_available_plates()
    return jsonify(result), status


@admin_bp.route("/api/plates", methods=["POST"])
def api_add_plate():
    result, status = plate_admin_service.create_plate(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/plates/<plate_number>", methods=["PUT"])
def api_update_plate(plate_number):
    result, status = plate_admin_service.update_plate(plate_number, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/plates/<plate_number>", methods=["DELETE"])
def api_delete_plate(plate_number):
    result, status = plate_admin_service.remove_plate(plate_number)
    return jsonify(result), status


@admin_bp.route("/api/stats", methods=["GET"])
def api_get_stats():
    result, status = plate_admin_service.database_stats()
    return jsonify(result), status
