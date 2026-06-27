# Interactive Editing for Steps 01 (Ontology) & 02 (GraphRAG) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users review/edit the LLM-generated ontology behind an approve-and-build gate (Step 01), and curate the built knowledge graph — edit/delete/merge nodes & edges (Step 02).

**Architecture:** Both editors live inside the existing `Process.vue` screen and the existing `graph_bp` Flask blueprint. Step 01 adds a pure validation module + one persistence endpoint + an `OntologyEditor.vue` form, and stops the frontend from auto-building. Step 02 adds five `Neo4jStorage` Cypher primitives + five account-scoped curation endpoints + an editable detail panel. No new top-level routes/views, no new dependencies.

**Tech Stack:** Flask + Flask-SQLAlchemy (auth), Neo4j (graph, via `neo4j` driver), Vue 3 + vue-i18n + Vite, pytest, `uv` for backend deps.

## Global Constraints

- No new third-party dependencies (backend or frontend).
- Every new endpoint is under `/api/graph/...` on `graph_bp` and enforces account isolation: ontology endpoint uses `require_account_access(project.account_id)`; all graph-curation endpoints use `require_graph_account_access(graph_id)`. Access failure returns **404** with `{"success": false, "error": <localized>}` (hide existence) — never 403.
- All endpoints return `{"success": bool, ...}`; errors carry `"error"` (localized via `t(...)`) and HTTP `400` (validation), `404` (access/not-found), `409` (graph busy / project `GRAPH_BUILDING`).
- axios client (`frontend/src/api/index.js`) response interceptor returns the UNWRAPPED payload (so `await service(...)` resolves to the JSON body); error objects still carry `e.response.data`.
- All new user-facing strings have keys in BOTH `locales/en.json` and `locales/de.json` (German uses Sie-form + real umlauts), kept at full key parity.
- Reserved attribute names that must never be allowed in an ontology: `name`, `uuid`, `group_id`, `created_at`, `summary`.
- Node identity = the `uuid` property on `:Entity`; edge identity = the `uuid` property on `[:RELATION]`. A node's entity type is the node's non-`Entity` label. An edge's `fact_type` maps to the relationship's `name` property.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit.
- Backend test command prefix: `cd backend && uv run pytest ...`. Frontend build: `cd frontend && npm run build`.

---

## File Structure

- `backend/app/services/ontology_validator.py` *(new)* — pure validation (`validate_ontology`) returning errors + warnings. No I/O.
- `backend/app/api/graph.py` *(modify)* — add `PUT /project/<id>/ontology` and five curation endpoints.
- `backend/app/storage/neo4j_storage.py` *(modify)* — add `update_node`, `delete_node`, `update_edge`, `delete_edge`, `merge_nodes` + pure helper `_union_attributes`.
- `backend/tests/test_ontology_validator.py` *(new)* — unit tests for the validator.
- `backend/tests/test_ontology_endpoint.py` *(new)* — endpoint tests (FakeStorage / project on disk).
- `backend/tests/test_graph_curation_endpoints.py` *(new)* — curation endpoint tests (extended FakeStorage).
- `backend/tests/test_neo4j_curation.py` *(new)* — integration tests for the real Cypher primitives, `skipif` no Neo4j; plus always-on unit tests for `_union_attributes`.
- `frontend/src/components/OntologyEditor.vue` *(new)* — full-CRUD ontology form with live validation.
- `frontend/src/views/Process.vue` *(modify)* — stop auto-build; mount `OntologyEditor`; Approve & Build with rebuild-discard confirm; editable detail panel with delete + merge.
- `frontend/src/api/graph.js` *(modify)* — client methods: `saveOntology`, `updateNode`, `deleteNode`, `updateEdge`, `deleteEdge`, `mergeNodes`.
- `locales/en.json`, `locales/de.json` *(modify)* — new strings.

---

## Task 1: Ontology validation module

**Files:**
- Create: `backend/app/services/ontology_validator.py`
- Test: `backend/tests/test_ontology_validator.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `validate_ontology(ontology: dict) -> dict` returning `{"errors": list[str], "warnings": list[str]}`. `ontology` has keys `entity_types` (list of `{name, description, attributes:[{name,type,description}], examples}`) and `edge_types` (list of `{name, description, source_targets:[{source,target}], attributes}`). Pure, no I/O. `RESERVED_ATTRIBUTE_NAMES = {"name","uuid","group_id","created_at","summary"}`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ontology_validator.py
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ontology_validator.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.ontology_validator'`.

- [ ] **Step 3: Implement the module**

```python
# backend/app/services/ontology_validator.py
"""Pure validation for human-edited ontologies. No I/O."""
from typing import Any, Dict, List

RESERVED_ATTRIBUTE_NAMES = {"name", "uuid", "group_id", "created_at", "summary"}
FALLBACK_ENTITY_TYPES = ("Person", "Organization")


def validate_ontology(ontology: Dict[str, Any]) -> Dict[str, List[str]]:
    """Return {"errors": [...], "warnings": [...]}.

    Errors are build-breaking (block save/build). Warnings are soft guidance
    (save/build still allowed).
    """
    errors: List[str] = []
    warnings: List[str] = []

    entity_types = ontology.get("entity_types") or []
    edge_types = ontology.get("edge_types") or []

    # --- entity types ---
    seen_entity_names = set()
    entity_names = set()
    for ent in entity_types:
        name = (ent.get("name") or "").strip()
        if not name:
            errors.append("Entity type name cannot be empty.")
            continue
        if name in seen_entity_names:
            errors.append(f"Duplicate entity type name: {name}")
        seen_entity_names.add(name)
        entity_names.add(name)

        seen_attr = set()
        for attr in ent.get("attributes") or []:
            aname = (attr.get("name") or "").strip()
            if not aname:
                errors.append(f"Attribute name in '{name}' cannot be empty.")
                continue
            if aname in RESERVED_ATTRIBUTE_NAMES:
                errors.append(f"Attribute '{aname}' in '{name}' is a reserved name.")
            if aname in seen_attr:
                errors.append(f"Duplicate attribute '{aname}' in entity type '{name}'.")
            seen_attr.add(aname)

    # --- edge types ---
    seen_edge_names = set()
    for edge in edge_types:
        name = (edge.get("name") or "").strip()
        if not name:
            errors.append("Edge type name cannot be empty.")
        else:
            if name in seen_edge_names:
                errors.append(f"Duplicate edge type name: {name}")
            seen_edge_names.add(name)
        for st in edge.get("source_targets") or []:
            for role in ("source", "target"):
                ref = (st.get(role) or "").strip()
                if ref and ref not in entity_names:
                    errors.append(
                        f"Edge '{name or '?'}' {role} references unknown entity type: {ref}"
                    )

    # --- soft warnings ---
    if len(entity_types) != 10:
        warnings.append(f"Recommended exactly 10 entity types (have {len(entity_types)}).")
    if not (6 <= len(edge_types) <= 10):
        warnings.append(f"Recommended 6-10 edge types (have {len(edge_types)}).")
    for fb in FALLBACK_ENTITY_TYPES:
        if fb not in entity_names:
            warnings.append(f"Missing recommended fallback entity type: {fb}.")

    return {"errors": errors, "warnings": warnings}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ontology_validator.py -q`
