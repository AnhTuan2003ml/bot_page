"""
Legacy compatibility layer.

Routes/controllers moved to web.routes. Keep importing admin_bp from here so
existing app.py and external imports do not break.
"""

from web.routes import admin_bp
