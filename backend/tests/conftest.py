"""Shared pytest fixtures."""
import pytest


@pytest.fixture(autouse=True)
def _reset_auth_db():
    """Dispose and reset the module-level auth-store engine between tests."""
    yield
    import app.auth.db as authdb
    if authdb._engine is not None:
        authdb._engine.dispose()
        authdb._engine = None
