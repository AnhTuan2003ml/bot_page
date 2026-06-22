from flask import jsonify, redirect, render_template, request

from web.routes import admin_bp
from web.services import skill_data_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/data")
def admin_data_redirect():
    return redirect("/admin/skill-data")


@admin_bp.route("/admin/skill-data")
def admin_skill_data_index():
    context = get_common_context()
    context["active_page"] = "data"
    selected_skill = request.args.get("skill") or ""
    context.update(skill_data_admin_service.get_skill_data_page_context(selected_skill))
    return render_template("pages/skill_data.html", **context)


@admin_bp.route("/admin/skills/<path:skill_name>/data")
def admin_skill_data_legacy(skill_name):
    return redirect(f"/admin/skill-data?skill={skill_name}")


@admin_bp.route("/api/skills/<path:skill_name>/fields", methods=["GET"])
def api_skill_fields(skill_name):
    result, status = skill_data_admin_service.api_get_fields(skill_name)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/fields", methods=["POST"])
def api_save_skill_fields(skill_name):
    result, status = skill_data_admin_service.api_save_fields(skill_name, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/items", methods=["GET"])
def api_skill_items(skill_name):
    result, status = skill_data_admin_service.api_get_items(skill_name, request.args)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/items", methods=["POST"])
def api_create_skill_item(skill_name):
    result, status = skill_data_admin_service.api_create_item(skill_name, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/items/<path:item_id>", methods=["GET"])
def api_get_skill_item(skill_name, item_id):
    result, status = skill_data_admin_service.api_get_item(skill_name, item_id)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/items/<path:item_id>", methods=["PUT"])
def api_update_skill_item(skill_name, item_id):
    result, status = skill_data_admin_service.api_update_item(skill_name, item_id, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:skill_name>/items/<path:item_id>", methods=["DELETE"])
def api_delete_skill_item(skill_name, item_id):
    result, status = skill_data_admin_service.api_delete_item(skill_name, item_id)
    return jsonify(result), status
