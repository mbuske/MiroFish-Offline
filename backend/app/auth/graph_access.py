"""Ownership guard for graph_id-keyed endpoints."""
from flask import current_app
from .ownership import require_owner_or_admin


def require_graph_owner_or_admin(graph_id):
    """Raise PermissionError if the current user may not access this graph."""
    storage = current_app.extensions.get('neo4j_storage')
    owner = storage.get_graph_owner(graph_id) if storage else None
    require_owner_or_admin(owner)
