import pytest
from contextlib import contextmanager
from flask import Flask, g
from app.auth import ownership
from app.auth.models import ROLE_ADMIN, ROLE_USER


class _U:
    def __init__(self, uid, role):
        self.id, self.role = uid, role


@contextmanager
def _ctx(app, user):
    with app.test_request_context():
        g.current_user = user
        yield


def test_owner_can_access():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access("u1") is True
        assert ownership.can_access("u2") is False


def test_admin_can_access_anything():
    app = Flask(__name__)
    with _ctx(app, _U("a", ROLE_ADMIN)):
        assert ownership.can_access("u2") is True
        assert ownership.can_access(None) is True


def test_require_raises_for_foreign():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u2")


def test_nonadmin_denied_legacy_unowned():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access(None) is False  # legacy/unowned → non-admin denied


def test_anonymous_user_denied():
    app = Flask(__name__)
    with _ctx(app, None):                       # no authenticated user
        assert ownership.can_access("u1") is False
        assert ownership.can_access(None) is False
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u1")


def test_list_projects_filters_by_owner(tmp_path, monkeypatch):
    from app.models import project as pj
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path), raising=False)
    # create two projects with different owners
    p1 = pj.ProjectManager.create_project("P1", owner_id="u1")
    p2 = pj.ProjectManager.create_project("P2", owner_id="u2")
    mine = pj.ProjectManager.list_projects(owner_id="u1")
    assert {p.project_id for p in mine} == {p1.project_id}
    everything = pj.ProjectManager.list_projects(include_all=True)
    assert {p.project_id for p in everything} >= {p1.project_id, p2.project_id}


def test_list_simulations_filters_by_owner(tmp_path, monkeypatch):
    from app.services.simulation_manager import SimulationManager
    m = SimulationManager()
    m.SIMULATION_DATA_DIR = str(tmp_path)
    s1 = m.create_simulation(project_id="p1", graph_id="g1", owner_id="u1")
    m.create_simulation(project_id="p2", graph_id="g2", owner_id="u2")
    mine = m.list_simulations(owner_id="u1")
    assert len(mine) == 1
    assert all(s.owner_id == "u1" for s in mine)
    everything = m.list_simulations(include_all=True)
    assert len(everything) == 2


def test_list_reports_filters_by_owner(tmp_path, monkeypatch):
    from app.services.report_agent import ReportManager, Report, ReportStatus
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path), raising=False)
    r1 = Report(
        report_id="r1",
        simulation_id="s1",
        graph_id="g1",
        simulation_requirement="req1",
        status=ReportStatus.COMPLETED,
    )
    r1.owner_id = "u1"
    r2 = Report(
        report_id="r2",
        simulation_id="s2",
        graph_id="g2",
        simulation_requirement="req2",
        status=ReportStatus.COMPLETED,
    )
    r2.owner_id = "u2"
    ReportManager.save_report(r1)
    ReportManager.save_report(r2)
    mine = ReportManager.list_reports(owner_id="u1")
    assert len(mine) == 1
    assert all(x.owner_id == "u1" for x in mine)
    everything = ReportManager.list_reports(include_all=True)
    assert len(everything) == 2
