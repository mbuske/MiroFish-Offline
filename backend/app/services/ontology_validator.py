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
