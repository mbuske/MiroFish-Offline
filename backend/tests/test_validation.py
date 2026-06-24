"""
Tests for input-validation helpers that close path-traversal / IPC-injection
vectors (CVE-2026-7059 and the unvalidated simulation_id IPC issue).
"""
import os

import pytest

from app.utils.validation import (
    validate_simulation_id,
    validate_platform,
    safe_join,
)


class TestValidateSimulationId:
    def test_accepts_normal_id(self):
        assert validate_simulation_id("sim_abc123") == "sim_abc123"

    def test_accepts_hyphen_and_underscore(self):
        assert validate_simulation_id("sim_ab-cd_12") == "sim_ab-cd_12"

    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError):
            validate_simulation_id("../../etc/passwd")

    def test_rejects_slash(self):
        with pytest.raises(ValueError):
            validate_simulation_id("sim_a/b")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            validate_simulation_id("")

    def test_rejects_wrong_prefix(self):
        with pytest.raises(ValueError):
            validate_simulation_id("evil_123")


class TestValidatePlatform:
    def test_accepts_reddit(self):
        assert validate_platform("reddit") == "reddit"

    def test_accepts_twitter(self):
        assert validate_platform("twitter") == "twitter"

    def test_rejects_traversal(self):
        with pytest.raises(ValueError):
            validate_platform("../../secret")

    def test_rejects_unknown(self):
        with pytest.raises(ValueError):
            validate_platform("facebook")


class TestSafeJoin:
    def test_joins_inside_base(self, tmp_path):
        base = str(tmp_path)
        result = safe_join(base, "sim_1", "state.json")
        assert result == os.path.join(base, "sim_1", "state.json")

    def test_blocks_escape_via_dotdot(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError):
            safe_join(base, "..", "..", "etc", "passwd")

    def test_blocks_absolute_escape(self, tmp_path):
        base = str(tmp_path)
        with pytest.raises(ValueError):
            safe_join(base, "/etc/passwd")
