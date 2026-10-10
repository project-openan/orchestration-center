# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Coverage for the fail-closed startup check (docs/design/security-design.md 6.3).

The unsafe cell is ``enable_https=false`` + no credential + a non-loopback bind: no
mTLS, no application-layer guard on ``/api/v1/*``, and the port reachable from off
this host. The image defaults (Dockerfile: ``ORCH_IP=0.0.0.0``,
``ORCH_ENABLE_HTTPS=false``, empty ``access_password``) land in exactly that cell, so
these tests pin the refusal and the two documented ways out of it.
"""

import os
from unittest.mock import Mock, patch

import pytest

from orchestrate.server.security_preflight import (
    ADMIN_INITIAL_PASSWORD_ENV,
    SecurityPreflightError,
    credential_configured,
    dev_insecure_mode_enabled,
    is_loopback_bind,
    security_preflight,
)


@pytest.fixture(autouse=True)
def _no_ambient_bootstrap_credential(monkeypatch):
    """The check reads the process environment; keep the ambient one out of it."""
    monkeypatch.delenv(ADMIN_INITIAL_PASSWORD_ENV, raising=False)
    # HTTP needs an independent machine credential, not just the UI password.
    monkeypatch.setenv("ORCH_API_TOKEN", "test-only-machine-token-at-least-32-bytes")


def _conf(**overrides):
    conf = {
        "enable_https": "false",
        "ip": "127.0.0.1",
        "persistence_mode": "file",
        "access_password": "",
        "security.dev_insecure_mode": "false",
    }
    conf.update(overrides)
    return conf


class TestIsLoopbackBind:
    @pytest.mark.parametrize("address", ["127.0.0.1", "127.0.0.10", "localhost", "LOCALHOST", "::1"])
    def test_loopback(self, address):
        assert is_loopback_bind(address) is True

    @pytest.mark.parametrize("address", ["0.0.0.0", "::", "192.168.1.10", "example.com", "", "  "])
    def test_exposed(self, address):
        """A wildcard bind is the case the check exists for, not a loopback one."""
        assert is_loopback_bind(address) is False


class TestCredentialConfigured:
    def test_empty_access_password_is_not_a_credential(self):
        assert credential_configured(_conf(access_password="")) is False

    def test_access_password_counts(self):
        assert credential_configured(_conf(access_password="deadbeef")) is True

    def test_named_initial_password_file_counts(self, tmp_path):
        path = tmp_path / "admin_pw"
        path.write_text("secret")
        assert credential_configured(_conf(persistence_mode="postgresql", admin_initial_password_file=str(path))) is True

    def test_missing_initial_password_file_does_not_count(self, tmp_path):
        assert credential_configured(_conf(admin_initial_password_file=str(tmp_path / "absent"))) is False

    def test_environment_bootstrap_counts(self, monkeypatch):
        monkeypatch.setenv(ADMIN_INITIAL_PASSWORD_ENV, "secret")
        assert credential_configured(_conf(persistence_mode="postgresql")) is True
        assert credential_configured(_conf()) is False

    def test_database_user_counts(self, monkeypatch):
        conf = _conf(persistence_mode="postgresql")
        with patch("database.utils.user_store.has_any_user", return_value=True) as has_any:
            assert credential_configured(conf) is True
        has_any.assert_called_once()

    def test_unreachable_user_store_does_not_count(self, monkeypatch):
        """Fail closed: "cannot tell" must not read as "a credential exists"."""
        conf = _conf(persistence_mode="postgresql")
        with patch("database.utils.user_store.has_any_user", side_effect=RuntimeError("db down")):
            assert credential_configured(conf) is False


class TestPreflightMatrix:
    """One case per row of the section 6.3 table, plus the rows' neighbours."""

    def test_https_enabled_starts_anywhere(self):
        result = security_preflight(_conf(enable_https="true", ip="0.0.0.0"))
        assert result.https_enabled is True
        assert result.warnings == ()

    def test_https_enabled_without_credential_still_starts(self):
        result = security_preflight(_conf(enable_https="true", ip="0.0.0.0"))
        assert result.credential_configured is False

    def test_plaintext_with_credential_starts_with_a_warning(self):
        result = security_preflight(_conf(access_password="deadbeef", ip="0.0.0.0"))
        assert result.credential_configured is True
        assert len(result.warnings) == 1
        assert "plaintext" in result.warnings[0]

    def test_credentialless_loopback_requires_the_dev_flag(self):
        with pytest.raises(SecurityPreflightError):
            security_preflight(_conf(ip="127.0.0.1"))

    def test_dev_flag_permits_the_credentialless_loopback_bind(self):
        result = security_preflight(_conf(ip="127.0.0.1", **{"security.dev_insecure_mode": "true"}))
        assert result.dev_insecure_mode is True
        assert len(result.warnings) == 1
        assert "dev_insecure_mode" in result.warnings[0]

    def test_dev_flag_does_not_permit_a_non_loopback_bind(self):
        with pytest.raises(SecurityPreflightError) as exc:
            security_preflight(_conf(ip="0.0.0.0", **{"security.dev_insecure_mode": "true"}))
        assert "does not lift this" in str(exc.value)

    def test_unsafe_cell_refuses_and_names_both_ways_out(self):
        with pytest.raises(SecurityPreflightError) as exc:
            security_preflight(_conf(ip="0.0.0.0"))
        message = str(exc.value)
        assert "Refusing to start" in message
        assert "access_password" in message
        assert "ip=127.0.0.1" in message

    @pytest.mark.parametrize("ip", ["0.0.0.0", "::", "", "192.168.1.10", "orchestration-center"])
    def test_every_non_loopback_bind_refuses_without_a_credential(self, ip):
        with pytest.raises(SecurityPreflightError):
            security_preflight(_conf(ip=ip))

    @pytest.mark.parametrize("ip", ["0.0.0.0", "::", "", "192.168.1.10", "orchestration-center"])
    def test_a_credential_makes_every_bind_startable(self, ip):
        result = security_preflight(_conf(ip=ip, access_password="deadbeef"))
        assert result.credential_configured is True


class TestDevInsecureModeFlag:
    def test_default_is_off(self):
        assert dev_insecure_mode_enabled({}) is False

    @pytest.mark.parametrize("value", ["true", "True", " true "])
    def test_truthy_spellings(self, value):
        assert dev_insecure_mode_enabled({"security.dev_insecure_mode": value}) is True

    @pytest.mark.parametrize("value", ["false", "0", "yes", ""])
    def test_everything_else_is_off(self, value):
        assert dev_insecure_mode_enabled({"security.dev_insecure_mode": value}) is False


class TestShippedServerConf:
    """Reads the shipped file, not a fixture: the default must stay fail-closed."""

    _PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "etc", "conf", "server.conf.example"
    )

    @staticmethod
    def _parse(path):
        conf = {}
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                conf[key.strip()] = value.strip()
        return conf

    def test_dev_insecure_mode_ships_off(self):
        conf = self._parse(self._PATH)
        assert conf.get("security.dev_insecure_mode", "").lower() == "false"

    def test_shipped_conf_is_refused_on_a_non_loopback_bind(self):
        """The shipped file configures no credential, so exposing it must fail."""
        conf = {**self._parse(self._PATH), "persistence_mode": "file", "ip": "0.0.0.0"}
        with pytest.raises(SecurityPreflightError):
            security_preflight(conf)

    def test_shipped_conf_needs_the_dev_flag_on_its_own_loopback_default(self):
        """Even ip=127.0.0.1 as shipped starts only once the operator opts in."""
        conf = {**self._parse(self._PATH), "persistence_mode": "file"}
        with pytest.raises(SecurityPreflightError):
            security_preflight(conf)


class TestMainUsesThePreflight:
    def test_main_refuses_to_bind_in_the_unsafe_cell(self, monkeypatch, capsys):
        from orchestrate import start

        conf = _conf(ip="0.0.0.0")
        monkeypatch.setattr(start, "get_conf", lambda: conf)
        run = Mock(side_effect=AssertionError("the server must not bind"))
        monkeypatch.setattr(start.uvicorn, "run", run)

        with pytest.raises(SystemExit) as exc:
            start.main()

        assert "Refusing to start" in str(exc.value)
        run.assert_not_called()

    def test_main_starts_with_the_dev_flag_on_loopback(self, monkeypatch):
        from orchestrate import start

        conf = _conf(ip="127.0.0.1", **{"security.dev_insecure_mode": "true"})
        monkeypatch.setattr(start, "get_conf", lambda: conf)
        run = Mock()
        audit = Mock()
        monkeypatch.setattr(start.uvicorn, "run", run)
        monkeypatch.setattr(start.audit_logger, "audit", audit)

        start.main()

        run.assert_called_once()
        audit.assert_called_once()
        assert audit.call_args.args[0]["details"]["dev_insecure_mode"] is True


class TestHealthEndpoint:
    def test_health_is_public_and_echoes_the_dev_flag(self, monkeypatch):
        from fastapi.testclient import TestClient

        from orchestrate.server import frontend_support_server as server

        monkeypatch.setattr(
            server, "get_conf", lambda: {"security.dev_insecure_mode": "true"}
        )
        client = TestClient(server.app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "dev_insecure_mode": True}

    def test_health_reports_the_flag_off_by_default(self, monkeypatch):
        from fastapi.testclient import TestClient

        from orchestrate.server import frontend_support_server as server

        monkeypatch.setattr(server, "get_conf", lambda: {})
        client = TestClient(server.app)
        assert client.get("/health").json() == {"status": "ok", "dev_insecure_mode": False}
