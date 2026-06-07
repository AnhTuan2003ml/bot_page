from flask import jsonify, redirect, render_template, request

from web.routes import admin_bp
from web.services import page_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin")
def admin_redirect():
    return redirect("/admin/pages")


@admin_bp.route("/admin/dashboard")
def admin_dashboard():
    return redirect("/admin/pages")


@admin_bp.route("/admin/page-config")
def admin_page_config():
    return redirect("/admin/pages")


@admin_bp.route("/admin/pages")
def admin_pages():
    context = get_common_context()
    context["active_page"] = "pages"
    return render_template("pages/dashboard.html", **context)


@admin_bp.route("/api/pages/verify-token", methods=["POST"])
def api_verify_page_token():
    result, status = page_admin_service.verify_page_token(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/pages", methods=["GET"])
def api_list_pages():
    result, status = page_admin_service.list_pages()
    return jsonify(result), status


@admin_bp.route("/api/pages", methods=["POST"])
def api_add_page():
    result, status = page_admin_service.add_page(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/pages/<page_id>", methods=["GET"])
def api_get_page(page_id):
    result, status = page_admin_service.get_page(page_id)
    return jsonify(result), status


@admin_bp.route("/api/pages/<page_id>", methods=["PUT"])
def api_update_page(page_id):
    result, status = page_admin_service.update_page(page_id, request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/pages/<page_id>", methods=["DELETE"])
def api_delete_page(page_id):
    result, status = page_admin_service.delete_page(page_id)
    return jsonify(result), status


@admin_bp.route("/api/pages/<page_id>/toggle", methods=["POST"])
def api_toggle_page(page_id):
    result, status = page_admin_service.toggle_page(page_id)
    return jsonify(result), status


@admin_bp.route("/api/ai-config", methods=["GET"])
def api_get_ai_config():
    result, status = page_admin_service.ai_config()
    return jsonify(result), status
