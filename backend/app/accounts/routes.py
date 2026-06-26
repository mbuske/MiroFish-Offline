"""/api/superadmin/* — account provisioning (superadmin only)."""
from flask import Blueprint, jsonify, request, g

from . import service as acct_service
from ..auth import service as user_service
from ..auth.decorators import superadmin_required
from ..auth.models import ROLE_ACCOUNT_ADMIN
from ..branding import service as branding_service

superadmin_bp = Blueprint("superadmin", __name__, url_prefix="/api/superadmin")


def _u(u):
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role,
            "is_active": u.is_active, "account_id": u.account_id}


@superadmin_bp.route("/accounts", methods=["GET"])
@superadmin_required
def list_accounts():
    return jsonify({"success": True, "accounts": acct_service.list_accounts()})


@superadmin_bp.route("/accounts", methods=["POST"])
@superadmin_required
def create_account():
    name = (request.get_json(silent=True) or {}).get("name")
    try:
        aid = acct_service.create_account(name, created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "account": {"id": aid, "name": name.strip()}}), 201


@superadmin_bp.route("/accounts/<account_id>/active", methods=["POST"])
@superadmin_required
def set_active(account_id):
    active = bool((request.get_json(silent=True) or {}).get("active"))
    try:
        acct_service.set_account_active(account_id, active)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@superadmin_bp.route("/accounts/<account_id>/admin", methods=["POST"])
@superadmin_required
def create_account_admin(account_id):
    if not acct_service.get_account(account_id):
        return jsonify({"success": False, "error": "account not found"}), 404
    d = request.get_json(silent=True) or {}
    try:
        uid = user_service.create_user(d.get("email", ""), d.get("password", ""),
                                       name=d.get("name"), role=ROLE_ACCOUNT_ADMIN,
                                       account_id=account_id, created_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "user": _u(user_service.get_user(uid))}), 201


@superadmin_bp.route("/accounts/<account_id>/slug", methods=["POST"])
@superadmin_required
def set_slug(account_id):
    slug = (request.get_json(silent=True) or {}).get("slug", "")
    try:
        acct_service.set_account_slug(account_id, slug)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@superadmin_bp.route("/accounts/<account_id>/users", methods=["GET"])
@superadmin_required
def account_users(account_id):
    return jsonify({"success": True, "users": [_u(u) for u in user_service.list_users(account_id=account_id)]})


@superadmin_bp.route("/accounts/<account_id>/branding", methods=["POST"])
@superadmin_required
def update_account_branding(account_id):
    if not acct_service.get_account(account_id):
        return jsonify({"success": False, "error": "account not found"}), 404
    d = request.get_json(silent=True) or {}
    try:
        branding_service.update_colors(
            account_id,
            primary_color=d.get("primary_color"),
            accent_color=d.get("accent_color"),
            updated_by=g.current_user.id,
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@superadmin_bp.route("/accounts/<account_id>/branding/logo", methods=["POST"])
@superadmin_required
def upload_account_logo(account_id):
    if not acct_service.get_account(account_id):
        return jsonify({"success": False, "error": "account not found"}), 404
    f = request.files.get("file")
    if f is None:
        return jsonify({"success": False, "error": "Missing file field"}), 400
    try:
        branding_service.save_asset(account_id, "logo", f, updated_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "logo_url": f"/api/branding/logo?account={account_id}"})


@superadmin_bp.route("/accounts/<account_id>/branding/favicon", methods=["POST"])
@superadmin_required
def upload_account_favicon(account_id):
    if not acct_service.get_account(account_id):
        return jsonify({"success": False, "error": "account not found"}), 404
    f = request.files.get("file")
    if f is None:
        return jsonify({"success": False, "error": "Missing file field"}), 400
    try:
        branding_service.save_asset(account_id, "favicon", f, updated_by=g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "favicon_url": f"/api/branding/favicon?account={account_id}"})
