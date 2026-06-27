# Design: Interactive Editing for Steps 01 (Ontology) & 02 (GraphRAG)

**Date:** 2026-06-27
**Status:** Approved (design) — pending implementation plan
**Builds on:** the existing graph pipeline (`backend/app/api/graph.py`, `frontend/src/views/Process.vue`, `backend/app/storage/neo4j_storage.py`) and the multi-tenant access model (`require_account_access`, `require_graph_account_access`).
**Branch:** new feature branch off `main`.

---

## 1. Goals & Decisions

Today the graph pipeline is automatic and read-only: Step 01 generates an ontology with the LLM and immediately feeds it into Step 02, which builds the Neo4j knowledge graph; neither the ontology nor the built graph can be edited. This feature makes both steps human-editable.

| Decision | Choice |
|----------|--------|
| Step 01 workflow | **Pause gate before build.** After generation the pipeline stops on an editable ontology; the build runs only when the user clicks **Approve & Build**. |
| Step 01 edit depth | **Full CRUD** on entity types and edge types (names, descriptions, attributes, examples, edge source→target pairs) and the analysis summary. |
| Step 01 validation | **Block breakers, warn on soft rules.** Hard-block build-breaking input; show non-blocking warnings for the generator's soft guidance. |
| Step 02 edit depth | **Curate: edit + delete + merge.** Edit a selected node/edge's fields, delete wrong nodes/edges, merge duplicate nodes. No free-form authoring. |
| Packaging | **One spec, one plan, phased — Step 01 first, then Step 02.** |
| Account isolation | Reuse existing guards; 404 on mismatch. |

**Non-goals (YAGNI):** free-form graph authoring (manually adding nodes/drawing edges), bulk/multi-select field editing, ontology versioning/history, retroactively applying ontology edits to an already-built graph (only a rebuild does that), editing during an in-progress build.

---

## 2. Architecture

Both editors live **inside the existing `Process.vue` screen** and the existing `graph_bp` blueprint — no new top-level views or routes. The screen keeps its two-pane layout (left: live graph + detail panel; right: phase panel). Step 01's editor is a new component rendered in the Phase-01 panel; Step 02's editor extends the existing left-pane detail panel.

The backend already separates `/api/graph/ontology/generate` from `/api/graph/build`, so the pause gate is primarily a **frontend** change (stop auto-calling build) plus one new ontology-persistence endpoint. Step 02 needs new Neo4j write primitives and curation endpoints.

---

## 3. Step 01 — Ontology Editor

### 3.1 Data model (unchanged shape)

`project.ontology` already stores:

```jsonc
{
  "entity_types": [
    { "name": "Student",            // PascalCase, unique, non-empty
      "description": "…",
      "attributes": [ { "name": "full_name", "type": "text", "description": "…" } ],
      "examples": ["…"] }
  ],
  "edge_types": [
    { "name": "ENROLLED_IN",        // UPPER_SNAKE_CASE, unique, non-empty
      "description": "…",
      "source_targets": [ { "source": "Student", "target": "University" } ],
      "attributes": [] }
  ]
}
```

`project.analysis_summary` is a sibling string field. Editing reuses these fields; no schema change.

### 3.2 Flow (pause gate)

1. `handleNewProject` calls `/ontology/generate` (unchanged) and **stops** — it no longer calls `startBuildGraph()` automatically. Project status is `ONTOLOGY_GENERATED`.
2. The Phase-01 panel renders the ontology in `OntologyEditor.vue` (editable).
3. On save, the frontend calls the new endpoint (§3.4) which validates and persists `project.ontology` + `project.analysis_summary`.
4. **Approve & Build** calls the existing `/api/graph/build` for the project → Step 02.

### 3.3 `OntologyEditor.vue`

Full CRUD:
- **Entity types:** add / rename / delete; edit description; edit `attributes[]` (name, type, description); edit `examples[]`.
- **Edge types:** add / delete; edit description; edit `source_targets[]` where `source`/`target` are selected from the **current entity-type names**; edit `attributes[]`.
- **Analysis summary:** free-text edit.

Validation runs live client-side for immediate feedback; the server is authoritative.

### 3.4 New endpoint

`PUT /api/graph/project/<project_id>/ontology`
- Body: `{ ontology: { entity_types, edge_types }, analysis_summary? }`.
- `require_account_access(project.account_id)` → **404** on mismatch.
- Runs server-side validation (§3.5). On hard-block failure → **400** `{ success:false, error, violations:[…] }`. On success → persists and returns the saved ontology plus any **warnings** (non-blocking).
- Rejected if status is `GRAPH_BUILDING` → **409**.

### 3.5 Validation rules

Implemented as a **pure module** (`backend/app/services/ontology_validator.py`) returning `{ errors:[…], warnings:[…] }`, used by both the endpoint and unit tests.

**Hard-block (errors):**
- entity or edge type name empty or duplicated;
- attribute name empty, duplicated within its type, or one of the reserved words `name`, `uuid`, `group_id`, `created_at`, `summary`;
- an edge `source` or `target` referencing a name not present in `entity_types`.

**Warn (non-blocking):**
- entity-type count ≠ 10;
- edge-type count outside 6–10;
- missing `Person` or `Organization` fallback entity type.

The client mirrors these rules; build is allowed with warnings present but blocked while any error exists.

---

## 4. Step 02 — Graph Curation

### 4.1 New `Neo4jStorage` primitives

