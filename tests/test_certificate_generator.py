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

"""Regression coverage for #16: certificate_generator.py and
password_generator.py had zero automated tests despite being the code that
produces the server's self-signed TLS certificate and its private-key
password on every fresh HTTPS-enabled deployment.
"""

import os

import pytest

from common.cert.certificate_generator import CertificateGenerator
from common.cert.password_generator import PasswordGenerator


class TestPasswordGenerator:
    def test_default_length_is_sixteen(self):
        gen = PasswordGenerator()
        assert len(gen.generate_password()) == 16

    def test_respects_custom_length(self):
        gen = PasswordGenerator()
        assert len(gen.generate_password(24)) == 24

    def test_raises_for_length_below_eight(self):
        gen = PasswordGenerator()
        with pytest.raises(ValueError, match="at least 8"):
            gen.generate_password(7)

    def test_contains_all_four_character_classes(self):
        """The generator seeds one character from each of digit/upper/lower/
        special into the first four (pre-shuffle) slots, so this must hold
        for every generated password regardless of RNG -- not just often."""
        gen = PasswordGenerator()
        for _ in range(50):
            password = gen.generate_password(16)
            assert any(c in PasswordGenerator.DIGITS for c in password)
            assert any(c in PasswordGenerator.UPPER for c in password)
            assert any(c in PasswordGenerator.LOWER for c in password)
            assert any(c in PasswordGenerator.SPECIAL for c in password)

    def test_passwords_are_not_all_identical(self):
        gen = PasswordGenerator()
        passwords = {gen.generate_password(16) for _ in range(20)}
        assert len(passwords) > 1


class TestCertificateGeneratorSelfSignedApi:
    def test_generates_cert_and_key_with_provided_password(self, tmp_path):
        cert_dir = str(tmp_path / "certs")
        gen = CertificateGenerator()
        assert gen.generate_self_signed_cert(cert_dir, "serverAuth", "S3cure!Pass") is True
        assert os.path.exists(os.path.join(cert_dir, "server_RSA.cer"))
        assert os.path.exists(os.path.join(cert_dir, "server_key_RSA.pem"))

    def test_returns_false_for_empty_password(self, tmp_path):
        cert_dir = str(tmp_path / "certs")
        gen = CertificateGenerator()
        assert gen.generate_self_signed_cert(cert_dir, "serverAuth", "") is False
        # cert_dir itself is created before the password is validated; no
        # cert/key files are written since generation aborts before that.
        assert not os.path.exists(os.path.join(cert_dir, "server_RSA.cer"))
        assert not os.path.exists(os.path.join(cert_dir, "server_key_RSA.pem"))

    def test_returns_false_without_overwriting_existing_certificates(self, tmp_path):
        cert_dir = str(tmp_path / "certs")
        gen = CertificateGenerator()
        assert gen.generate_self_signed_cert(cert_dir, "serverAuth", "S3cure!Pass") is True
        key_path = os.path.join(cert_dir, "server_key_RSA.pem")
        original_contents = open(key_path, "rb").read()

        assert gen.generate_self_signed_cert(cert_dir, "serverAuth", "AnotherPass1!") is False
        assert open(key_path, "rb").read() == original_contents

    def test_returns_false_for_unsupported_key_algorithm(self, tmp_path):
        gen = CertificateGenerator(key_algorithm="DSA")
        assert gen.generate_self_signed_cert(str(tmp_path / "certs"), "serverAuth", "S3cure!Pass") is False
