"""Shared fixtures for the unit suite. No network access anywhere in here."""

from __future__ import annotations

import pytest

from arborist.config import Config

BASE_ENV: dict[str, str] = {
    "SCANOPY_BASE_URL": "http://scanopy.test:60072",
    "SCANOPY_API_KEY": "scp_u_unit_test_key",
}


@pytest.fixture
def base_env() -> dict[str, str]:
    return dict(BASE_ENV)


@pytest.fixture
def make_env():
    """Build a fake env dict on top of the minimal valid base."""

    def _make(**overrides: str) -> dict[str, str]:
        env = dict(BASE_ENV)
        env.update(overrides)
        return env

    return _make


@pytest.fixture
def make_config(make_env):
    """Build a Config through the real from_env parser."""

    def _make(**overrides: str) -> Config:
        return Config.from_env(make_env(**overrides))

    return _make