All scoped to a `graph_id`, written in Cypher:

- `update_node(uuid, fields)` — `fields` ⊆ `{name, entity_type, attributes, summary}`. `entity_type` replaces the node's entity-type label; `attributes` is merged (provided keys overwrite). Returns the updated node.
- `delete_node(uuid)` — detaches and deletes the node and its incident relationships.
- `update_edge(edge_id, fields)` — `fields` ⊆ `{fact, fact_type}`.
- `delete_edge(edge_id)` — deletes one relationship.
- `merge_nodes(primary_uuid, duplicate_uuids[])` — re-points every relationship of each duplicate onto `primary`, unions attributes (primary wins on key conflict), collapses self-loops and duplicate parallel edges, deletes the duplicates. **Transactional**: a partial failure rolls back.

### 4.2 New endpoints (`graph.py`)

Each calls `require_graph_account_access(graph_id)` → **404** on mismatch, and returns **409** if the graph's project is `GRAPH_BUILDING`.

- `PATCH /api/graph/<graph_id>/node/<uuid>` `{name?, entity_type?, attributes?, summary?}`
- `DELETE /api/graph/<graph_id>/node/<uuid>`
- `PATCH /api/graph/<graph_id>/edge/<edge_id>` `{fact?, fact_type?}`
- `DELETE /api/graph/<graph_id>/edge/<edge_id>`
- `POST /api/graph/<graph_id>/merge` `{primary, duplicates:[…]}`

All return `{ success, data|error }`. Merge is atomic (§4.1).

### 4.3 UI — extend the existing detail panel

No new screen. In `Process.vue`'s left-pane detail panel:
- Selecting a node/edge shows an **Edit** toggle; in edit mode its fields become inputs. The node **entity_type** field is a **dropdown of the ontology's entity-type names** (plus the node's current value if it is off-ontology), keeping the graph aligned with Step 01.
- A **Delete** action on the selected node/edge (with confirm).
- **Merge**: choose a primary node, multi-select one or more duplicate nodes, confirm → merge.
- After any successful edit/delete/merge, the view refreshes from `/api/graph/data/<graph_id>`.

### 4.4 Rebuild-overwrites-edits hazard

Manual curation lives only in Neo4j. Re-running `/build` — including **Approve & Build** after editing the ontology when a graph already exists — regenerates the graph and **discards manual edits**. Before any such rebuild, the UI shows an explicit **confirm dialog** ("Rebuilding replaces the current graph and discards manual edits"). No silent loss.

---

## 5. Cross-cutting

- **Isolation:** ontology endpoint uses `require_account_access(project.account_id)`; all curation endpoints use `require_graph_account_access(graph_id)`; both 404 on mismatch.
- **Concurrency:** edits to a graph whose project is `GRAPH_BUILDING` are rejected (**409**) to avoid racing the build task.
- **Downstream consistency:** curation writes straight to Neo4j, so simulation steps that read the same graph see the changes with no extra plumbing.
- **Error contract:** `{success, error}` with `400` (validation), `404` (access/not-found), `409` (busy); merge rolls back on partial failure.
- **No new dependencies.**

---

## 6. Testing (TDD)

**Backend**
- `ontology_validator`: a unit test per hard-block rule and per soft-warn rule (errors vs warnings separated correctly).
- `PUT /project/<id>/ontology`: persists; cross-account → 404; rejects each breaker → 400; allows save with warnings; 409 while building.
- Storage primitives against a seeded test graph: `update_node` (incl. entity-type label change + attribute merge), `delete_node` (incident edges gone), `update_edge`, `delete_edge`, `merge_nodes` (edge re-pointing, attribute union, self/parallel-edge collapse, duplicates deleted).
- Curation endpoints: happy path + cross-account 404 + 409-while-building each.

**Frontend**
- `npm run build` clean; component checks where harnessed.
- Manual: generate → edit ontology (trigger one warning + one block) → Approve & Build → select & edit a node, delete an edge, merge two duplicates → trigger a rebuild and see the discard-confirm.

---

## 7. Implementation Phases (Step 01 before Step 02)

1. **`ontology_validator` module** — pure validation functions, fully unit-tested.
2. **`PUT /api/graph/project/<id>/ontology`** — persistence endpoint using #1 (account-scoped, 409 while building).
3. **Pause gate + `OntologyEditor.vue`** — stop auto-build; editable ontology form with live validation; Approve & Build.
4. **Neo4j curation primitives** — `update/delete_node`, `update/delete_edge`, `merge_nodes` (+ tests).
5. **Curation endpoints** — node/edge PATCH & DELETE, merge; guards, 409.
6. **Editable detail panel + delete + merge UI** + rebuild-discard confirm.
7. **i18n (EN/DE)** for all new strings.

---

## 8. Impact on existing code

- `backend/app/api/graph.py` — add ontology PUT endpoint + 5 curation endpoints.
- `backend/app/storage/neo4j_storage.py` — add 5 write primitives.
- `backend/app/services/ontology_validator.py` — new pure module.
- `frontend/src/views/Process.vue` — remove auto-build; mount `OntologyEditor`; editable detail panel; rebuild-discard confirm.
- `frontend/src/components/OntologyEditor.vue` — new.
- `frontend/src/api/graph.js` — new client methods (save ontology, node/edge edit/delete, merge).
- `locales/en.json`, `locales/de.json` — new strings.
