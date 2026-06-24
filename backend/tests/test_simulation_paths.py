"""
Tests that SimulationManager rejects unsafe simulation_id / platform values,
closing the path-traversal (CVE-2026-7059) and IPC-injection vectors at the
service chokepoint (`_get_simulation_dir` is the base for the IPC dirs too).
"""
import pytest

from app.services.simulation_manager import SimulationManager


@pytest.fixture
def manager(tmp_path):
    m = SimulationManager()
    # Point the data dir at a writable tmp location for hermetic tests.
    m.SIMULATION_DATA_DIR = str(tmp_path)
    return m


class TestSimulationDirGuard:
    def test_rejects_traversal_id(self, manager):
        with pytest.raises(ValueError):
            manager._get_simulation_dir("../../etc")

    def test_rejects_slash_id(self, manager):
        with pytest.raises(ValueError):
            manager._get_simulation_dir("sim_a/../b")

    def test_accepts_valid_id(self, manager):
        d = manager._get_simulation_dir("sim_valid123")
        assert d.endswith("sim_valid123")


class TestGetProfilesPlatformGuard:
    def test_rejects_bad_platform(self, manager):
        # Must reject before touching the filesystem, regardless of sim state.
        with pytest.raises(ValueError):
            manager.get_profiles("sim_x", platform="../../secret")
