"""config.py — Config.from_env parsing and validation (§5.7)."""

from __future__ import annotations

import pytest

from arborist.config import Config, Profile, TlsPosture
from arborist.errors import ConfigError


class TestRequiredVars:
    def test_missing_required_vars_listed_together(self):
        with pytest.raises(ConfigError) as excinfo:
            Config.from_env({})
        msg = str(excinfo.value)
        assert "SCANOPY_BASE_URL" in msg
        assert "SCANOPY_API_KEY" in msg

    def test_missing_api_key_only(self, make_env):
        env = make_env()
        del env["SCANOPY_API_KEY"]
        with pytest.raises(ConfigError) as excinfo:
            Config.from_env(env)
        msg = str(excinfo.value)
        assert "SCANOPY_API_KEY" in msg
        assert "SCANOPY_BASE_URL" not in msg

    def test_base_url_scheme_enforced(self, make_env):
        with pytest.raises(ConfigError, match="http:// or https://"):
            Config.from_env(make_env(SCANOPY_BASE_URL="scanopy.lan:60072"))

    def test_base_url_trailing_slash_stripped(self, make_config):
        cfg = make_config(SCANOPY_BASE_URL="http://scanopy.test:60072/")
        assert cfg.base_url == "http://scanopy.test:60072"


class TestBooleanParsing:
    @pytest.mark.parametrize("raw", ["true", "TRUE", "1", "yes", "on"])
    def test_truthy(self, make_config, raw):
        assert make_config(SCANOPY_TLS_VERIFY=raw).tls_verify is True

    @pytest.mark.parametrize("raw", ["false", "FALSE", "0", "no", "off"])
    def test_falsy(self, make_config, raw):
        assert make_config(SCANOPY_TLS_VERIFY=raw).tls_verify is False

    def test_garbage_is_an_error_not_a_default(self, make_env):
        with pytest.raises(ConfigError, match="not a boolean"):
            Config.from_env(make_env(SCANOPY_TLS_VERIFY="banana"))


class TestProfile:
    def test_invalid_profile_rejected(self, make_env):
        with pytest.raises(ConfigError, match="ARBORIST_PROFILE"):
            Config.from_env(make_env(ARBORIST_PROFILE="root"))

    def test_readwrite_accepted_case_insensitively(self, make_config):
        assert make_config(ARBORIST_PROFILE="ReadWrite").profile is Profile.READWRITE

    def test_consolidation_requires_readwrite(self, make_env):
        with pytest.raises(ConfigError, match="readwrite"):
            Config.from_env(make_env(ARBORIST_ENABLE_CONSOLIDATION="true"))

    def test_consolidation_with_readwrite_ok(self, make_config):
        cfg = make_config(
            ARBORIST_PROFILE="readwrite", ARBORIST_ENABLE_CONSOLIDATION="true"
        )
        assert cfg.profile is Profile.READWRITE
        assert cfg.enable_consolidation is True


class TestTls:
    def test_ca_path_with_verify_false_is_contradiction(self, make_env, tmp_path):
        ca = tmp_path / "ca.pem"
        ca.write_text("dummy")
        with pytest.raises(ConfigError, match="pick one"):
            Config.from_env(
                make_env(SCANOPY_TLS_CA_PATH=str(ca), SCANOPY_TLS_VERIFY="false")
            )

    def test_ca_path_missing_file(self, make_env, tmp_path):
        with pytest.raises(ConfigError, match="missing file"):
            Config.from_env(make_env(SCANOPY_TLS_CA_PATH=str(tmp_path / "nope.pem")))

    def test_ca_path_with_verify_true_ok(self, make_config, tmp_path):
        ca = tmp_path / "ca.pem"
        ca.write_text("dummy")
        cfg = make_config(SCANOPY_TLS_CA_PATH=str(ca))
        assert cfg.tls_ca_path == str(ca)
        assert cfg.tls_verify is True

    def test_invalid_posture_rejected(self, make_env):
        with pytest.raises(ConfigError, match="ARBORIST_TLS_POSTURE"):
            Config.from_env(make_env(ARBORIST_TLS_POSTURE="yolo"))

    def test_cert_key_paths_must_exist(self, make_env, tmp_path):
        with pytest.raises(ConfigError, match="ARBORIST_TLS_CERT_PATH"):
            Config.from_env(make_env(ARBORIST_TLS_CERT_PATH=str(tmp_path / "c.pem")))


class TestDefaults:
    def test_defaults(self, make_config):
        cfg = make_config()
        assert cfg.profile is Profile.READONLY
        assert cfg.tls_verify is True
        assert cfg.tls_ca_path is None
        assert cfg.enable_consolidation is False
        assert cfg.auth_token is None
        assert cfg.allowed_hosts == []
        assert cfg.tls_posture is TlsPosture.LOOPBACK
        assert cfg.tls_cert_path is None
        assert cfg.tls_key_path is None
        assert cfg.allow_untested_version is False
        assert cfg.network_id is None

    def test_allowed_hosts_parsed_and_trimmed(self, make_config):
        cfg = make_config(ARBORIST_ALLOWED_HOSTS=" arborist.lan:60074 , other.lan ,, ")
        assert cfg.allowed_hosts == ["arborist.lan:60074", "other.lan"]

    def test_network_id_passthrough(self, make_config):
        cfg = make_config(SCANOPY_NETWORK_ID="d0b1e0aa-0000-0000-0000-000000000001")
        assert cfg.network_id == "d0b1e0aa-0000-0000-0000-000000000001"
