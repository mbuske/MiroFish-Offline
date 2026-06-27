# backend/tests/test_graph_curation_endpoints.py
import pytest
from app import create_app
import app.api.graph as graphmod
import app.models.project as pjmod


_TEST_TOKEN = "test-token-for-pytest"


class _FakeStorage:
    def __init__(self, account="acct1"):
        self.account = account
        self.deleted_nodes, self.deleted_edges, self.merged = [], [], []
    # access check helper used by require_graph_account_access path:
    def get_graph_account(self, graph_id):
        return self.account
    def update_node(self, uuid, fields):
        return {"uuid": uuid, "name": fields.get("name", "n"), "labels": [fields.get("entity_type", "Person")],
                "summary": fields.get("summary", ""), "attributes": fields.get("attributes", {})}
    def delete_node(self, uuid):
        self.deleted_nodes.append(uuid)
    def update_edge(self, euuid, fields):
        return {"uuid": euuid, "fact": fields.get("fact", ""), "name": fields.get("fact_type", "REL")}
    def delete_edge(self, euuid):
        self.deleted_edges.append(euuid)
    def merge_nodes(self, primary, dups):
        self.merged.append((primary, dups)); return {"uuid": primary, "name": "p", "labels": ["Person"]}


class _AuthClient:
    """Thin wrapper that auto-injects the bearer token on every request."""
    def __init__(self, tc, fake):
        self._tc = tc
        self._fake = fake

    def _headers(self, extra):
        h = dict(extra or {})
        h.setdefault("Authorization", f"Bearer {_TEST_TOKEN}")
        return h

    def get(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs.get("headers"))
        return self._tc.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs.get("headers"))
        return self._tc.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs.get("headers"))
        return self._tc.put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs.get("headers"))
        return self._tc.patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["headers"] = self._headers(kwargs.get("headers"))
        return self._tc.delete(*args, **kwargs)


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, API_TOKEN=_TEST_TOKEN)
    fake = _FakeStorage()
    app.extensions['neo4j_storage'] = fake
    monkeypatch.setattr(graphmod, "_get_storage", lambda: fake)
    # Access guard: allow when fake.account == "acct1"
    def _guard(graph_id):
        if fake.account != "acct1":
            raise PermissionError()
    monkeypatch.setattr(graphmod, "require_graph_account_access", _guard)
    # No project lookup -> skip 409 check
    monkeypatch.setattr(graphmod.ProjectManager, "get_project_by_graph_id",
                        staticmethod(lambda gid: None), raising=False)
    return _AuthClient(app.test_client(), fake)


def test_patch_node_ok(client):
    r = client.patch("/api/graph/g1/node/n1", json={"name": "X", "entity_type": "Worker"})
    assert r.status_code == 200
    assert r.get_json()["data"]["name"] == "X"


def test_delete_node_ok(client):
    r = client.delete("/api/graph/g1/node/n1")
    assert r.status_code == 200 and "n1" in client._fake.deleted_nodes


def test_patch_edge_ok(client):
    r = client.patch("/api/graph/g1/edge/e1", json={"fact": "f", "fact_type": "KNOWS"})
    assert r.status_code == 200 and r.get_json()["data"]["name"] == "KNOWS"


def test_delete_edge_ok(client):
    r = client.delete("/api/graph/g1/edge/e1")
    assert r.status_code == 200 and "e1" in client._fake.deleted_edges


def test_merge_ok(client):
    r = client.post("/api/graph/g1/merge", json={"primary": "p", "duplicates": ["d1", "d2"]})
    assert r.status_code == 200 and client._fake.merged == [("p", ["d1", "d2"])]


def test_merge_missing_primary_400(client):
    r = client.post("/api/graph/g1/merge", json={"duplicates": ["d1"]})
    assert r.status_code == 400


def test_merge_empty_duplicates_400(client):
    r = client.post("/api/graph/g1/merge", json={"primary": "p", "duplicates": []})
    assert r.status_code == 400


def test_cross_account_404(client):
    client._fake.account = "other"
    r = client.delete("/api/graph/g1/node/n1")
    assert r.status_code == 404


def test_patch_node_while_building_409(client, monkeypatch):
    class _P: status = None
    p = _P(); p.status = pjmod.ProjectStatus.GRAPH_BUILDING
    monkeypatch.setattr(graphmod.ProjectManager, "get_project_by_graph_id", staticmethod(lambda gid: p))
    r = client.patch("/api/graph/g1/node/n1", json={"name": "X"})
    assert r.status_code == 409
