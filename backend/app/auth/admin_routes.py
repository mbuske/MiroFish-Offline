"""/api/admin/users/* — admin-only account management."""
from flask import Blueprint, jsonify, request, g

from . import service
from .decorators import admin_required
from .models import ROLE_USER

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _u(u):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "created_at": u.created_at.isoformat()}


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_users():
    return jsonify({"success": True, "users": [_u(u) for u in service.list_users()]})


@admin_bp.route("/users", methods=["POST"])
@admin_required
def create_user():
    d = request.get_json(silent=True) or {}
    try:
        uid = service.create_user(d.get("email", ""), d.get("password", ""),
                                  name=d.get("name"), role=d.get("role", ROLE_USER),
                                  created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "user": _u(service.get_user(uid))}), 201


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@admin_required
def set_role(user_id):
    try:
        service.set_role(user_id, (request.get_json(silent=True) or {}).get("role"))
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/active", methods=["POST"])
@admin_required
def set_active(user_id):
    active = bool((request.get_json(silent=True) or {}).get("active"))
    service.set_active(user_id, active)
    return jsonify({"success": True})


@admin_bp.route("/users/<user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    pw = (request.get_json(silent=True) or {}).get("password")
    try:
        service.reset_password(user_id, pw)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})
