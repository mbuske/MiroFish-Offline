"""
SimulationRunner must confine the run-state / IPC directory it derives from an
untrusted simulation_id, closing the IPC command-injection vector (file-based
IPC dirs live under this path).
"""
import pytest

from app.services.simulation_runner import SimulationRunner


def test_rejects_traversal_id():
    with pytest.raises(ValueError):
        SimulationRunner._sim_state_dir("../../etc")


def test_rejects_embedded_traversal():
    with pytest.raises(ValueError):
        SimulationRunner._sim_state_dir("sim_../../x")


def test_accepts_valid_id():
    path = SimulationRunner._sim_state_dir("sim_ok123")
    assert path.endswith("sim_ok123")
