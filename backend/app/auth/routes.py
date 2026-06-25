"""/api/auth/* — login, logout, current user."""
from flask import Blueprint, current_app, g, jsonify, request

from . import service
from ..config import Config

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _user_dict(user):
    account_name = None
    if user.account_id:
        from ..accounts.service import get_account
        acc = get_account(user.account_id)
        account_name = acc.name if acc else None
    return {"id": user.id, "email": user.email, "name": user.name,
            "role": user.role, "account_id": user.account_id, "account_name": account_name}


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
    # Block login when the user's account is deactivated (superadmin has account_id None).
    if user.account_id:
        from ..accounts.service import get_account
        acc = get_account(user.account_id)
        if acc is not None and acc.is_active is False:
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
    resp.set_cookie(
        Config.SESSION_COOKIE_NAME, "", max_age=0, expires=0,
        httponly=True, samesite="Lax",
        secure=not current_app.config.get("DEBUG", False),
        path="/",
    )
    return resp


@auth_bp.route("/me", methods=["GET"])
def me():
    user = getattr(g, "current_user", None)
    if not user:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    return jsonify({"success": True, "user": _user_dict(user)})
