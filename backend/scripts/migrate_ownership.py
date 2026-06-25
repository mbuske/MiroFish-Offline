"""Backfill owner_id on pre-multi-user data, assigning it to the seed admin.

Usage:  cd backend && uv run python scripts/migrate_ownership.py
Idempotent: objects that already have an owner are left untouched.
"""

import sys
import os

# Ensure the backend package root is on sys.path when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.project import ProjectManager


def backfill(admin_id: str) -> dict:
    """Assign *admin_id* as owner to every unowned resource.

    Args:
        admin_id: The user ID of the seed admin.

    Returns:
        A dict with keys ``projects``, ``simulations``, ``reports`` whose
        values are the count of records updated (0 on a second idempotent run).
    """
    counts = {"projects": 0, "simulations": 0, "reports": 0}

    # ── Projects ─────────────────────────────────────────────────────────────
    for p in ProjectManager.list_projects(limit=10_000, include_all=True):
        if getattr(p, "owner_id", None) is None:
            p.owner_id = admin_id
            ProjectManager.save_project(p)
            counts["projects"] += 1

    # ── Simulations ──────────────────────────────────────────────────────────
    from app.services.simulation_manager import SimulationManager

    sm = SimulationManager()
    for s in sm.list_simulations(include_all=True):
        if getattr(s, "owner_id", None) is None:
            s.owner_id = admin_id
            sm._save_simulation_state(s)
            counts["simulations"] += 1

    # ── Reports ──────────────────────────────────────────────────────────────
    from app.services.report_agent import ReportManager

    for r in ReportManager.list_reports(limit=10_000, include_all=True):
        if getattr(r, "owner_id", None) is None:
            r.owner_id = admin_id
            ReportManager.save_report(r)
            counts["reports"] += 1

    return counts


def _resolve_admin_id() -> str:
    """Return the ID of the first active admin in the auth DB."""
    from app.auth.db import init_db
    from app.auth import service
    from app.config import Config

    init_db(Config.AUTH_DB_PATH)
    admins = [u for u in service.list_users() if u.role == "admin"]
    if not admins:
        raise SystemExit("No admin user exists; seed an admin first.")
    return admins[0].id


if __name__ == "__main__":
    admin_id = _resolve_admin_id()
    result = backfill(admin_id)
    print("Backfilled:", result)
