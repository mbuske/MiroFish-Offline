"""Ownership guard for graph_id-keyed endpoints."""
from flask import current_app
from .accounts import require_account_access


def require_graph_account_access(graph_id):
    """Raise PermissionError if the current user's account may not access this graph."""
    storage = current_app.extensions.get('neo4j_storage')
    account = storage.get_graph_account(graph_id) if storage else None
    require_account_access(account)
