"""Tests for the idempotent ownership-backfill migration (Task 18)."""
import os
import importlib
import importlib.util
import pytest


def _load_migrate_ownership():
    """Load migrate_ownership from backend/scripts/ using its own sys.path setup."""
    scripts_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts")
    )
    spec_path = os.path.join(scripts_dir, "migrate_ownership.py")
    spec = importlib.util.spec_from_file_location("migrate_ownership", spec_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def patched_dirs(tmp_path, monkeypatch):
    """Redirect all three resource dirs to isolated tmp subdirs."""
    from app.models import project as pj
    from app.services.simulation_manager import SimulationManager
    from app.services.report_agent import ReportManager

    proj_dir = str(tmp_path / "projects")
    sim_dir = str(tmp_path / "simulations")
    rep_dir = str(tmp_path / "reports")
    os.makedirs(proj_dir, exist_ok=True)
    os.makedirs(sim_dir, exist_ok=True)
    os.makedirs(rep_dir, exist_ok=True)

    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", proj_dir, raising=False)
    monkeypatch.setattr(SimulationManager, "SIMULATION_DATA_DIR", sim_dir, raising=False)
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", rep_dir, raising=False)

    return {"proj": proj_dir, "sim": sim_dir, "rep": rep_dir}


# ── Project backfill ──────────────────────────────────────────────────────────

def test_backfill_assigns_admin_and_is_idempotent(patched_dirs):
    """Legacy project (owner_id=None) gets assigned the admin; second run is a no-op."""
    from app.models import project as pj

    p = pj.ProjectManager.create_project("legacy")  # owner_id None

    mod = _load_migrate_ownership()
    counts = mod.backfill("admin-id")

    assert pj.ProjectManager.get_project(p.project_id).owner_id == "admin-id"
    assert counts["projects"] >= 1

    # idempotent: second run changes nothing
    counts2 = mod.backfill("admin-id")
    assert counts2["projects"] == 0


def test_backfill_leaves_owned_projects_untouched(patched_dirs):
    """Projects that already have an owner_id are not modified."""
    from app.models import project as pj

    owned = pj.ProjectManager.create_project("already-owned", owner_id="original-owner")
    unowned = pj.ProjectManager.create_project("unowned")

    mod = _load_migrate_ownership()
    counts = mod.backfill("admin-id")

    assert counts["projects"] == 1  # only the unowned one
    assert pj.ProjectManager.get_project(owned.project_id).owner_id == "original-owner"
    assert pj.ProjectManager.get_project(unowned.project_id).owner_id == "admin-id"


# ── Simulation backfill ───────────────────────────────────────────────────────

def test_backfill_simulations(patched_dirs):
    """Legacy simulations (owner_id=None) get assigned the admin; owned ones are skipped."""
    from app.services.simulation_manager import SimulationManager

    sm = SimulationManager()
    s_unowned = sm.create_simulation(project_id="p1", graph_id="g1")
    s_owned = sm.create_simulation(project_id="p2", graph_id="g2", owner_id="original-owner")

    mod = _load_migrate_ownership()
    counts = mod.backfill("admin-id")

    assert counts["simulations"] == 1

    sm2 = SimulationManager()
    assert sm2.get_simulation(s_unowned.simulation_id).owner_id == "admin-id"
    assert sm2.get_simulation(s_owned.simulation_id).owner_id == "original-owner"

    # idempotent
    counts2 = mod.backfill("admin-id")
    assert counts2["simulations"] == 0


# ── Report backfill ───────────────────────────────────────────────────────────

def test_backfill_reports(patched_dirs):
    """Legacy reports (owner_id=None) get assigned the admin; owned ones are skipped."""
    from app.services.report_agent import ReportManager, Report, ReportStatus

    r_unowned = Report(
        report_id="report-001",
        simulation_id="sim-x",
        graph_id="g-x",
        simulation_requirement="test",
        status=ReportStatus.COMPLETED,
        owner_id=None,
    )
    r_owned = Report(
        report_id="report-002",
        simulation_id="sim-y",
        graph_id="g-y",
        simulation_requirement="test",
        status=ReportStatus.COMPLETED,
        owner_id="original-owner",
    )
    ReportManager.save_report(r_unowned)
    ReportManager.save_report(r_owned)

    mod = _load_migrate_ownership()
    counts = mod.backfill("admin-id")

    assert counts["reports"] == 1
    assert ReportManager.get_report("report-001").owner_id == "admin-id"
    assert ReportManager.get_report("report-002").owner_id == "original-owner"

    # idempotent
    counts2 = mod.backfill("admin-id")
    assert counts2["reports"] == 0


# ── Return shape guarantee ────────────────────────────────────────────────────

def test_backfill_returns_required_keys(patched_dirs):
    """backfill() always returns a dict with projects/simulations/reports/graphs keys."""
    mod = _load_migrate_ownership()
    counts = mod.backfill("admin-id")

    assert "projects" in counts
    assert "simulations" in counts
    assert "reports" in counts
    assert "graphs" in counts
