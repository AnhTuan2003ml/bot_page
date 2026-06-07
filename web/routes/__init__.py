from flask import Blueprint

admin_bp = Blueprint("admin", __name__, template_folder="../../templates")

from web.routes import static_files  # noqa: E402,F401
from web.routes import admin_logs  # noqa: E402,F401
from web.routes import admin_stats  # noqa: E402,F401
from web.routes import admin_config  # noqa: E402,F401
from web.routes import admin_ai  # noqa: E402,F401
from web.routes import admin_pages  # noqa: E402,F401
from web.routes import admin_skills  # noqa: E402,F401
