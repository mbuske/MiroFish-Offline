"""
The API-layer helper that resolves a simulation directory from an untrusted
URL/path parameter must validate and confine it (CVE-2026-7059), covering the
direct os.path.join sites that bypass SimulationManager.
"""
import pytest

from app.api.simulation import _resolve_simulation_dir


def test_rejects_traversal():
    with pytest.raises(ValueError):
        _resolve_simulation_dir("../../etc")


def test_rejects_encoded_slash_payload():
    with pytest.raises(ValueError):
        _resolve_simulation_dir("sim_../../x")


def test_accepts_valid_id():
    path = _resolve_simulation_dir("sim_abc123")
    assert path.endswith("sim_abc123")
