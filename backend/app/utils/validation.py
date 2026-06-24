"""
Input-validation helpers for untrusted request parameters.

These close path-traversal and IPC-injection vectors where attacker-controlled
values (simulation_id, platform) are used to build filesystem paths:
  - CVE-2026-7059 (path traversal via `platform` / `simulation_id`)
  - unvalidated `simulation_id` reaching the file-based IPC channel
"""
import os
import re

# A simulation id is generated internally as `sim_<token>`. Restrict to a safe
# charset so it can never traverse directories or escape the data dir.
_SIMULATION_ID_RE = re.compile(r"^sim_[A-Za-z0-9_-]{1,64}$")

# OASIS supports exactly these social platforms.
_ALLOWED_PLATFORMS = frozenset({"reddit", "twitter"})


def validate_simulation_id(simulation_id: str) -> str:
    """Return the id unchanged if it is a safe simulation id, else raise ValueError."""
    if not isinstance(simulation_id, str) or not _SIMULATION_ID_RE.match(simulation_id):
        raise ValueError(f"Invalid simulation_id: {simulation_id!r}")
    return simulation_id


def validate_platform(platform: str) -> str:
    """Return the platform unchanged if it is in the allowlist, else raise ValueError."""
    if platform not in _ALLOWED_PLATFORMS:
        raise ValueError(f"Invalid platform: {platform!r}")
    return platform


def safe_join(base: str, *parts: str) -> str:
    """
    Join `parts` onto `base` and guarantee the result stays inside `base`.

    Raises ValueError if the resolved path escapes the base directory (via
    '..', an absolute component, or a symlink-style escape).
    """
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, *parts))
    # Containment check: target must be base itself or live under base + sep.
    if target != base_abs and not target.startswith(base_abs + os.sep):
        raise ValueError(f"Path escapes base directory: {os.path.join(*parts)!r}")
    return target
