"""config.py — validate_http_transport, the §5.5 hardening matrix."""

from __future__ import annotations

import pytest

from arborist.config import is_loopback_host
from arborist.errors import TransportSecurityError

TOKEN = "unit-test-token-0123456789"  # >= 16 chars


class TestIsLoopbackHost:
    @pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.53"])
    def test_loopback(self, host):
        assert is_loopback_host(host) is True

    @pytest.mark.parametrize("host", ["0.0.0.0", "arborist.lan", "192.168.1.5", "::"])
    def test_not_loopback(self, host):
        assert is_loopback_host(host) is False


class TestValidateHttpTransport:
    def test_loopback_with_token_ok(self, make_config):
        cfg = make_config(ARBORIST_AUTH_TOKEN=TOKEN)
        cfg.validate_http_transport("127.0.0.1", 60074)  # must not raise

    def test_loopback_without_token_refused(self, make_config):
        cfg = make_config()
        with pytest.raises(TransportSecurityError, match="ARBORIST_AUTH_TOKEN"):
            cfg.validate_http_transport("127.0.0.1", 60074)

    def test_short_token_refused(self, make_config):
        cfg = make_config(ARBORIST_AUTH_TOKEN="short")
        with pytest.raises(TransportSecurityError, match="at least 16"):
            cfg.validate_http_transport("127.0.0.1", 60074)

    def test_non_loopback_with_loopback_posture_refused(self, make_config):
        cfg = make_config(
            ARBORIST_AUTH_TOKEN=TOKEN,
            ARBORIST_ALLOWED_HOSTS="arborist.lan:60074",
        )
        with pytest.raises(TransportSecurityError, match="ARBORIST_TLS_POSTURE"):
            cfg.validate_http_transport("0.0.0.0", 60074)

    def test_non_loopback_terminated_upstream_full_kit_ok(self, make_config):
        cfg = make_config(
            ARBORIST_AUTH_TOKEN=TOKEN,
            ARBORIST_TLS_POSTURE="terminated-upstream",
            ARBORIST_ALLOWED_HOSTS="arborist.lan:60074",
        )
        cfg.validate_http_transport("0.0.0.0", 60074)  # must not raise

    def test_non_loopback_without_allowed_hosts_refused(self, make_config):
        cfg = make_config(
            ARBORIST_AUTH_TOKEN=TOKEN,
            ARBORIST_TLS_POSTURE="terminated-upstream",
        )
        with pytest.raises(TransportSecurityError, match="ARBORIST_ALLOWED_HOSTS"):
            cfg.validate_http_transport("0.0.0.0", 60074)

    def test_direct_posture_without_cert_key_refused(self, make_config):
        cfg = make_config(ARBORIST_AUTH_TOKEN=TOKEN, ARBORIST_TLS_POSTURE="direct")
        with pytest.raises(TransportSecurityError, match="ARBORIST_TLS_CERT_PATH"):
            cfg.validate_http_transport("127.0.0.1", 60074)

    def test_direct_posture_with_cert_and_key_ok(self, make_config, tmp_path):
        cert = tmp_path / "cert.pem"
        key = tmp_path / "key.pem"
        cert.write_text("dummy")
        key.write_text("dummy")
        cfg = make_config(
            ARBORIST_AUTH_TOKEN=TOKEN,
            ARBORIST_TLS_POSTURE="direct",
            ARBORIST_TLS_CERT_PATH=str(cert),
            ARBORIST_TLS_KEY_PATH=str(key),
            ARBORIST_ALLOWED_HOSTS="arborist.lan:60074",
        )
        cfg.validate_http_transport("0.0.0.0", 60074)  # must not raise

    def test_all_violations_listed_together(self, make_config):
        # No token, non-loopback, default posture, no allowed hosts:
        # every problem must appear in one error.
        cfg = make_config()
        with pytest.raises(TransportSecurityError) as excinfo:
            cfg.validate_http_transport("0.0.0.0", 60074)
        msg = str(excinfo.value)
        assert "ARBORIST_AUTH_TOKEN" in msg
        assert "ARBORIST_TLS_POSTURE" in msg
        assert "ARBORIST_ALLOWED_HOSTS" in msg
