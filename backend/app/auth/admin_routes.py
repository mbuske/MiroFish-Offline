"""/api/admin/users/* — account-scoped user management."""
from flask import Blueprint, jsonify, request, g

from . import service
from .accounts import current_account_id, is_superadmin
from .decorators import account_admin_required
from .models import ROLE_USER, ROLE_ACCOUNT_ADMIN

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")

_ALLOWED_ROLES = {ROLE_USER, ROLE_ACCOUNT_ADMIN}


def _u(u):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "created_at": u.created_at.isoformat()}


@admin_bp.route("/users", methods=["GET"])
@account_admin_required
def list_users():
    if is_superadmin():
        account_id = request.args.get("account_id")
    else:
        account_id = current_account_id()
        if account_id is None:
            return jsonify({"success": False, "error": "account context missing"}), 403
    return jsonify({"success": True, "users": [_u(u) for u in service.list_users(account_id=account_id)]})


@admin_bp.route("/users", methods=["POST"])
@account_admin_required
def create_user():
    d = request.get_json(silent=True) or {}
    if is_superadmin():
        account_id = d.get("account_id")
    else:
        account_id = current_account_id()
        if account_id is None:
            return jsonify({"success": False, "error": "account context missing"}), 403
    role = d.get("role", ROLE_USER)
    if role not in _ALLOWED_ROLES:
        return jsonify({"success": False, "error": f"role must be one of {sorted(_ALLOWED_ROLES)}"}), 400
    try:
        uid = service.create_user(d.get("email", ""), d.get("password", ""),
                                  name=d.get("name"), role=role,
                                  account_id=account_id,
                                  created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "user": _u(service.get_user(uid))}), 201


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@account_admin_required
def set_role(user_id):
    target = service.get_user(user_id)
    if target is None:
        return jsonify({"success": False, "error": "not found"}), 404
    if not is_superadmin() and target.account_id != current_account_id():
        return jsonify({"success": False, "error": "not found"}), 404
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in _ALLOWED_ROLES:
        return jsonify({"success": False, "error": f"role must be one of {sorted(_ALLOWED_ROLES)}"}), 400
    try:
        service.set_role(user_id, role)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/active", methods=["POST"])
@account_admin_required
def set_active(user_id):
    target = service.get_user(user_id)
    if target is None:
        return jsonify({"success": False, "error": "not found"}), 404
    if not is_superadmin() and target.account_id != current_account_id():
        return jsonify({"success": False, "error": "not found"}), 404
    d = request.get_json(silent=True) or {}
    if "active" not in d:
        return jsonify({"success": False, "error": "missing 'active'"}), 400
    service.set_active(user_id, bool(d["active"]))
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/reset-password", methods=["POST"])
@account_admin_required
def reset_password(user_id):
    target = service.get_user(user_id)
    if target is None:
        return jsonify({"success": False, "error": "not found"}), 404
    if not is_superadmin() and target.account_id != current_account_id():
        return jsonify({"success": False, "error": "not found"}), 404
    pw = (request.get_json(silent=True) or {}).get("password")
    try:
        service.reset_password(user_id, pw)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})