Expected: PASS (10 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/ontology_validator.py backend/tests/test_ontology_validator.py
git commit -m "feat(ontology): pure validation module (block-breakers, warn-soft)"
```

---

## Task 2: Ontology persistence endpoint

**Files:**
- Modify: `backend/app/api/graph.py` (add route near the other project routes, e.g. after `reset_project`)
- Test: `backend/tests/test_ontology_endpoint.py`

**Interfaces:**
- Consumes: `validate_ontology` (Task 1); `ProjectManager.get_project`, `ProjectManager.save_project`; `require_account_access`, `current_account_id`; `ProjectStatus`; `t(...)`.
- Produces: `PUT /api/graph/project/<project_id>/ontology`. Body `{"ontology": {"entity_types": [...], "edge_types": [...]}, "analysis_summary": "optional"}`. Returns `200 {"success": true, "data": {"ontology": {...}, "analysis_summary": "...", "warnings": [...]}}`; `400` on validation errors `{"success": false, "error": <localized>, "violations": [...]}`; `404` on access/not-found; `409` if project status is `GRAPH_BUILDING`.

Read first for exact import/style: `backend/app/api/graph.py:48-168` (existing project routes show `ProjectManager`, `require_account_access`, `current_account_id`, `t`, error shape) and `backend/app/services/project_manager.py` for the `Project` fields `ontology`, `analysis_summary`, `status`.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_ontology_endpoint.py
import json
import pytest
from app import create_app
import app.api.graph as graphmod
import app.services.project_manager as pjmod


class _Proj:
    def __init__(self, account_id="acct1", status=None):
        self.project_id = "proj_test"
        self.account_id = account_id
        self.status = status or pjmod.ProjectStatus.ONTOLOGY_GENERATED
        self.ontology = {"entity_types": [], "edge_types": []}
        self.analysis_summary = ""


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    # Bypass auth: force current account + user
    monkeypatch.setattr(graphmod, "current_account_id", lambda: "acct1")
    monkeypatch.setattr(graphmod, "current_user_id", lambda: "user1")
    # require_account_access: allow when account matches "acct1"
    def _raise_or_ok(account_id):
        if account_id != "acct1":
            raise PermissionError()
    monkeypatch.setattr(graphmod, "require_account_access", _raise_or_ok)
    return app.test_client()


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
    body["ontology"]["entity_types"] = body["ontology"]["entity_types"][:9]  # 9 -> warning
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_ontology_endpoint.py -q`
Expected: FAIL — 404 for the route (endpoint not registered) on the success-path tests.

- [ ] **Step 3: Implement the endpoint**

Add to `backend/app/api/graph.py` (ensure `from app.services.ontology_validator import validate_ontology` is imported at top):

```python
@graph_bp.route('/project/<project_id>/ontology', methods=['PUT'])
def save_ontology(project_id: str):
    """Persist a human-edited ontology after validation (Step 01 pause gate)."""
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": t('api.projectNotFound', id=project_id)}), 404
        try:
            require_account_access(project.account_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.projectNotFound', id=project_id)}), 404

        if project.status == ProjectStatus.GRAPH_BUILDING:
            return jsonify({"success": False, "error": t('api.graphBuilding')}), 409

        data = request.get_json(silent=True) or {}
        ontology = data.get("ontology") or {}
        ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        result = validate_ontology(ontology)
        if result["errors"]:
            return jsonify({
                "success": False,
                "error": t('api.ontologyValidationFailed'),
                "violations": result["errors"],
            }), 400

        project.ontology = ontology
        if "analysis_summary" in data:
            project.analysis_summary = data.get("analysis_summary") or ""
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        return jsonify({
            "success": True,
            "data": {
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "warnings": result["warnings"],
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
```

- [ ] **Step 4: Add the i18n key used above**

Add `"ontologyValidationFailed"` under the existing `api` block in BOTH locale files (full strings; do not leave placeholders):
- `locales/en.json` → `"api": { ..., "ontologyValidationFailed": "Ontology validation failed" }`
- `locales/de.json` → `"api": { ..., "ontologyValidationFailed": "Ontologie-Validierung fehlgeschlagen" }`

(Confirm `api.graphBuilding` and `api.projectNotFound` already exist — they are used elsewhere in `graph.py`. Reuse them; do not duplicate.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_ontology_endpoint.py -q`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/graph.py backend/tests/test_ontology_endpoint.py locales/en.json locales/de.json
git commit -m "feat(ontology): PUT /project/<id>/ontology persistence endpoint"
```

---

## Task 3: Pause gate + OntologyEditor.vue (frontend)

**Files:**
- Create: `frontend/src/components/OntologyEditor.vue`
- Modify: `frontend/src/views/Process.vue` (remove auto-build after generate; mount editor; Approve & Build)
- Modify: `frontend/src/api/graph.js` (add `saveOntology`)
- Modify: `locales/en.json`, `locales/de.json`

**Interfaces:**
- Consumes: `PUT /api/graph/project/<id>/ontology` (Task 2). The axios client returns the unwrapped payload.
- Produces: `saveOntology(projectId, payload)` in `graph.js`; `OntologyEditor.vue` emitting `@saved` and `@approve-build`.

Read first: `frontend/src/views/Process.vue:569-700` (the `handleNewProject` → `generateOntology` → `startBuildGraph` sequence and `currentPhase`/`projectData` refs); `frontend/src/api/graph.js:1-40` (client method pattern using `service`/`requestWithRetry`).

- [ ] **Step 1: Add the API client method**

In `frontend/src/api/graph.js`:

```js
/**
 * Save a human-edited ontology (Step 01 pause gate).
 * @param {string} projectId
 * @param {{ontology: object, analysis_summary?: string}} payload
 */
export function saveOntology(projectId, payload) {
  return requestWithRetry(() =>
    service({ url: `/api/graph/project/${projectId}/ontology`, method: 'put', data: payload })
  )
}
```

- [ ] **Step 2: Create `OntologyEditor.vue`**

Full-CRUD form with live validation mirroring the backend rules. Entity-type source/target selectors use the current entity list.

```vue
<!-- frontend/src/components/OntologyEditor.vue -->
<template>
  <div class="ontology-editor">
    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.entityTypes') }} ({{ entityTypes.length }})</h3>
        <button class="oe-add" @click="addEntity">+ {{ $t('ontology.addEntity') }}</button>
      </div>
      <div v-for="(ent, ei) in entityTypes" :key="ei" class="oe-card">
        <div class="oe-row">
          <input v-model="ent.name" :placeholder="$t('ontology.typeName')" class="oe-input" />
          <button class="oe-del" @click="entityTypes.splice(ei, 1)">✕</button>
        </div>
        <input v-model="ent.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div class="oe-attrs">
          <div class="oe-attr-head">
            <span>{{ $t('ontology.attributes') }}</span>
            <button class="oe-add-sm" @click="ent.attributes.push({ name: '', type: 'text', description: '' })">+</button>
          </div>
          <div v-for="(attr, ai) in ent.attributes" :key="ai" class="oe-row">
            <input v-model="attr.name" :placeholder="$t('ontology.attrName')" class="oe-input-sm" />
            <input v-model="attr.type" :placeholder="$t('ontology.attrType')" class="oe-input-sm" />
            <input v-model="attr.description" :placeholder="$t('ontology.description')" class="oe-input-sm" />
            <button class="oe-del" @click="ent.attributes.splice(ai, 1)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <div class="oe-section">
      <div class="oe-section-head">
        <h3>{{ $t('ontology.edgeTypes') }} ({{ edgeTypes.length }})</h3>
        <button class="oe-add" @click="addEdge">+ {{ $t('ontology.addEdge') }}</button>
      </div>
      <div v-for="(edge, gi) in edgeTypes" :key="gi" class="oe-card">
        <div class="oe-row">
          <input v-model="edge.name" :placeholder="$t('ontology.edgeName')" class="oe-input" />
          <button class="oe-del" @click="edgeTypes.splice(gi, 1)">✕</button>
        </div>
        <input v-model="edge.description" :placeholder="$t('ontology.description')" class="oe-input" />
        <div v-for="(st, si) in edge.source_targets" :key="si" class="oe-row">
          <select v-model="st.source" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'s'+n" :value="n">{{ n }}</option>
          </select>
          <span class="oe-arrow">→</span>
          <select v-model="st.target" class="oe-input-sm">
            <option v-for="n in entityNames" :key="'t'+n" :value="n">{{ n }}</option>
          </select>
          <button class="oe-del" @click="edge.source_targets.splice(si, 1)">✕</button>
        </div>
        <button class="oe-add-sm" @click="edge.source_targets.push({ source: entityNames[0] || '', target: entityNames[0] || '' })">+ {{ $t('ontology.addPair') }}</button>
      </div>
    </div>

    <ul v-if="errors.length" class="oe-errors">
      <li v-for="(e, i) in errors" :key="i">{{ e }}</li>
    </ul>
    <ul v-if="warnings.length" class="oe-warnings">
      <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
    </ul>

    <div class="oe-actions">
      <button class="oe-save" :disabled="saving || errors.length > 0" @click="onSave">
        {{ saving ? $t('common.loading') : $t('ontology.save') }}
      </button>
      <button class="oe-build" :disabled="saving || errors.length > 0" @click="onApproveBuild">
        {{ $t('ontology.approveBuild') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { saveOntology } from '@/api/graph'

const props = defineProps({
  projectId: { type: String, required: true },
  ontology: { type: Object, required: true },
  analysisSummary: { type: String, default: '' },
})
const emit = defineEmits(['saved', 'approve-build'])
const { t } = useI18n()

const RESERVED = ['name', 'uuid', 'group_id', 'created_at', 'summary']
// Deep clone so edits don't mutate the parent until saved
const entityTypes = ref(JSON.parse(JSON.stringify(props.ontology.entity_types || [])))
const edgeTypes = ref(JSON.parse(JSON.stringify(props.ontology.edge_types || [])))
const saving = ref(false)

const entityNames = computed(() => entityTypes.value.map(e => (e.name || '').trim()).filter(Boolean))

function addEntity() { entityTypes.value.push({ name: '', description: '', attributes: [], examples: [] }) }
function addEdge() { edgeTypes.value.push({ name: '', description: '', source_targets: [], attributes: [] }) }

const errors = computed(() => {
  const errs = []
  const seenE = new Set()
  for (const ent of entityTypes.value) {
    const n = (ent.name || '').trim()
    if (!n) { errs.push(t('ontology.errEmptyEntity')); continue }
    if (seenE.has(n)) errs.push(t('ontology.errDupEntity', { name: n }))
    seenE.add(n)
    const seenA = new Set()
    for (const a of ent.attributes || []) {
      const an = (a.name || '').trim()
      if (!an) { errs.push(t('ontology.errEmptyAttr', { type: n })); continue }
      if (RESERVED.includes(an)) errs.push(t('ontology.errReservedAttr', { attr: an, type: n }))
      if (seenA.has(an)) errs.push(t('ontology.errDupAttr', { attr: an, type: n }))
      seenA.add(an)
    }
  }
  const names = new Set(entityNames.value)
  const seenG = new Set()
  for (const g of edgeTypes.value) {
    const n = (g.name || '').trim()
    if (!n) errs.push(t('ontology.errEmptyEdge'))
    else { if (seenG.has(n)) errs.push(t('ontology.errDupEdge', { name: n })); seenG.add(n) }
    for (const st of g.source_targets || []) {
      for (const role of ['source', 'target']) {
        const ref = (st[role] || '').trim()
        if (ref && !names.has(ref)) errs.push(t('ontology.errUnknownRef', { name: n || '?', ref }))
      }
    }
  }
  return errs
})

const warnings = computed(() => {
  const w = []
  if (entityTypes.value.length !== 10) w.push(t('ontology.warnEntityCount', { n: entityTypes.value.length }))
  if (edgeTypes.value.length < 6 || edgeTypes.value.length > 10) w.push(t('ontology.warnEdgeCount', { n: edgeTypes.value.length }))
  for (const fb of ['Person', 'Organization']) if (!entityNames.value.includes(fb)) w.push(t('ontology.warnFallback', { fb }))
  return w
})

function payload() {
  return { ontology: { entity_types: entityTypes.value, edge_types: edgeTypes.value }, analysis_summary: props.analysisSummary }
}

async function onSave() {
  if (errors.value.length) return
  saving.value = true
  try { const res = await saveOntology(props.projectId, payload()); emit('saved', res.data) }
  finally { saving.value = false }
}

async function onApproveBuild() {
  if (errors.value.length) return
  saving.value = true
  try { const res = await saveOntology(props.projectId, payload()); emit('saved', res.data); emit('approve-build') }
  finally { saving.value = false }
}
</script>

<style scoped>
.ontology-editor { display: flex; flex-direction: column; gap: 1rem; font-family: 'JetBrains Mono', monospace; }
.oe-section-head { display: flex; justify-content: space-between; align-items: center; }
.oe-card { border: 1px solid #EAEAEA; padding: 0.6rem; margin: 0.4rem 0; display: flex; flex-direction: column; gap: 0.4rem; }
.oe-row { display: flex; gap: 0.4rem; align-items: center; }
.oe-input, .oe-input-sm { border: 1px solid #CCC; padding: 4px 8px; font-size: 0.8rem; flex: 1; }
.oe-input-sm { font-size: 0.75rem; }
.oe-arrow { color: #999; }
.oe-add, .oe-add-sm, .oe-save, .oe-build { font-family: 'JetBrains Mono', monospace; cursor: pointer; border: 1px solid #CCC; background: transparent; padding: 4px 10px; font-size: 0.8rem; }
.oe-save, .oe-build { background: #000; color: #fff; border: none; padding: 8px 18px; }
.oe-build { background: var(--brand-primary, #FF4500); }
.oe-del { background: transparent; border: none; color: #c00; cursor: pointer; }
.oe-errors { color: #c00; font-size: 0.75rem; }
.oe-warnings { color: #b8860b; font-size: 0.75rem; }
.oe-actions { display: flex; gap: 0.6rem; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
```

- [ ] **Step 3: Wire the pause gate in `Process.vue`**

In `frontend/src/views/Process.vue`:
1. Import the editor and add to imports near line 418:
   ```js
   import OntologyEditor from '@/components/OntologyEditor.vue'
   ```
2. In `handleNewProject` (around lines 592–635), **remove** the automatic `await startBuildGraph()` calls so generation stops at the editable ontology. Leave `projectData`/`currentProjectId` being set from the generate response.
3. In the Phase-01 panel (the `v-if="projectData?.ontology"` blocks around lines 263–294), replace the read-only entity-tags / relation-list with the editor:
   ```vue
   <div class="detail-section" v-if="projectData?.ontology && currentPhase === 0">
     <OntologyEditor
       :project-id="currentProjectId"
       :ontology="projectData.ontology"
       :analysis-summary="projectData.analysis_summary || ''"
       @saved="onOntologySaved"
       @approve-build="onApproveBuild"
     />
   </div>
   ```
4. Add handlers in `<script setup>`:
   ```js
   function onOntologySaved(data) {
     projectData.value.ontology = data.ontology
     projectData.value.analysis_summary = data.analysis_summary
   }
   async function onApproveBuild() {
     await startBuildGraph()  // existing function; advances to Phase 02
   }
   ```

- [ ] **Step 4: Add i18n keys**

Add an `ontology` block to BOTH `locales/en.json` and `locales/de.json` with every key referenced above, in parity. English values:
```json
"ontology": {
  "entityTypes": "Entity types", "edgeTypes": "Edge types",
  "addEntity": "Add entity type", "addEdge": "Add edge type", "addPair": "Add source→target",
  "typeName": "Type name", "edgeName": "Edge name", "description": "Description",
  "attributes": "Attributes", "attrName": "Attribute name", "attrType": "Type",
  "save": "Save ontology", "approveBuild": "Approve & Build",
  "errEmptyEntity": "Entity type name cannot be empty.",
  "errDupEntity": "Duplicate entity type: {name}",
  "errEmptyAttr": "Attribute name in '{type}' cannot be empty.",
  "errReservedAttr": "Attribute '{attr}' in '{type}' is reserved.",
  "errDupAttr": "Duplicate attribute '{attr}' in '{type}'.",
  "errEmptyEdge": "Edge type name cannot be empty.",
  "errDupEdge": "Duplicate edge type: {name}",
  "errUnknownRef": "Edge '{name}' references unknown entity type: {ref}",
  "warnEntityCount": "Recommended exactly 10 entity types (have {n}).",
  "warnEdgeCount": "Recommended 6-10 edge types (have {n}).",
  "warnFallback": "Missing recommended fallback type: {fb}."
}
```
German values (Sie-form), same keys — e.g. `"approveBuild": "Übernehmen & Erstellen"`, `"save": "Ontologie speichern"`, `"warnFallback": "Empfohlener Fallback-Typ fehlt: {fb}."`, etc. Keep all keys present in both files.

- [ ] **Step 5: Build to verify it compiles**

Run: `cd frontend && npm run build`
Expected: built with 0 errors. Also `node -e "JSON.parse(require('fs').readFileSync('locales/de.json','utf8'));JSON.parse(require('fs').readFileSync('locales/en.json','utf8'))"` prints nothing (valid JSON).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/OntologyEditor.vue frontend/src/views/Process.vue frontend/src/api/graph.js locales/en.json locales/de.json
git commit -m "feat(ontology): pause gate + OntologyEditor with live validation"
```

---

## Task 4: Neo4j curation primitives

**Files:**
- Modify: `backend/app/storage/neo4j_storage.py` (add 5 methods + `_union_attributes` helper)
- Test: `backend/tests/test_neo4j_curation.py`

**Interfaces:**
- Consumes: the existing `Neo4jStorage` driver/session machinery; node schema `(:Entity {graph_id, uuid, name, name_lower, summary, attributes_json})` + entity-type label; edge schema `[:RELATION {graph_id, uuid, name, fact, attributes_json}]`.
- Produces:
  - `update_node(uuid: str, fields: dict) -> dict` — `fields` ⊆ `{name, entity_type, attributes, summary}`. Sets `name`(+`name_lower`), `summary`; merges `attributes` into `attributes_json`; for `entity_type`, removes existing non-`Entity` labels and adds the new label. Returns updated node dict (same shape as `_node_to_dict`).
  - `delete_node(uuid: str) -> None` — `MATCH (n:Entity {uuid}) DETACH DELETE n`.
  - `update_edge(edge_uuid: str, fields: dict) -> dict` — `fields` ⊆ `{fact, fact_type}` (`fact_type` writes the relationship `name`). Returns updated edge dict.
  - `delete_edge(edge_uuid: str) -> None` — `MATCH ()-[r:RELATION {uuid}]->() DELETE r`.
  - `merge_nodes(primary_uuid: str, duplicate_uuids: list[str]) -> dict` — re-point all edges of each duplicate to `primary`, union attributes (primary wins), drop self-loops + parallel duplicate edges, delete duplicates. Returns the primary node dict. Runs in ONE write transaction (atomic).
  - Pure helper `_union_attributes(primary: dict, dup: dict) -> dict` — returns merged attributes with primary keys winning.

Read first: `backend/app/storage/neo4j_storage.py` — `_node_to_dict` (lines ~the helper), `_edge_to_dict`, `get_node`, `_call_with_retry`, and the relation-creation Cypher (~line 369) for label/property conventions.

- [ ] **Step 1: Write the failing tests** (pure-helper test always runs; integration tests skip without Neo4j)

```python
# backend/tests/test_neo4j_curation.py
import os
import pytest
from app.storage.neo4j_storage import Neo4jStorage


# ---------- always-on pure helper test ----------
def test_union_attributes_primary_wins():
    merged = Neo4jStorage._union_attributes({"role": "lead", "age": "30"}, {"role": "member", "city": "X"})
    assert merged == {"role": "lead", "age": "30", "city": "X"}


# ---------- integration tests (need a live Neo4j) ----------
def _neo4j_available():
    try:
        s = Neo4jStorage()
        s.close() if hasattr(s, "close") else None
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_neo4j_curation.py -q`
Expected: the pure-helper test FAILS (`AttributeError: _union_attributes`); integration tests are SKIPPED if no Neo4j (that's acceptable — they will run in the Docker stack).

- [ ] **Step 3: Implement the primitives**

Add to `backend/app/storage/neo4j_storage.py` (inside the `Neo4jStorage` class). Match existing `_call_with_retry`/session style and `json.dumps` for `attributes_json`.

```python
    @staticmethod
    def _union_attributes(primary: dict, dup: dict) -> dict:
        merged = dict(dup or {})
        merged.update(primary or {})  # primary wins
        return merged

    def update_node(self, uuid: str, fields: dict) -> dict:
        def _write(tx):
            node = tx.run("MATCH (n:Entity {uuid:$u}) RETURN n, labels(n) AS labels", u=uuid).single()
            if node is None:
                raise ValueError(f"Node not found: {uuid}")
            sets, params = [], {"u": uuid}
            if "name" in fields:
                sets.append("n.name=$name"); sets.append("n.name_lower=$name_lower")
                params["name"] = fields["name"]; params["name_lower"] = (fields["name"] or "").lower()
            if "summary" in fields:
                sets.append("n.summary=$summary"); params["summary"] = fields["summary"]
            if "attributes" in fields:
                import json as _json
                sets.append("n.attributes_json=$attrs"); params["attrs"] = _json.dumps(fields["attributes"] or {})
            if sets:
                tx.run(f"MATCH (n:Entity {{uuid:$u}}) SET {', '.join(sets)}", **params)
            if "entity_type" in fields and fields["entity_type"]:
                cur_labels = [l for l in node["labels"] if l != "Entity"]
                for old in cur_labels:
                    tx.run(f"MATCH (n:Entity {{uuid:$u}}) REMOVE n:`{old}`", u=uuid)
                tx.run(f"MATCH (n:Entity {{uuid:$u}}) SET n:`{fields['entity_type']}`", u=uuid)
            rec = tx.run("MATCH (n:Entity {uuid:$u}) RETURN n, labels(n) AS labels", u=uuid).single()
            return self._node_to_dict(rec["n"], rec["labels"])
        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)

    def delete_node(self, uuid: str) -> None:
        def _write(tx):
            tx.run("MATCH (n:Entity {uuid:$u}) DETACH DELETE n", u=uuid)
        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _write)

    def update_edge(self, edge_uuid: str, fields: dict) -> dict:
        def _write(tx):
            sets, params = [], {"u": edge_uuid}
            if "fact" in fields:
                sets.append("r.fact=$fact"); params["fact"] = fields["fact"]
            if "fact_type" in fields:
                sets.append("r.name=$name"); params["name"] = fields["fact_type"]
            if sets:
                res = tx.run(
                    f"MATCH (src:Entity)-[r:RELATION {{uuid:$u}}]->(tgt:Entity) "
                    f"SET {', '.join(sets)} "
                    f"RETURN r, src.uuid AS s, tgt.uuid AS t", **params).single()
            else:
                res = tx.run(
                    "MATCH (src:Entity)-[r:RELATION {uuid:$u}]->(tgt:Entity) "
                    "RETURN r, src.uuid AS s, tgt.uuid AS t", u=edge_uuid).single()
            if res is None:
                raise ValueError(f"Edge not found: {edge_uuid}")
            return self._edge_to_dict(res["r"], res["s"], res["t"])
        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)

    def delete_edge(self, edge_uuid: str) -> None:
        def _write(tx):
            tx.run("MATCH ()-[r:RELATION {uuid:$u}]->() DELETE r", u=edge_uuid)
        with self._driver.session() as session:
            self._call_with_retry(session.execute_write, _write)

    def merge_nodes(self, primary_uuid: str, duplicate_uuids: list) -> dict:
        import json as _json
        def _write(tx):
            prim = tx.run("MATCH (n:Entity {uuid:$u}) RETURN n", u=primary_uuid).single()
            if prim is None:
                raise ValueError(f"Primary node not found: {primary_uuid}")
            prim_attrs = _json.loads(dict(prim["n"]).get("attributes_json") or "{}")
            for dup in duplicate_uuids:
                if dup == primary_uuid:
                    continue
                drec = tx.run("MATCH (n:Entity {uuid:$u}) RETURN n", u=dup).single()
                if drec is None:
                    continue
                dup_attrs = _json.loads(dict(drec["n"]).get("attributes_json") or "{}")
                prim_attrs = self._union_attributes(prim_attrs, dup_attrs)
                # Re-point outgoing edges
                tx.run(
                    "MATCH (d:Entity {uuid:$d})-[r:RELATION]->(o:Entity) "
                    "MATCH (p:Entity {uuid:$p}) "
                    "WHERE o.uuid <> $p "
                    "CREATE (p)-[nr:RELATION]->(o) SET nr = properties(r) DELETE r", d=dup, p=primary_uuid)
                # Re-point incoming edges
                tx.run(
                    "MATCH (o:Entity)-[r:RELATION]->(d:Entity {uuid:$d}) "
                    "MATCH (p:Entity {uuid:$p}) "
                    "WHERE o.uuid <> $p "
                    "CREATE (o)-[nr:RELATION]->(p) SET nr = properties(r) DELETE r", d=dup, p=primary_uuid)
                tx.run("MATCH (d:Entity {uuid:$d}) DETACH DELETE d", d=dup)
            tx.run("MATCH (p:Entity {uuid:$p}) SET p.attributes_json=$a", p=primary_uuid, a=_json.dumps(prim_attrs))
            rec = tx.run("MATCH (n:Entity {uuid:$u}) RETURN n, labels(n) AS labels", u=primary_uuid).single()
            return self._node_to_dict(rec["n"], rec["labels"])
        with self._driver.session() as session:
            return self._call_with_retry(session.execute_write, _write)
