from flask import jsonify, redirect, render_template, request

from web.routes import admin_bp
from web.services import skill_admin_service, skill_data_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/skills")
def admin_skills():
    context = get_common_context()
    context["active_page"] = "skills"
    return render_template("pages/skills.html", **context)


@admin_bp.route("/admin/skill-data")
def admin_skill_data():
    context = get_common_context()
    context["active_page"] = "skill_data"
    selected_skill = request.args.get("skill") or ""
    context.update(skill_data_admin_service.get_skill_data_page_context(selected_skill))
    return render_template("pages/skill_data.html", **context)


@admin_bp.route("/admin/plates")
def legacy_data_redirect():
    return redirect("/admin/skill-data", code=302)


@admin_bp.route("/api/skills", methods=["GET"])
def api_get_skills():
    result, status = skill_admin_service.list_skills()
    return jsonify(result), status


@admin_bp.route("/api/skills/_templates/fields", methods=["GET"])
def api_get_skill_field_templates():
    result, status = skill_admin_service.get_skill_field_templates()
    return jsonify(result), status


@admin_bp.route("/api/skills", methods=["POST"])
def api_add_skill():
    result, status = skill_admin_service.add_skill(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<name>", methods=["PUT"])
def api_update_skill(name):
    result, status = skill_admin_service.update_skill(name, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<name>", methods=["DELETE"])
def api_delete_skill(name):
    result, status = skill_admin_service.delete_skill(name)
    return jsonify(result), status


@admin_bp.route("/api/skills/<name>/toggle", methods=["POST"])
def api_toggle_skill(name):
    result, status = skill_admin_service.toggle_skill(name)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/fields", methods=["GET"])
def api_get_skill_fields(name):
    result, status = skill_data_admin_service.api_get_fields(name)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/fields", methods=["PUT", "POST"])
def api_save_skill_fields(name):
    result, status = skill_data_admin_service.api_save_fields(name, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/items", methods=["GET"])
def api_list_skill_items(name):
    result, status = skill_data_admin_service.api_get_items(name, request.args)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/items", methods=["POST"])
def api_create_skill_item(name):
    result, status = skill_data_admin_service.api_create_item(name, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/items/<path:item_id>", methods=["GET"])
def api_get_skill_item(name, item_id):
    result, status = skill_data_admin_service.api_get_item(name, item_id)
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/items/<path:item_id>", methods=["PUT"])
def api_update_skill_item(name, item_id):
    result, status = skill_data_admin_service.api_update_item(name, item_id, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/skills/<path:name>/items/<path:item_id>", methods=["DELETE"])
def api_delete_skill_item(name, item_id):
    result, status = skill_data_admin_service.api_delete_item(name, item_id)
    return jsonify(result), status
