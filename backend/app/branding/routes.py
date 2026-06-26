"""Public branding read endpoints — no auth required."""
from flask import Blueprint, jsonify, send_file, request

from . import service

branding_bp = Blueprint("branding", __name__, url_prefix="/api/branding")


@branding_bp.route("/config", methods=["GET"])
def get_config():
    slug = request.args.get("account")
    account_id = service.resolve_account_id_for_slug(slug)
    res = service.resolve_branding(account_id)
    q = f"?account={slug}" if slug else ""
    return jsonify({"success": True, "data": {
        "primary_color": res["primary_color"],
        "accent_color": res["accent_color"],
        "logo_url": f"/api/branding/logo{q}" if res["logo_filename"] else None,
        "favicon_url": f"/api/branding/favicon{q}" if res["favicon_filename"] else None,
    }})


def _serve(kind):
    slug = request.args.get("account")
    account_id = service.resolve_account_id_for_slug(slug)
    # try account asset, then default
    path = service.asset_path(account_id, kind) if account_id else None
    if path is None:
        path = service.asset_path(None, kind)
    if path is None:
        return jsonify({"success": False, "error": "not found"}), 404
    return send_file(path)


@branding_bp.route("/logo", methods=["GET"])
def get_logo():
    return _serve("logo")


@branding_bp.route("/favicon", methods=["GET"])
def get_favicon():
    return _serve("favicon")
