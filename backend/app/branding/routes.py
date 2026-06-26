"""Public branding read endpoints — no auth required."""
from flask import Blueprint, jsonify, send_file

from . import service as branding_service

branding_bp = Blueprint("branding", __name__, url_prefix="/api/branding")


@branding_bp.route("/config", methods=["GET"])
def get_config():
    data = branding_service.get_branding(account_id=None)

    logo_url = (
        "/api/branding/logo"
        if branding_service.asset_path(None, "logo") is not None
        else None
    )
    favicon_url = (
        "/api/branding/favicon"
        if branding_service.asset_path(None, "favicon") is not None
        else None
    )

    return jsonify({
        "success": True,
        "data": {
            "primary_color": data["primary_color"],
            "accent_color": data["accent_color"],
            "logo_url": logo_url,
            "favicon_url": favicon_url,
        },
    })


@branding_bp.route("/logo", methods=["GET"])
def get_logo():
    path = branding_service.asset_path(None, "logo")
    if path is None:
        return jsonify({"success": False, "error": "No logo configured"}), 404
    return send_file(path)


@branding_bp.route("/favicon", methods=["GET"])
def get_favicon():
    path = branding_service.asset_path(None, "favicon")
    if path is None:
        return jsonify({"success": False, "error": "No favicon configured"}), 404
    return send_file(path)
