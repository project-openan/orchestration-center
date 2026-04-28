# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

import os.path
import re
from abc import ABC, abstractmethod
import datetime
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa, ec

from common.cert import cert_parse
from common.cert.x509_obj import X509Obj
from common.util.cipher_util import DEFAULT_ENCODING
from common.util.conf_obj import ConfObj
from common.util.conf_util import load_cert_password
from common.util.constant_param import CONFIG_FILE_PATH
from common.util.validation_result import ValidationResult


class PathValidator:
    def __init__(self, cert_path: str, suffix: str, is_required=True, conf_tip=""):
        self.cert_path = cert_path
        self.suffix = suffix.lower()
        self.is_required = is_required
        new_conf_tip = f'"{conf_tip}"' if conf_tip is not None and conf_tip != "" else ''
        self.conf_tip = f"Please check {new_conf_tip} config in \"etc/conf/server.conf\" file and try again."

    def is_support_format(self, file_extension: str) -> bool:
        if self.suffix == "":
            return True
        return self.suffix == file_extension.lower()

    def validate(self) -> ValidationResult:
        if self.cert_path is None or self.cert_path == "":
            if not self.is_required:
                return ValidationResult(True, "Not config!")
            return ValidationResult(False, f"Cert file path is empty! {self.conf_tip}")

        cert_path_obj = Path(self.cert_path)
        if not cert_path_obj.exists():
            return ValidationResult(False, f"Cert file does not exist! {self.cert_path}. {self.conf_tip}")
        file_extension = cert_path_obj.suffix.lower()
        if not self.is_support_format(file_extension):
            return ValidationResult(False, f"Cert file extension is not support! {self.conf_tip}")
        return ValidationResult(True, "")


class AbstractValidatorLink(ABC):
    def __init__(self, conf_obj: ConfObj):
        self.conf_obj = conf_obj
        self.link = self.build_link()

    @abstractmethod
    def build_link(self):
        pass

    def validate(self) -> ValidationResult:
        for link in self.link:
            result = link.validate()
            if not result.is_valid:
                return result
        return ValidationResult(True, "")


class PathValidatorLink(AbstractValidatorLink):

    def build_link(self):
        conf_obj = self.conf_obj
        return [
            PathValidator(conf_obj.ssl_certfile, suffix=".cer", is_required=True, conf_tip="ssl_certfile"),
            PathValidator(conf_obj.ssl_keyfile, suffix=".pem", is_required=True, conf_tip="ssl_keyfile"),
            PathValidator(conf_obj.ssl_keyfile_password, suffix=".cer", is_required=True,
                          conf_tip="ssl_keyfile_password"),
            PathValidator(conf_obj.ssl_ca_certs, suffix=".cer", is_required=True, conf_tip="ssl_ca_certs"),
            PathValidator(conf_obj.ssl_crl_file, suffix=".cer", is_required=True, conf_tip="ssl_crl_file"),
        ]


class CommonContentValidator:
    def __init__(self, cert_path: str, conf_tip=""):
        self.cert_path = cert_path
        new_conf_tip = f'"{conf_tip}"' if conf_tip is not None and conf_tip != "" else ''
        self.conf_tip = f"Please check {new_conf_tip} config in \"etc/conf/server.conf\" file and try again."

    @staticmethod
    def validate_public_key_length(public_key) -> bool:
        if isinstance(public_key, rsa.RSAPublicKey):
            return public_key.key_size >= 3072
        if isinstance(public_key, ec.EllipticCurvePublicKey):
            return public_key.key_size >= 256
        return False

    @staticmethod
    def validate_private_key_length(private_key) -> bool:
        if isinstance(private_key, rsa.RSAPublicKey):
            return private_key.key_size >= 3072
        if isinstance(private_key, ec.EllipticCurvePublicKey):
            return private_key.key_size >= 256
        return False

    @staticmethod
    def validate_certificate_validity(x509_obj: X509Obj) -> bool:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        for cer_obj in x509_obj.cert_list:
            try:
                valid_from = datetime.datetime.fromisoformat(cer_obj.valid_from.replace('Z', '+00:00'))
                valid_to = datetime.datetime.fromisoformat(cer_obj.valid_to.replace('Z', '+00:00'))
                if current_time < valid_from or current_time > valid_to:
                    return False
            except (ValueError, TypeError):
                return False
        return True

    def validate(self) -> ValidationResult:
        pass


class CerContentValidator(CommonContentValidator):

    def validate(self) -> ValidationResult:
        try:
            x509_obj = cert_parse.parse_cer_certificate(self.cert_path)
            if len(x509_obj.cert_list) == 0:
                return ValidationResult(False, f"No certificate found! {self.conf_tip}")
            for cert_obj in x509_obj.cert_list:
                if cert_obj.version != x509.Version.v3:
                    return ValidationResult(False, f"Certificate format is not X.509v3! {self.conf_tip}")
                if not self.validate_public_key_length(cert_obj.public_key):
                    return ValidationResult(
                        False,
                        f"Certificate key algorithm or length does not meet requirements. {self.conf_tip}")
            if not self.validate_certificate_validity(x509_obj):
                return ValidationResult(False, f"Certificate is not valid at current time. {self.conf_tip}")

            return ValidationResult(True, f"CER certificate validation passed! {self.conf_tip}")
        except Exception as e:
            return ValidationResult(False, f"{e} {self.conf_tip}")


