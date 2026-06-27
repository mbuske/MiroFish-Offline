# backend/tests/test_ontology_endpoint.py
import json
import pytest
from app import create_app
import app.api.graph as graphmod
import app.models.project as pjmod


class _Proj:
    def __init__(self, account_id="acct1", status=None):
        self.project_id = "proj_test"
        self.account_id = account_id
        self.status = status or pjmod.ProjectStatus.ONTOLOGY_GENERATED
        self.ontology = {"entity_types": [], "edge_types": []}
        self.analysis_summary = ""


_TEST_TOKEN = "test-token-for-pytest"


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, API_TOKEN=_TEST_TOKEN)
    # Bypass auth: force current account + user
    monkeypatch.setattr(graphmod, "current_account_id", lambda: "acct1")
    monkeypatch.setattr(graphmod, "current_user_id", lambda: "user1")
    # require_account_access: allow when account matches "acct1"
    def _raise_or_ok(account_id):
        if account_id != "acct1":
            raise PermissionError()
    monkeypatch.setattr(graphmod, "require_account_access", _raise_or_ok)

    class _AuthClient:
        """Thin wrapper that auto-injects the bearer token on every request."""
        def __init__(self, tc):
            self._tc = tc

        def _headers(self, extra):
            h = dict(extra or {})
            h.setdefault("Authorization", f"Bearer {_TEST_TOKEN}")
            return h

        def put(self, *args, **kwargs):
            kwargs["headers"] = self._headers(kwargs.get("headers"))
            return self._tc.put(*args, **kwargs)

        def get(self, *args, **kwargs):
            kwargs["headers"] = self._headers(kwargs.get("headers"))
            return self._tc.get(*args, **kwargs)

        def post(self, *args, **kwargs):
            kwargs["headers"] = self._headers(kwargs.get("headers"))
            return self._tc.post(*args, **kwargs)

        def delete(self, *args, **kwargs):
            kwargs["headers"] = self._headers(kwargs.get("headers"))
            return self._tc.delete(*args, **kwargs)

    return _AuthClient(app.test_client())


def _valid_body():
    specifics = [{"name": f"Type{i}", "description": "d", "attributes": [], "examples": []} for i in range(8)]
    entities = specifics + [
        {"name": "Person", "description": "d", "attributes": [], "examples": []},
        {"name": "Organization", "description": "d", "attributes": [], "examples": []},
    ]
    edges = [{"name": f"REL_{i}", "description": "d",
              "source_targets": [{"source": "Person", "target": "Organization"}], "attributes": []}
             for i in range(6)]
    return {"ontology": {"entity_types": entities, "edge_types": edges}, "analysis_summary": "s"}


def test_save_ontology_persists_and_returns_saved(client, monkeypatch):
    proj = _Proj()
    saved = {}
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: proj))
    monkeypatch.setattr(graphmod.ProjectManager, "save_project", staticmethod(lambda p: saved.update({"p": p})))
    resp = client.put("/api/graph/project/proj_test/ontology", json=_valid_body())
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert len(data["data"]["ontology"]["entity_types"]) == 10
    assert data["data"]["warnings"] == []
    assert proj.ontology["entity_types"][0]["name"] == "Type0"


def test_save_ontology_with_breaker_returns_400(client, monkeypatch):
    proj = _Proj()
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: proj))
    monkeypatch.setattr(graphmod.ProjectManager, "save_project", staticmethod(lambda p: None))
    body = _valid_body()
    body["ontology"]["entity_types"][0]["attributes"] = [{"name": "uuid", "type": "text", "description": ""}]
    resp = client.put("/api/graph/project/proj_test/ontology", json=body)
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
    assert resp.get_json()["violations"]


def test_save_ontology_allows_warnings(client, monkeypatch):
    proj = _Proj()
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: proj))
    monkeypatch.setattr(graphmod.ProjectManager, "save_project", staticmethod(lambda p: None))
    body = _valid_body()
    body["ontology"]["entity_types"] = body["ontology"]["entity_types"][1:]  # 9 -> warning (drop Type0, keep Person+Organization)
    resp = client.put("/api/graph/project/proj_test/ontology", json=body)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["warnings"]


def test_save_ontology_cross_account_404(client, monkeypatch):
    proj = _Proj(account_id="other")
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: proj))
    monkeypatch.setattr(graphmod.ProjectManager, "save_project", staticmethod(lambda p: None))
    resp = client.put("/api/graph/project/proj_test/ontology", json=_valid_body())
    assert resp.status_code == 404


def test_save_ontology_while_building_409(client, monkeypatch):
    proj = _Proj(status=pjmod.ProjectStatus.GRAPH_BUILDING)
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: proj))
    monkeypatch.setattr(graphmod.ProjectManager, "save_project", staticmethod(lambda p: None))
    resp = client.put("/api/graph/project/proj_test/ontology", json=_valid_body())
    assert resp.status_code == 409


def test_save_ontology_not_found_404(client, monkeypatch):
    monkeypatch.setattr(graphmod.ProjectManager, "get_project", staticmethod(lambda pid: None))
    resp = client.put("/api/graph/project/missing/ontology", json=_valid_body())
    assert resp.status_code == 404
