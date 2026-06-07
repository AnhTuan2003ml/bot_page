from flask import jsonify, render_template, request

from web.routes import admin_bp
from web.services import ai_admin_service
from web.services.common_admin_service import get_common_context


@admin_bp.route("/admin/ai-service")
def admin_ai_service():
    context = get_common_context()
    context["active_page"] = "ai-service"
    return render_template("pages/ai-service.html", **context)


@admin_bp.route("/api/ai/provider", methods=["GET"])
def api_get_provider():
    result, status = ai_admin_service.provider_info()
    return jsonify(result), status


@admin_bp.route("/api/ai/provider", methods=["POST"])
def api_set_provider():
    result, status = ai_admin_service.set_provider(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/ai/intent-provider", methods=["GET"])
def api_get_intent_provider():
    result, status = ai_admin_service.intent_provider_info()
    return jsonify(result), status


@admin_bp.route("/api/ai/intent-provider", methods=["POST"])
def api_set_intent_provider():
    result, status = ai_admin_service.set_intent_provider(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/ai/settings", methods=["GET"])
def api_get_ai_settings():
    result, status = ai_admin_service.ai_settings()
    return jsonify(result), status


@admin_bp.route("/api/ai/settings", methods=["POST"])
def api_save_ai_settings():
    result, status = ai_admin_service.save_ai_settings(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/ai/test-provider", methods=["POST"])
def api_test_provider():
    result, status = ai_admin_service.test_provider(request.get_json(silent=True) or {})
    return jsonify(result), status


@admin_bp.route("/api/ai/test", methods=["POST"])
def api_test_ai():
    result, status = ai_admin_service.test_ai(request.get_json(silent=True) or {})
    return jsonify(result), status
