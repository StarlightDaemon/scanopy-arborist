"""redact.py — output hygiene (§5.8)."""

from __future__ import annotations

import pytest

from arborist.redact import REDACTED, is_sensitive_key, redact


class TestIsSensitiveKey:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "PASSWORD",
            "passphrase",
            "secret",
            "client_secret",
            "token",
            "auth_token",
            "api_key",
            "api-key",
            "apiKey",
            "apikey",
            "private_key",
            "credential",
            "credential_assignments",
            "session",
            "session_id",
            "authorization",
            "key",  # exact bare "key" — Scanopy uses it for API-key material
        ],
    )
    def test_sensitive(self, key):
        assert is_sensitive_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "name",
            "hostname",
            "ip_address",
            "mac_address",
            "network_id",
            "description",
            "monkey",  # contains "key" but only the exact key "key" is anchored
            "keyboard",
        ],
    )
    def test_not_sensitive(self, key):
        assert is_sensitive_key(key) is False


class TestRedact:
    def test_nested_dicts_and_lists(self):
        payload = {
            "hosts": [
                {
                    "name": "gateway",
                    "password": "hunter2",
                    "services": [{"name": "ssh", "token": "abc"}],
                },
            ],
            "meta": {"api_key": "scp_u_xyz", "count": 1},
        }
        out = redact(payload)
        assert out["hosts"][0]["password"] == REDACTED
        assert out["hosts"][0]["services"][0]["token"] == REDACTED
        assert out["meta"]["api_key"] == REDACTED
        # Non-sensitive values untouched at every depth.
        assert out["hosts"][0]["name"] == "gateway"
        assert out["hosts"][0]["services"][0]["name"] == "ssh"
        assert out["meta"]["count"] == 1

    @pytest.mark.parametrize(
        "key", ["password", "secret", "token", "api_key", "apiKey", "session"]
    )
    def test_sensitive_scalar_masked(self, key):
        assert redact({key: "value"}) == {key: REDACTED}

    def test_exact_key_key_masked(self):
        out = redact({"key": "scp_u_material", "monkey": "bananas"})
        assert out["key"] == REDACTED
        assert out["monkey"] == "bananas"

    def test_containers_under_sensitive_keys_replaced_wholesale(self):
        payload = {
            "credential_assignments": [{"id": "c1", "credential_id": "x"}],
            "session": {"cookie": "abc"},
        }
        out = redact(payload)
        # The whole container is masked, not its individual leaves.
        assert out["credential_assignments"] == REDACTED
        assert out["session"] == REDACTED

    def test_top_level_list(self):
        out = redact([{"password": "a"}, {"name": "b"}])
        assert out == [{"password": REDACTED}, {"name": "b"}]

    def test_scalars_and_none_pass_through(self):
        assert redact("plain") == "plain"
        assert redact(42) == 42
        assert redact(None) is None

    def test_original_not_mutated(self):
        payload = {"outer": {"password": "hunter2"}}
        redact(payload)
        assert payload["outer"]["password"] == "hunter2"
