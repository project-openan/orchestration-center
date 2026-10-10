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

"""Regression coverage for #10: etc/conf/server.conf shipped verify_client=false,
silently overriding ConfObj's own secure default (ssl.CERT_REQUIRED, see
TestConfObj.test_as_object_verify_client_default in test_cert_validator.py).
With enable_https=true and no other reasoning to override it, the external
API (/api/v1/*) ended up with no authentication at all -- auth_middleware
only guards the internal API by design, and mTLS was the only thing meant
to cover the external one.

This test reads the public image configuration template, not a fixture, so it fails the
moment that regression is reintroduced -- by anyone, including a future
docs/config edit that doesn't touch this test file at all.
"""

import os

import ssl

from common.util.conf_obj import ConfObj

_SERVER_CONF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "etc", "conf", "server.conf.example"
)


def _parse_conf_file(path):
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


class TestShippedServerConfDefaults:
    def test_verify_client_is_not_shipped_as_false(self):
        conf = _parse_conf_file(_SERVER_CONF_PATH)
        assert conf.get("verify_client", "").lower() != "false", (
            "etc/conf/server.conf ships verify_client=false, which overrides "
            "ConfObj's secure ssl.CERT_REQUIRED default and leaves the "
            "external API (/api/v1/*) with no authentication at all when "
            "enable_https=true (see #10)."
        )

    def test_shipped_config_resolves_to_cert_required(self):
        conf = _parse_conf_file(_SERVER_CONF_PATH)
        obj = ConfObj.as_object(conf)
        assert obj.verify_client == ssl.CERT_REQUIRED
