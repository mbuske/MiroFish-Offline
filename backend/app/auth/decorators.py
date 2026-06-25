"""Authorization decorators."""
from functools import wraps
from flask import g, jsonify
from .models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def superadmin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role != ROLE_SUPERADMIN:
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


def account_admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role not in (ROLE_ACCOUNT_ADMIN, ROLE_SUPERADMIN):
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper


# Backward-compat alias; removed in a later task when admin_routes.py and branding/admin_routes.py migrate
admin_required = account_admin_required
