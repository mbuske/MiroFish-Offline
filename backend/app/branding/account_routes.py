"""Account-admin branding write API.

Blueprint: branding_account_bp
URL prefix: /api/account/branding

All routes require @account_admin_required and a non-null current_account_id()
(superadmins with account_id=None must use the superadmin/default routes instead).
Writes go to the caller's own account.
"""
from flask import Blueprint, jsonify, request, g

from . import service
from ..auth.decorators import account_admin_required
from ..auth.accounts import current_account_id

branding_account_bp = Blueprint("branding_account", __name__, url_prefix="/api/account/branding")


@branding_account_bp.route("", methods=["POST"])
@account_admin_required
def update_colors():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    d = request.get_json(silent=True) or {}
    try:
        service.update_colors(aid, d.get("primary_color"), d.get("accent_color"), g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@branding_account_bp.route("/logo", methods=["POST"])
@account_admin_required
def upload_logo():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "error": "no file"}), 400
    try:
        service.save_asset(aid, "logo", f, g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "logo_url": "/api/branding/logo"})


@branding_account_bp.route("/favicon", methods=["POST"])
@account_admin_required
def upload_favicon():
    aid = current_account_id()
    if aid is None:
        return jsonify({"success": False, "error": "no account context"}), 400
    f = request.files.get("file")
    if not f:
        return jsonify({"success": False, "error": "no file"}), 400
    try:
        service.save_asset(aid, "favicon", f, g.current_user.id)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "favicon_url": "/api/branding/favicon"})