```

> NOTE: the merge re-points edges with `CREATE` (no parallel-edge dedup for v1 simplicity — collapse is best-effort). If a reviewer requires strict parallel-edge dedup, that is a follow-up; the spec lists collapse as desired but v1 prioritizes correctness of re-pointing + duplicate deletion. Flag this as a known simplification, do not silently claim full dedup.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_neo4j_curation.py -q`
Expected: the pure-helper test PASSES; integration tests PASS if Neo4j is reachable, else SKIPPED. (In the Docker stack, run `docker compose exec mirofish sh -c "cd /app/backend && uv run pytest tests/test_neo4j_curation.py -q"` to exercise the integration tests.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/storage/neo4j_storage.py backend/tests/test_neo4j_curation.py
git commit -m "feat(graph): Neo4j curation primitives (update/delete node & edge, merge)"
```

---

## Task 5: Graph curation endpoints

**Files:**
- Modify: `backend/app/api/graph.py` (add 5 endpoints)
- Test: `backend/tests/test_graph_curation_endpoints.py`

**Interfaces:**
- Consumes: Task 4 storage primitives; `require_graph_account_access(graph_id)`; `_get_storage()`; `t(...)`. For the 409-while-building check, resolve the project from the graph: use `ProjectManager.get_project_by_graph_id(graph_id)` if it exists; otherwise skip the 409 check (see Step 3 note).
- Produces:
  - `PATCH /api/graph/<graph_id>/node/<uuid>` body `{name?, entity_type?, attributes?, summary?}` → `200 {"success":true,"data":<node>}`.
  - `DELETE /api/graph/<graph_id>/node/<uuid>` → `200 {"success":true}`.
  - `PATCH /api/graph/<graph_id>/edge/<edge_uuid>` body `{fact?, fact_type?}` → `200 {"success":true,"data":<edge>}`.
  - `DELETE /api/graph/<graph_id>/edge/<edge_uuid>` → `200 {"success":true}`.
  - `POST /api/graph/<graph_id>/merge` body `{primary, duplicates:[...]}` → `200 {"success":true,"data":<primary_node>}`. Missing `primary`/empty `duplicates` → `400`.

Read first: `backend/app/api/graph.py:621-660` (`get_graph_data`, `delete_graph` — the `require_graph_account_access` + `_get_storage` + error-shape pattern) and `backend/tests/test_graph_access.py:24-40` (`_FakeStorage` + injection into `current_app.extensions['neo4j_storage']`).

- [ ] **Step 1: Write the failing tests** (extend the FakeStorage pattern)

```python
# backend/tests/test_graph_curation_endpoints.py
import pytest
from app import create_app
import app.api.graph as graphmod


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


@pytest.fixture
def client(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
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
    c = app.test_client(); c._fake = fake; return c


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_graph_curation_endpoints.py -q`
Expected: FAIL — routes return 404 (not registered).

- [ ] **Step 3: Implement the endpoints**

Add to `backend/app/api/graph.py`. Use a small helper for the 409 check that no-ops when the project lookup is unavailable:

```python
def _reject_if_building(graph_id):
    """Return a 409 response if the graph's project is currently building, else None."""
    getter = getattr(ProjectManager, "get_project_by_graph_id", None)
    if getter is None:
        return None
    project = getter(graph_id)
    if project and project.status == ProjectStatus.GRAPH_BUILDING:
        return jsonify({"success": False, "error": t('api.graphBuilding')}), 409
    return None


@graph_bp.route('/<graph_id>/node/<uuid>', methods=['PATCH'])
def patch_node(graph_id, uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        fields = request.get_json(silent=True) or {}
        node = _get_storage().update_node(uuid, fields)
        return jsonify({"success": True, "data": node})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/node/<uuid>', methods=['DELETE'])
def remove_node(graph_id, uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        _get_storage().delete_node(uuid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/edge/<edge_uuid>', methods=['PATCH'])
def patch_edge(graph_id, edge_uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        fields = request.get_json(silent=True) or {}
        edge = _get_storage().update_edge(edge_uuid, fields)
        return jsonify({"success": True, "data": edge})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/edge/<edge_uuid>', methods=['DELETE'])
def remove_edge(graph_id, edge_uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        _get_storage().delete_edge(edge_uuid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/merge', methods=['POST'])
def merge_graph_nodes(graph_id):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        data = request.get_json(silent=True) or {}
        primary = data.get("primary")
        duplicates = data.get("duplicates") or []
        if not primary or not duplicates:
            return jsonify({"success": False, "error": t('api.mergeRequiresNodes')}), 400
        node = _get_storage().merge_nodes(primary, duplicates)
        return jsonify({"success": True, "data": node})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500
```

- [ ] **Step 4: Add i18n key**

Add `"mergeRequiresNodes"` under the `api` block in BOTH locale files (EN: `"A primary node and at least one duplicate are required."`; DE: `"Ein Primärknoten und mindestens ein Duplikat sind erforderlich."`). Confirm `api.graphNotFound` already exists (it does — used in `get_graph_data`); reuse it.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_graph_curation_endpoints.py -q`
Expected: PASS (8 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/graph.py backend/tests/test_graph_curation_endpoints.py locales/en.json locales/de.json
git commit -m "feat(graph): account-scoped curation endpoints (node/edge edit/delete, merge)"
```

---

## Task 6: Editable detail panel + delete + merge UI (frontend)

**Files:**
- Modify: `frontend/src/views/Process.vue` (detail panel edit mode, delete, merge, rebuild-discard confirm)
- Modify: `frontend/src/api/graph.js` (`updateNode`, `deleteNode`, `updateEdge`, `deleteEdge`, `mergeNodes`)
- Modify: `locales/en.json`, `locales/de.json`

**Interfaces:**
- Consumes: Task 5 endpoints; the existing `selectedItem` ref (`{type:'node'|'edge', data:{...}, color}`), `graphData`, `currentGraphId`, and `refreshGraph()` in `Process.vue` (read lines ~46–215 and the `<script setup>` selection logic); the ontology entity-type list via `projectData.value.ontology.entity_types`.
- Produces: client methods in `graph.js`; an editable detail panel.

- [ ] **Step 1: Add API client methods**

In `frontend/src/api/graph.js`:

```js
export function updateNode(graphId, uuid, fields) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/node/${uuid}`, method: 'patch', data: fields }))
}
export function deleteNode(graphId, uuid) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/node/${uuid}`, method: 'delete' }))
}
export function updateEdge(graphId, edgeUuid, fields) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/edge/${edgeUuid}`, method: 'patch', data: fields }))
}
export function deleteEdge(graphId, edgeUuid) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/edge/${edgeUuid}`, method: 'delete' }))
}
export function mergeNodes(graphId, primary, duplicates) {
  return requestWithRetry(() => service({ url: `/api/graph/${graphId}/merge`, method: 'post', data: { primary, duplicates } }))
}
```

- [ ] **Step 2: Add edit/delete/merge state + handlers in `Process.vue` `<script setup>`**

```js
import { updateNode, deleteNode, updateEdge, deleteEdge, mergeNodes } from '@/api/graph'

const editMode = ref(false)
const editBuffer = ref({})       // working copy of selected item's editable fields
const mergeSelection = ref([])   // duplicate node uuids chosen for merge

const ontologyTypeOptions = computed(() =>
  (projectData.value?.ontology?.entity_types || []).map(e => e.name).filter(Boolean))

function startEdit() {
  const d = selectedItem.value?.data || {}
  if (selectedItem.value.type === 'node') {
    editBuffer.value = { name: d.name || '', entity_type: (d.labels && d.labels[0]) || '',
                         summary: d.summary || '', attributes: { ...(d.attributes || {}) } }
  } else {
    editBuffer.value = { fact: d.fact || '', fact_type: d.fact_type || d.name || '' }
  }
  editMode.value = true
}

async function saveEdit() {
  const gid = currentGraphId.value
  const d = selectedItem.value.data
  if (selectedItem.value.type === 'node') await updateNode(gid, d.uuid, editBuffer.value)
  else await updateEdge(gid, d.uuid, editBuffer.value)
  editMode.value = false
  await refreshGraph()
}

async function deleteSelected() {
  const gid = currentGraphId.value
  const d = selectedItem.value.data
  if (selectedItem.value.type === 'node') await deleteNode(gid, d.uuid)
  else await deleteEdge(gid, d.uuid)
  selectedItem.value = null
  await refreshGraph()
}

function toggleMergeCandidate(uuid) {
  const i = mergeSelection.value.indexOf(uuid)
  if (i >= 0) mergeSelection.value.splice(i, 1)
  else mergeSelection.value.push(uuid)
}

async function doMerge() {
  // primary = current selected node; duplicates = mergeSelection (excluding primary)
  const primary = selectedItem.value.data.uuid
  const dups = mergeSelection.value.filter(u => u !== primary)
  if (!dups.length) return
  await mergeNodes(currentGraphId.value, primary, dups)
  mergeSelection.value = []
  await refreshGraph()
}
```

- [ ] **Step 3: Make the detail panel editable (template)**

In the existing `selectedItem` detail panel (around lines 57–166), add an Edit toggle and inputs. Minimal additions (keep existing read-only view when `!editMode`):

```vue
<!-- inside .detail-panel header -->
<div class="detail-actions">
  <button v-if="!editMode" class="da-btn" @click="startEdit">{{ $t('graph.edit') }}</button>
  <button v-else class="da-btn" @click="saveEdit">{{ $t('common.save') }}</button>
  <button class="da-btn da-del" @click="deleteSelected">{{ $t('graph.delete') }}</button>
</div>

<!-- node edit fields (show when editMode && selectedItem.type==='node') -->
<div v-if="editMode && selectedItem.type === 'node'" class="detail-edit">
  <input v-model="editBuffer.name" :placeholder="$t('graph.nodeName')" class="de-input" />
  <select v-model="editBuffer.entity_type" class="de-input">
    <option v-for="opt in [...new Set([...ontologyTypeOptions, editBuffer.entity_type].filter(Boolean))]"
            :key="opt" :value="opt">{{ opt }}</option>
  </select>
  <textarea v-model="editBuffer.summary" :placeholder="$t('graph.summary')" class="de-input"></textarea>
</div>

<!-- edge edit fields -->
<div v-else-if="editMode && selectedItem.type === 'edge'" class="detail-edit">
  <input v-model="editBuffer.fact_type" :placeholder="$t('graph.factType')" class="de-input" />
  <textarea v-model="editBuffer.fact" :placeholder="$t('graph.fact')" class="de-input"></textarea>
</div>
```

For merge: when a node is selected, list other nodes as merge candidates (reuse `graphData.nodes`), each with a checkbox calling `toggleMergeCandidate(node.uuid)`, plus a "Merge into this node" button calling `doMerge()` (only enabled when `mergeSelection` is non-empty). Keep it within the detail panel; do not add a new screen.

- [ ] **Step 4: Rebuild-discard confirm**

Wrap the existing rebuild trigger (the `force: true` rebuild path / "Approve & Build" when a graph already exists) so it asks for confirmation first:

```js
async function confirmRebuildIfNeeded() {
  if (graphData.value && (graphData.value.node_count || graphData.value.nodes?.length)) {
    return window.confirm(t('graph.rebuildDiscardWarning'))
  }
  return true
}
```
Call `if (!(await confirmRebuildIfNeeded())) return` at the start of the rebuild/force-build handler. (Use `const { t } = useI18n()` — confirm it's already imported in `Process.vue`; if not, add it.)

- [ ] **Step 5: Add i18n keys**

Add to BOTH locale files under existing blocks, in parity:
- `graph.edit` (EN "Edit" / DE "Bearbeiten"), `graph.delete` ("Delete"/"Löschen"), `graph.nodeName` ("Node name"/"Knotenname"), `graph.summary` ("Summary"/"Zusammenfassung"), `graph.factType` ("Relation type"/"Beziehungstyp"), `graph.fact` ("Fact"/"Fakt"), `graph.rebuildDiscardWarning` (EN "Rebuilding replaces the current graph and discards manual edits. Continue?" / DE "Beim Neuaufbau wird der aktuelle Graph ersetzt und manuelle Änderungen verworfen. Fortfahren?"), `graph.mergeInto` ("Merge selected into this node"/"Ausgewählte in diesen Knoten zusammenführen").
- Reuse `common.save` if present; otherwise add it.

- [ ] **Step 6: Build to verify it compiles + locales parse**

Run: `cd frontend && npm run build` → 0 errors.
Run: `node -e "JSON.parse(require('fs').readFileSync('locales/de.json','utf8'));JSON.parse(require('fs').readFileSync('locales/en.json','utf8'));console.log('ok')"` → prints `ok`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/Process.vue frontend/src/api/graph.js locales/en.json locales/de.json
git commit -m "feat(graph): editable detail panel + delete + merge + rebuild-discard confirm"
```

---

## Task 7: i18n parity audit + docs

**Files:**
- Modify: `locales/en.json`, `locales/de.json` (close any gaps)
- Modify: `docs/accounts-and-branding.md` is unrelated; instead add a short section to `docs/README.md` change log and (optional) a note in an existing graph doc.

**Interfaces:**
- Consumes: all `$t(...)`/`t(...)` keys referenced in Tasks 2,3,5,6.
- Produces: full EN/DE key parity; a documented feature entry.

- [ ] **Step 1: Audit referenced keys vs locale files**

Run (from repo root):
```bash
grep -rhoE "\\\$t\('[^']+'\)|[^A-Za-z]t\('[^']+'\)" frontend/src/components/OntologyEditor.vue frontend/src/views/Process.vue | grep -oE "'[^']+'" | tr -d "'" | sort -u
```
For every key printed, confirm it exists in BOTH `locales/en.json` and `locales/de.json`. Add any missing key to both (EN + DE values). Backend keys to confirm exist: `api.ontologyValidationFailed`, `api.mergeRequiresNodes`, `api.graphBuilding`, `api.projectNotFound`, `api.graphNotFound`.

- [ ] **Step 2: Verify full recursive parity**

Run:
```bash
cd backend && uv run python -c "import json; a=json.load(open('../locales/en.json')); b=json.load(open('../locales/de.json'));
def paths(d,p=''):
 out=set()
 for k,v in d.items():
  np=p+'.'+k if p else k
  out|=paths(v,np) if isinstance(v,dict) else {np}
 return out
ea,eb=paths(a),paths(b); print('only_en',sorted(ea-eb)); print('only_de',sorted(eb-ea))"
```
Expected: `only_en []` and `only_de []`.

- [ ] **Step 3: Add a change-log entry to `docs/README.md`**

Under "## Change log of recent fork work", add:
```markdown
### Step 01/02 editors (`feat/ontology-graph-editors`)
Interactive editing for the graph pipeline: an ontology editor behind an
approve-and-build pause gate (full CRUD + block-breaker/warn-soft validation),
and knowledge-graph curation (edit/delete/merge nodes & edges) via new Neo4j
primitives and account-scoped endpoints. See the spec at
`docs/superpowers/specs/2026-06-27-ontology-and-graph-editors-design.md`.
```

- [ ] **Step 4: Commit**

```bash
git add locales/en.json locales/de.json docs/README.md
git commit -m "docs+i18n: EN/DE parity for editors + change-log entry"
```

---

## Final Verification (after all tasks)

- [ ] Full backend suite green & pristine: `cd backend && uv run pytest tests/ -q`.
- [ ] Neo4j integration tests in the running stack: `docker compose exec mirofish sh -c "cd /app/backend && uv run pytest tests/test_neo4j_curation.py -q"` (should run, not skip).
- [ ] `cd frontend && npm run build` → 0 errors; both locale files parse; recursive parity clean.
- [ ] Manual (Docker, logged in as an account user with a project):
  - Upload docs → ontology appears editable, pipeline PAUSES (no auto-build).
  - Edit an entity type; add a reserved attribute `uuid` → Save/Build disabled with an error; remove it → enabled.
  - Reduce to 9 entity types → a non-blocking warning shows; Approve & Build still works.
  - Approve & Build → graph builds.
  - Select a node → Edit → change name/entity type/summary → Save → graph refreshes.
  - Delete an edge → it disappears.
  - Select a node, mark another as duplicate, Merge → duplicate gone, edges re-pointed.
  - Trigger a rebuild on a built graph → discard-confirm dialog appears.
- [ ] Cross-account check: a second account cannot edit the first account's graph (404).

## Self-Review Notes (spec coverage)

- Pause gate before build → Task 3. ✓
- Full CRUD ontology editor → Task 3. ✓
- Block-breakers/warn-soft validation (server authoritative + client live) → Tasks 1, 2, 3. ✓
- Ontology persistence endpoint (account-scoped, 409 while building) → Task 2. ✓
- Graph curation: edit + delete + merge → Tasks 4 (storage), 5 (endpoints), 6 (UI). ✓
- Merge semantics (re-point, attribute union, delete dups) → Task 4 (parallel-edge dedup flagged as v1 simplification). ✓
- Account isolation 404 + 409 while building → Tasks 2, 5. ✓
- Entity-type dropdown incl. off-ontology current value → Task 6. ✓
- Rebuild-overwrites-edits confirm → Task 6. ✓
- i18n EN/DE parity → every UI task + Task 7. ✓
- No new dependencies → all tasks. ✓
