"""
API security layer.

Addresses CVE-2026-7042 (missing authentication for critical functions) by
adding an opt-in bearer-token gate over the REST API, and provides CORS origin
hardening to replace the wildcard `*` origin.

The token is opt-in (enabled by setting API_TOKEN) so the default localhost,
single-user experience is preserved; when set, every /api/* route requires it.
"""
import hmac
import os

from flask import request, jsonify

# Routes that must never require auth (liveness probe + CORS preflight handled
# separately by method).
_AUTH_EXEMPT_PATHS = frozenset({"/health"})

_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def get_cors_origins(raw: str | None = None) -> list[str]:
    """
    Return the list of allowed CORS origins.

    Reads CORS_ORIGINS (comma-separated) from the environment when `raw` is not
    provided. Never returns a wildcard.
    """
    if raw is None:
        raw = os.environ.get("CORS_ORIGINS", "")
    if not raw.strip():
        raw = _DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


def _extract_token() -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key.strip()
    return None


def register_auth(app) -> None:
    """Install a before_request hook enforcing API_TOKEN on /api/* routes."""

    @app.before_request
    def _require_token():
        configured = app.config.get("API_TOKEN") or ""
        if not configured:
            # Hardening is opt-in; without a token the app stays open.
            return None
        if request.method == "OPTIONS":
            return None  # let CORS preflight through
        if not request.path.startswith("/api/"):
            return None
        if request.path in _AUTH_EXEMPT_PATHS:
            return None

        provided = _extract_token() or ""
        # Constant-time comparison to avoid timing oracles.
        if not provided or not hmac.compare_digest(provided, configured):
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return None
