"""
list_simulations() iterates directory names from disk. After tightening
simulation_id validation it must skip entries with unexpected names instead of
raising, so a stray directory cannot break listing.
"""
import os

import pytest

from app.services.simulation_manager import SimulationManager


@pytest.fixture
def manager(tmp_path):
    m = SimulationManager()
    m.SIMULATION_DATA_DIR = str(tmp_path)
    return m


def test_skips_invalid_named_dir_without_raising(manager, tmp_path):
    # A stray, non-conforming directory must not crash listing.
    os.makedirs(os.path.join(tmp_path, "..junk"), exist_ok=True)
    os.makedirs(os.path.join(tmp_path, "random_dir"), exist_ok=True)
    result = manager.list_simulations()
    assert result == []
