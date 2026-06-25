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


def test_list_projects_filters_by_account(tmp_path, monkeypatch):
    from app.models import project as pj
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path), raising=False)
    # create two projects with different accounts; owner_id kept as audit stamp
    p1 = pj.ProjectManager.create_project("P1", owner_id="u1", account_id="accA")
    p2 = pj.ProjectManager.create_project("P2", owner_id="u2", account_id="accB")
    mine = pj.ProjectManager.list_projects(account_id="accA")
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


def test_backfill_includes_graphs_key_and_invokes_graph_backfill(tmp_path, monkeypatch):
    """backfill() must return a ``graphs`` count and drive the graph-owner
    backfill via Neo4jStorage.set_graph_owner_if_missing — verified with a fake
    storage so no live Neo4j is required."""
    import app.storage.neo4j_storage as ns
    from app.models import project as pj
    from app.services import simulation_manager as smm
    from app.services import report_agent as ra
    from scripts import migrate_ownership

    # Point file-backed managers at empty temp dirs → 0 file-resource updates.
    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path / "proj"), raising=False)
    sm = smm.SimulationManager()
    monkeypatch.setattr(sm, "SIMULATION_DATA_DIR", str(tmp_path / "sim"), raising=False)
    monkeypatch.setattr(smm, "SimulationManager", lambda *a, **k: sm)
    monkeypatch.setattr(ra.ReportManager, "REPORTS_DIR", str(tmp_path / "rep"), raising=False)

    captured = {}

    class FakeStorage:
        def __init__(self, *a, **k):
            pass

        def set_graph_owner_if_missing(self, admin_id):
            captured["admin_id"] = admin_id
            return 3

    monkeypatch.setattr(ns, "Neo4jStorage", FakeStorage)

    result = migrate_ownership.backfill("admin-1")

    assert "graphs" in result
    assert result["graphs"] == 3
    assert captured.get("admin_id") == "admin-1"


def test_backfill_graph_step_tolerates_neo4j_down(tmp_path, monkeypatch):
    """If Neo4j is unavailable, backfill logs and continues with graphs=0."""
    import app.storage.neo4j_storage as ns
    from app.models import project as pj
    from app.services import simulation_manager as smm
    from app.services import report_agent as ra
    from scripts import migrate_ownership

    monkeypatch.setattr(pj.ProjectManager, "PROJECTS_DIR", str(tmp_path / "proj"), raising=False)
    sm = smm.SimulationManager()
    monkeypatch.setattr(sm, "SIMULATION_DATA_DIR", str(tmp_path / "sim"), raising=False)
    monkeypatch.setattr(smm, "SimulationManager", lambda *a, **k: sm)
    monkeypatch.setattr(ra.ReportManager, "REPORTS_DIR", str(tmp_path / "rep"), raising=False)

    class BoomStorage:
        def __init__(self, *a, **k):
            raise RuntimeError("Neo4j unavailable")

    monkeypatch.setattr(ns, "Neo4jStorage", BoomStorage)

    result = migrate_ownership.backfill("admin-1")
    assert result["graphs"] == 0


def test_set_graph_owner_if_missing_runs_backfill_cypher(monkeypatch):
    """Verify the Cypher targets unowned Graph nodes and returns the count."""
    import app.storage.neo4j_storage as ns

    captured = {}

    class FakeRecord:
        def __getitem__(self, key):
            return 5 if key == "updated" else None

    class FakeTx:
        def run(self, query, **params):
            captured["query"] = query
            captured["params"] = params

            class R:
                def single(self_inner): return FakeRecord()
            return R()

    class FakeSession:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute_write(self, func):
            return func(FakeTx())

    class FakeDriver:
        def session(self): return FakeSession()

    st = ns.Neo4jStorage.__new__(ns.Neo4jStorage)
    st._driver = FakeDriver()
    result = st.set_graph_owner_if_missing("admin-1")

    assert result == 5
    assert "owner_id IS NULL" in captured["query"]
    assert captured["params"]["admin"] == "admin-1"


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


def test_account_access_helpers():
    from flask import Flask, g
    from app.auth import accounts
    from app.auth.models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER
    import pytest

    class _U:
        def __init__(self, role, account_id):
            self.role, self.account_id = role, account_id

    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U(ROLE_USER, "accA")
        assert accounts.can_access_account("accA") is True
        assert accounts.can_access_account("accB") is False
        assert accounts.can_access_account(None) is False
        with pytest.raises(PermissionError):
            accounts.require_account_access("accB")
    with app.test_request_context():
        g.current_user = _U(ROLE_SUPERADMIN, None)
        assert accounts.can_access_account("accB") is True
        assert accounts.is_superadmin() is True
    with app.test_request_context():
        g.current_user = None
        assert accounts.can_access_account("accA") is False
