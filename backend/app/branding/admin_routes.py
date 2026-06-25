"""Admin-only branding write endpoints."""
from flask import Blueprint, jsonify, request

from app.auth.decorators import admin_required
from app.auth.ownership import current_user_id
from . import service as branding_service

branding_admin_bp = Blueprint(
    "branding_admin", __name__, url_prefix="/api/admin/branding"
)


@branding_admin_bp.route("", methods=["POST"])
@admin_required
def update_colors():
    d = request.get_json(silent=True) or {}
    try:
        branding_service.update_colors(
            primary_color=d.get("primary_color"),
            accent_color=d.get("accent_color"),
            updated_by=current_user_id(),
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True})


@branding_admin_bp.route("/logo", methods=["POST"])
@admin_required
def upload_logo():
    f = request.files.get("file")
    if f is None:
        return jsonify({"success": False, "error": "Missing file field"}), 400
    try:
        branding_service.save_asset("logo", f, updated_by=current_user_id())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "logo_url": "/api/branding/logo"})


@branding_admin_bp.route("/favicon", methods=["POST"])
@admin_required
def upload_favicon():
    f = request.files.get("file")
    if f is None:
        return jsonify({"success": False, "error": "Missing file field"}), 400
    try:
        branding_service.save_asset("favicon", f, updated_by=current_user_id())
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "favicon_url": "/api/branding/favicon"})
