"""Authorization decorators."""
from functools import wraps
from flask import g, jsonify
from .models import ROLE_ADMIN


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        if user.role != ROLE_ADMIN:
            return jsonify({"success": False, "error": "Forbidden"}), 403
        return fn(*args, **kwargs)
    return wrapper
