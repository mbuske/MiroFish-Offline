# backend/tests/test_neo4j_curation.py
import os
import pytest
from app.storage.neo4j_storage import Neo4jStorage


# ---------- always-on pure helper test ----------
def test_assert_valid_label_accepts_good_and_rejects_bad():
    Neo4jStorage._assert_valid_label("Person")       # no raise
    Neo4jStorage._assert_valid_label("Worker_2")     # no raise
    for bad in ["Foo` SET n.x=1", "has space", "", "1Starts", "a-b"]:
        with pytest.raises(ValueError):
            Neo4jStorage._assert_valid_label(bad)


def test_union_attributes_primary_wins():
    merged = Neo4jStorage._union_attributes({"role": "lead", "age": "30"}, {"role": "member", "city": "X"})
    assert merged == {"role": "lead", "age": "30", "city": "X"}


# ---------- integration tests (need a live Neo4j) ----------
def _neo4j_available():
    try:
        s = Neo4jStorage()
        s._driver.verify_connectivity()
        return True
    except Exception:
        return False


pytestmark_int = pytest.mark.skipif(not _neo4j_available(), reason="No Neo4j available")


@pytest.fixture
def graph():
    s = Neo4jStorage()
    gid = s.create_graph("curation-test")
    yield s, gid
    s.delete_graph(gid)


@pytestmark_int
def test_update_node_changes_fields_and_label(graph):
    s, gid = graph
    # Build a tiny graph: add_text creates entities/edges via the pipeline.
    # For a deterministic node, use create helpers if available; otherwise add_text.
    s.add_text(gid, "Alice works at Acme. Alice is a Person.")
    nodes = s.get_all_nodes(gid)
    n = nodes[0]
    updated = s.update_node(n["uuid"], {"name": "Alice2", "summary": "s2",
                                        "attributes": {"role": "lead"}, "entity_type": "Worker"})
    assert updated["name"] == "Alice2"
    assert updated["summary"] == "s2"
    assert updated["attributes"].get("role") == "lead"
    assert "Worker" in updated["labels"]


@pytestmark_int
def test_delete_node_removes_node_and_incident_edges(graph):
    s, gid = graph
    s.add_text(gid, "Alice works at Acme.")
    nodes = s.get_all_nodes(gid)
    uuid = nodes[0]["uuid"]
    s.delete_node(uuid)
    assert s.get_node(uuid) is None


@pytestmark_int
def test_merge_nodes_repoints_edges_and_deletes_duplicates(graph):
    s, gid = graph
    s.add_text(gid, "Alice works at Acme. Alicia works at Acme.")
    nodes = s.get_all_nodes(gid)
    # pick two person-like nodes as primary/dup (test environment dependent)
    primary, dup = nodes[0]["uuid"], nodes[1]["uuid"]
    s.merge_nodes(primary, [dup])
    assert s.get_node(dup) is None
    assert s.get_node(primary) is not None
