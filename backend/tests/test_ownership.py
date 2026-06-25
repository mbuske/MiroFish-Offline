"""Tests for data-isolation helpers.

The legacy owner-based helpers (is_admin, can_access, require_owner_or_admin)
were removed in Task 13.  Tests that exercised those helpers have been replaced
with account-scoped equivalents using ``app.auth.accounts``.
"""
import pytest
from contextlib import contextmanager
from flask import Flask, g

from app.auth import accounts as account_access
from app.auth.models import ROLE_SUPERADMIN, ROLE_ACCOUNT_ADMIN, ROLE_USER


class _U:
    def __init__(self, uid, role, account_id=None):
        self.id, self.role = uid, role
        self.account_id = account_id


@contextmanager
def _ctx(app, user):
    with app.test_request_context():
        g.current_user = user
        yield


# ---------------------------------------------------------------------------
# Account-scoped access helpers (replaced owner-based helpers)
# ---------------------------------------------------------------------------

def test_account_member_can_access_own_account():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        assert account_access.can_access_account("accA") is True
        assert account_access.can_access_account("accB") is False


def test_superadmin_can_access_any_account():
    app = Flask(__name__)
    with _ctx(app, _U("sa", ROLE_SUPERADMIN, account_id=None)):
        assert account_access.can_access_account("accX") is True
        assert account_access.can_access_account(None) is True


def test_require_account_access_raises_for_foreign():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        with pytest.raises(PermissionError):
            account_access.require_account_access("accB")


def test_non_account_member_denied_for_none_account():
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        assert account_access.can_access_account(None) is False


def test_anonymous_user_denied_account_access():
    app = Flask(__name__)
    with _ctx(app, None):
        assert account_access.can_access_account("accA") is False
        with pytest.raises(PermissionError):
            account_access.require_account_access("accA")


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


def test_list_simulations_filters_by_account(tmp_path, monkeypatch):
    from app.services.simulation_manager import SimulationManager
    m = SimulationManager()
    m.SIMULATION_DATA_DIR = str(tmp_path)
    # create two simulations with different accounts; owner_id kept as audit stamp
    s1 = m.create_simulation(project_id="p1", graph_id="g1", owner_id="u1", account_id="accA")
    s2 = m.create_simulation(project_id="p2", graph_id="g2", owner_id="u2", account_id="accB")
    mine = m.list_simulations(account_id="accA")
    assert {s.simulation_id for s in mine} == {s1.simulation_id}
    assert all(s.account_id == "accA" for s in mine)
    everything = m.list_simulations(include_all=True)
    assert {s.simulation_id for s in everything} >= {s1.simulation_id, s2.simulation_id}


def test_list_simulations_include_all_returns_all(tmp_path, monkeypatch):
    from app.services.simulation_manager import SimulationManager
    m = SimulationManager()
    m.SIMULATION_DATA_DIR = str(tmp_path)
    s1 = m.create_simulation(project_id="p1", graph_id="g1", owner_id="u1", account_id="accA")
    m.create_simulation(project_id="p2", graph_id="g2", owner_id="u2", account_id="accB")
    everything = m.list_simulations(include_all=True)
    assert len(everything) == 2


def test_chat_route_account_guard_via_require_account_access():
    """Verify the account-scoped guard: require_account_access raises for a
    different account, so a user from another account is denied graph access."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        # Same account — must not raise
        account_access.require_account_access("accA")

        # Different account — raises PermissionError
        with pytest.raises(PermissionError):
            account_access.require_account_access("accB")

    # Superadmin can access any account
    with _ctx(app, _U("sa", ROLE_SUPERADMIN, account_id=None)):
        account_access.require_account_access("accB")  # must not raise


def test_check_report_status_account_guard_via_can_access_account():
    """Verify the account-scoped guard used to gate report visibility."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        assert account_access.can_access_account("accA") is True   # same account → report visible
        assert account_access.can_access_account("accB") is False  # different account → hidden


def test_generate_status_account_guard_via_can_access_account():
    """Verify the account-scoped guard used to gate generate-status early return."""
    app = Flask(__name__)
    with _ctx(app, _U("u1", ROLE_USER, account_id="accA")):
        assert account_access.can_access_account("accA") is True   # same account gets completed payload
        assert account_access.can_access_account("accB") is False  # different account falls through


def test_list_reports_filters_by_account(tmp_path, monkeypatch):
    from app.services.report_agent import ReportManager, Report, ReportStatus
    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path), raising=False)
    r1 = Report(
        report_id="r1",
        simulation_id="s1",
        graph_id="g1",
        simulation_requirement="req1",
        status=ReportStatus.COMPLETED,
        owner_id="u1",
        account_id="accA",
    )
    r2 = Report(
        report_id="r2",
        simulation_id="s2",
        graph_id="g2",
        simulation_requirement="req2",
        status=ReportStatus.COMPLETED,
        owner_id="u2",
        account_id="accB",
    )
    ReportManager.save_report(r1)
    ReportManager.save_report(r2)
    mine = ReportManager.list_reports(account_id="accA")
    assert len(mine) == 1
    assert all(x.account_id == "accA" for x in mine)
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


# ---------------------------------------------------------------------------
# Task-12: account_id on Graph root node
# ---------------------------------------------------------------------------

def test_create_graph_includes_account_id_param(monkeypatch):
    """Verify account_id is passed as a query param and referenced in the Cypher."""
    import app.storage.neo4j_storage as ns

    captured = {}

    class FakeTx:
        def run(self, query, **params):
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
    st.create_graph("G", owner_id="u1", account_id="accA")

    assert captured.get("params", {}).get("account_id") == "accA", \
        "account_id must be passed as a query parameter"
    assert "account_id" in captured.get("query", ""), \
        "account_id must appear in the Cypher query string"


def test_get_graph_account_returns_account_id(monkeypatch):
    """Verify get_graph_account returns the account_id stored on the Graph root node."""
    import app.storage.neo4j_storage as ns

    class FakeRecord:
        def __getitem__(self, key):
            return "accA" if key == "account_id" else None

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
    result = st.get_graph_account("g1")
    assert result == "accA"


def test_get_graph_account_returns_none_for_legacy(monkeypatch):
    """Verify get_graph_account returns None when account_id is absent (legacy graph)."""
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
    result = st.get_graph_account("g_legacy")
    assert result is None


def test_require_graph_account_access_passes_same_account():
    """require_graph_account_access must pass when graph account matches current user account."""
    from flask import Flask, g, current_app
    from app.auth import graph_access
    from app.auth.models import ROLE_USER

    class _U:
        def __init__(self, role, account_id):
            self.role, self.account_id = role, account_id

    class _FakeStorage:
        def get_graph_account(self, graph_id):
            return "accA"

    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U(ROLE_USER, "accA")
        current_app.extensions['neo4j_storage'] = _FakeStorage()
        graph_access.require_graph_account_access("g1")  # must not raise


def test_require_graph_account_access_raises_for_foreign_account():
    """require_graph_account_access must raise for a user from a different account."""
    import pytest
    from flask import Flask, g, current_app
    from app.auth import graph_access
    from app.auth.models import ROLE_USER

    class _U:
        def __init__(self, role, account_id):
            self.role, self.account_id = role, account_id

    class _FakeStorage:
        def get_graph_account(self, graph_id):
            return "accB"

    app = Flask(__name__)
    with app.test_request_context():
        g.current_user = _U(ROLE_USER, "accA")
        current_app.extensions['neo4j_storage'] = _FakeStorage()
        with pytest.raises(PermissionError):
            graph_access.require_graph_account_access("g1")
