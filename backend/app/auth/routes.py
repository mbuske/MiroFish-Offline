"""/api/auth/* — login, logout, current user."""
from flask import Blueprint, current_app, g, jsonify, request

from . import service
from ..config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _user_dict(user):
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


def _set_cookie(resp, token):
    resp.set_cookie(
        Config.SESSION_COOKIE_NAME, token,
        max_age=Config.SESSION_TTL_DAYS * 86400,
        httponly=True, samesite="Lax",
        secure=not current_app.config.get("DEBUG", False),
        path="/",
    )


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "")
    password = data.get("password", "")
    user = service.get_user_by_email(email)
    if not user or not user.is_active or not service.verify_password(password, user.password_hash):
        return jsonify({"success": False, "error": "Invalid credentials"}), 401
    token = service.start_session(
        user.id, ttl_days=Config.SESSION_TTL_DAYS,
        user_agent=request.headers.get("User-Agent"),
        ip=request.remote_addr)
    resp = jsonify({"success": True, "user": _user_dict(user)})
    _set_cookie(resp, token)
    return resp


@auth_bp.route("/logout", methods=["POST"])
def logout():
    token = request.cookies.get(Config.SESSION_COOKIE_NAME)
    if token:
        service.revoke_session(token)
    resp = jsonify({"success": True})
    resp.delete_cookie(Config.SESSION_COOKIE_NAME, path="/")
    return resp


@auth_bp.route("/me", methods=["GET"])
def me():
    user = getattr(g, "current_user", None)
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return jsonify({"success": True, "user": _user_dict(user)})
