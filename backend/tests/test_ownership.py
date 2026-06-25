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


def test_chat_route_ownership_guard_via_require_owner_or_admin():
    """Verify the logic that guards POST /chat: require_owner_or_admin raises for
    a foreign owner_id, so a non-owner would receive 404 instead of graph access.
    Tested at the service layer (no Neo4j required)."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        # Owner can access their own simulation
        ownership.require_owner_or_admin("u1")  # must not raise

        # Non-owner is rejected — this is what the chat route catches and converts to 404
        with pytest.raises(PermissionError):
            ownership.require_owner_or_admin("u2")

    # Admin can access any simulation
    with _ctx(app, _U("admin", ROLE_ADMIN)):
        ownership.require_owner_or_admin("u2")  # must not raise


def test_check_report_status_ownership_via_can_access():
    """Verify the logic that guards GET /check/<simulation_id>: can_access returns
    False for a foreign owner_id, so report is set to None (no existence leak)."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access("u1") is True   # owner sees report
        assert ownership.can_access("u2") is False  # non-owner → report hidden


def test_generate_status_ownership_via_can_access():
    """Verify the logic that guards POST /generate/status: can_access gates the
    early-return so a non-owner falls through to the task_id path."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER)):
        assert ownership.can_access("u1") is True   # owner gets completed payload
        assert ownership.can_access("u2") is False  # non-owner falls through


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


def test_create_graph_includes_owner_param(monkeypatch):
    """Verify owner_id is passed as a query param and referenced in the Cypher."""
    import app.storage.neo4j_storage as ns

    captured = {}

    class FakeTx:
        def run(self, query, **params):
            # Capture the CREATE query (the graph node creation one)
            if "CREATE" in query and "Graph" in query:
                captured["query"] = query
                captured["params"] = params

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_write(self, func):
            return func(FakeTx())
        def execute_read(self, func):
            return func(FakeTx())

    class FakeDriver:
        def session(self): return FakeSession()

    st = ns.Neo4jStorage.__new__(ns.Neo4jStorage)
    st._driver = FakeDriver()
    st.create_graph("G", owner_id="u1")

    assert captured.get("params", {}).get("owner_id") == "u1", \
        "owner_id must be passed as a query parameter"
    assert "owner_id" in captured.get("query", ""), \
        "owner_id must appear in the Cypher query string"


def test_get_graph_owner_returns_owner_id(monkeypatch):
    """Verify get_graph_owner returns the owner_id stored on the Graph root node."""
    import app.storage.neo4j_storage as ns

    class FakeRecord:
        def __getitem__(self, key):
            return "u1" if key == "owner_id" else None

    class FakeTx:
        def run(self, query, **params):
            class R:
                def single(self_inner): return FakeRecord()
            return R()

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_read(self, func):
            return func(FakeTx())

    class FakeDriver:
        def session(self): return FakeSession()

    st = ns.Neo4jStorage.__new__(ns.Neo4jStorage)
    st._driver = FakeDriver()
    result = st.get_graph_owner("g1")
    assert result == "u1"


def test_get_graph_owner_returns_none_for_legacy(monkeypatch):
    """Verify get_graph_owner returns None when owner_id is absent (legacy graph)."""
    import app.storage.neo4j_storage as ns

    class FakeTx:
        def run(self, query, **params):
            class R:
                def single(self_inner): return None
            return R()

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_read(self, func):
            return func(FakeTx())

    class FakeDriver:
        def session(self): return FakeSession()

    st = ns.Neo4jStorage.__new__(ns.Neo4jStorage)
    st._driver = FakeDriver()
    result = st.get_graph_owner("g_legacy")
    assert result is None