class PrivateKeyValidator(CommonContentValidator):
    digit_pattern = re.compile(r"[0-9]")
    upper_pattern = re.compile(r"[A-Z]")
    lower_pattern = re.compile(r"[a-z]")
    special_pattern = re.compile(r'[`~!@#$%^&*()_=+|\[\{\}\];:\'",<.>/?]')

    patterns = [digit_pattern, upper_pattern, lower_pattern, special_pattern]

    min_length = 8

    def __init__(self, cert_path: str, password_bytes: bytes = None, server_path="", conf_tip=""):
        super().__init__(cert_path=cert_path, conf_tip=conf_tip)
        self.server_path = server_path
        self.password_bytes = password_bytes

    def password_verify(self, plaintext: str) -> bool:
        if len(plaintext) < self.min_length:
            return False
        char_types = sum(bool(re.search(pattern, plaintext)) for pattern in self.patterns)
        if char_types < 2:
            return False
        return True

    def validate(self) -> ValidationResult:
        try:
            if not self.password_verify(self.password_bytes.decode(DEFAULT_ENCODING)):
                return ValidationResult(
                    False,
                    f"PEM private key password is too week, please check the password complexity!"
                    f"Min length is {self.min_length} and must contains at least two of the "
                    f"following character types: digits, uppercase, lowercase and special characters"
                    f"(`~!@#$%^&*()_=+|[{{}}];:'\",<.>/?), and spaces.")
            private_key = cert_parse.parse_pem_files(self.cert_path, self.password_bytes)
            if not self.validate_private_key_length(private_key):
                return ValidationResult(
                    False,
                    f"Certificate key algorithm or length does not meet requirements. {self.conf_tip}")
            server_obj = cert_parse.parse_cer_certificate(self.server_path)
            if len(server_obj.cert_list) == 0 or server_obj.cert_list[0].public_key != private_key.public_key():
                return ValidationResult(False,
                                        f"The PEM private key does not match the CER identity certificate."
                                        f"Please check 'ssl_certfile' or 'ssl_keyfile' config "
                                        f"in 'etc/conf/server.conf' file and try again.")
            return ValidationResult(True, f"PEM private key validation passed! {self.conf_tip}")
        except Exception as e:
            return ValidationResult(False, f"{e} {self.conf_tip}")
        finally:
            self.password_bytes = b''


class CRLValidator(CommonContentValidator):
    crl_list_data = None

    def validate_crl_validity(self, crl_list: x509.CertificateRevocationList) -> bool:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        return crl_list.last_update_utc <= current_time <= crl_list.next_update_utc

    def validate(self) -> ValidationResult:
        try:
            if self.cert_path is None or self.cert_path == "":
                return ValidationResult(True, "CRL not config!")
            cert_path_obj = Path(self.cert_path)
            if not cert_path_obj.exists():
                return ValidationResult(False, f"CRL file not exist: {self.cert_path}. {self.conf_tip}")
            crl_list = cert_parse.parse_crl_list(self.cert_path)
            self.crl_list_data = crl_list
            is_v2 = len(crl_list.extensions) > 0
            if not is_v2:
                return ValidationResult(False, f"CRL format is not X.509v2. {self.conf_tip}")
            if not self.validate_crl_validity(crl_list):
                return ValidationResult(False, f"CRL is not valid at current time. {self.conf_tip}")
            return ValidationResult(True, f"CRL validity passed! {self.conf_tip}")
        except Exception as e:
            return ValidationResult(False, f"{e} {self.conf_tip}")


class CerContentValidatorLink(AbstractValidatorLink):

    def build_link(self):
        conf_obj = self.conf_obj
        return [
            CerContentValidator(conf_obj.ssl_certfile, conf_tip="ssl_certfile"),
            CerContentValidator(conf_obj.ssl_ca_certs, conf_tip="ssl_ca_certs")
        ]


class CertValidator:

    def __init__(self, conf_obj: ConfObj):
        self.conf_obj = conf_obj

    def validate(self) -> ValidationResult:
        if not os.path.exists(CONFIG_FILE_PATH):
            return ValidationResult(False,
                                    f"Config file not exists! Please config 'etc/conf/server.conf' "
                                    f"file and try again.'")
        result = PathValidatorLink(self.conf_obj).validate()
        if not result.is_valid:
            return result
        result = CerContentValidatorLink(self.conf_obj).validate()
        if not result.is_valid:
            return result
        key_path = self.conf_obj.ssl_keyfile
        password_bytes = load_cert_password(self.conf_obj.ssl_keyfile_password)
        result = PrivateKeyValidator(cert_path=key_path, password_bytes=password_bytes,
                                     server_path=self.conf_obj.ssl_certfile, conf_tip="ssl_keyfile").validate()
        if not result.is_valid:
            return result
        crl_validator = CRLValidator(cert_path=self.conf_obj.ssl_crl_file, conf_tip="ssl_crl_file")
        result = crl_validator.validate()
        if result.is_valid:
            self.conf_obj.crl_list_data = crl_validator.crl_list_data
        return result
