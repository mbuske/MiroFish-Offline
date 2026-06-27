from app.services.ontology_validator import validate_ontology, RESERVED_ATTRIBUTE_NAMES


def _entity(name, attrs=None):
    return {"name": name, "description": "d", "attributes": attrs or [], "examples": []}


def _edge(name, src, tgt):
    return {"name": name, "description": "d",
            "source_targets": [{"source": src, "target": tgt}], "attributes": []}


def _valid_ontology():
    # 10 entity types incl. Person/Organization fallbacks, 6 edges
    specifics = [f"Type{i}" for i in range(8)]
    entities = [_entity(n) for n in specifics] + [_entity("Person"), _entity("Organization")]
    edges = [_edge(f"REL_{i}", "Person", "Organization") for i in range(6)]
    return {"entity_types": entities, "edge_types": edges}


def test_valid_ontology_has_no_errors_or_warnings():
    res = validate_ontology(_valid_ontology())
    assert res["errors"] == []
    assert res["warnings"] == []


def test_empty_entity_name_is_error():
    o = _valid_ontology()
    o["entity_types"][0]["name"] = ""
    res = validate_ontology(o)
    assert any("empty" in e.lower() for e in res["errors"])


def test_duplicate_entity_name_is_error():
    o = _valid_ontology()
    o["entity_types"][1]["name"] = o["entity_types"][0]["name"]
    res = validate_ontology(o)
    assert any("duplicate" in e.lower() for e in res["errors"])


def test_reserved_attribute_name_is_error():
    o = _valid_ontology()
    o["entity_types"][0]["attributes"] = [{"name": "uuid", "type": "text", "description": ""}]
    res = validate_ontology(o)
    assert any("reserved" in e.lower() for e in res["errors"])


def test_duplicate_attribute_within_type_is_error():
    o = _valid_ontology()
    o["entity_types"][0]["attributes"] = [
        {"name": "role", "type": "text", "description": ""},
        {"name": "role", "type": "text", "description": ""},
    ]
    res = validate_ontology(o)
    assert any("duplicate attribute" in e.lower() for e in res["errors"])


def test_edge_referencing_unknown_entity_is_error():
    o = _valid_ontology()
    o["edge_types"][0]["source_targets"] = [{"source": "Nope", "target": "Person"}]
    res = validate_ontology(o)
    assert any("nope" in e.lower() for e in res["errors"])


def test_duplicate_edge_name_is_error():
    o = _valid_ontology()
    o["edge_types"][1]["name"] = o["edge_types"][0]["name"]
    res = validate_ontology(o)
    assert any("duplicate" in e.lower() for e in res["errors"])


def test_entity_count_not_ten_is_warning():
    o = _valid_ontology()
    o["entity_types"] = o["entity_types"][:9]  # 9 entities
    o["edge_types"] = []  # Clear edges to avoid referencing removed Organization
    res = validate_ontology(o)
    assert res["errors"] == []
    assert any("10" in w for w in res["warnings"])


def test_edge_count_out_of_range_is_warning():
    o = _valid_ontology()
    o["edge_types"] = o["edge_types"][:5]  # 5 edges (< 6)
    res = validate_ontology(o)
    assert any("6" in w or "10" in w for w in res["warnings"])


def test_missing_fallback_type_is_warning():
    o = _valid_ontology()
    o["entity_types"][-1]["name"] = "SomethingElse"  # drop Organization
    res = validate_ontology(o)
    assert any("organization" in w.lower() for w in res["warnings"])
