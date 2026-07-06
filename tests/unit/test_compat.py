"""compat.py — the §5.4 version gate."""

from __future__ import annotations

import pytest

from arborist.compat import (
    MAX_EXCLUSIVE,
    MIN_SUPPORTED,
    SUPPORTED_API_VERSION,
    check_compat,
    parse_version,
    supported_range,
)
from arborist.errors import VersionCompatError


class TestParseVersion:
    def test_plain(self):
        assert parse_version("0.17.3") == (0, 17, 3)

    def test_v_prefix(self):
        assert parse_version("v0.17.3") == (0, 17, 3)

    def test_prerelease_suffix(self):
        assert parse_version("0.17.3-rc1") == (0, 17, 3)

    def test_unparseable_raises(self):
        with pytest.raises(VersionCompatError, match="refusing to guess"):
            parse_version("weekly-build-7")


class TestCheckCompat:
    @pytest.mark.parametrize("version", ["0.17.2", "0.17.3", "v0.17.3", "0.17.3-rc1"])
    def test_inside_range_ok(self, version):
        result = check_compat(version, SUPPORTED_API_VERSION)
        assert result.ok
        assert result.reason == "supported"
        assert result.server_version == version

    def test_below_min_refused(self):
        result = check_compat("0.17.1", SUPPORTED_API_VERSION)
        assert not result.ok
        assert "older" in result.reason
        assert "0.17.2" in result.reason  # names the oldest verified version

    @pytest.mark.parametrize("version", ["0.18.0", "0.19.5", "1.0.0"])
    def test_at_or_above_max_exclusive_refused(self, version):
        result = check_compat(version, SUPPORTED_API_VERSION)
        assert not result.ok
        assert "newer" in result.reason
        # The refusal must point at the override escape hatch.
        assert "ARBORIST_ALLOW_UNTESTED_VERSION" in result.reason

    def test_unparseable_version_refused_not_raised(self):
        result = check_compat("garbage", SUPPORTED_API_VERSION)
        assert not result.ok
        assert "Could not parse" in result.reason

    def test_api_version_mismatch_refused(self):
        result = check_compat("0.17.3", 2)
        assert not result.ok
        assert "api_version 2" in result.reason
        assert str(SUPPORTED_API_VERSION) in result.reason

    def test_api_version_none_is_not_checked(self):
        # Older servers may not report api_version; the semver gate still applies.
        assert check_compat("0.17.3", None).ok
        assert not check_compat("0.18.0", None).ok

    def test_result_carries_inputs(self):
        result = check_compat("0.17.3", 1)
        assert result.server_version == "0.17.3"
        assert result.api_version == 1


def test_supported_range_string():
    rng = supported_range()
    assert ".".join(str(p) for p in MIN_SUPPORTED) in rng
    assert ".".join(str(p) for p in MAX_EXCLUSIVE) in rng
    assert rng.startswith(">=")
    assert ",<" in rng
