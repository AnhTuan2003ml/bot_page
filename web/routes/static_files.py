import os

from flask import send_from_directory

from web.routes import admin_bp


def _no_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@admin_bp.route("/templates/css/<path:filename>")
def serve_css(filename):
    css_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "css")
    return _no_cache(send_from_directory(css_dir, filename))


@admin_bp.route("/templates/js/<path:filename>")
def serve_js(filename):
    js_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "js")
    return _no_cache(send_from_directory(js_dir, filename))


@admin_bp.route("/templates/logo.ico")
def serve_logo():
    templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
    return _no_cache(send_from_directory(templates_dir, "logo.ico"))
