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

"""Certificate identity and real TLS handshake regressions; no external services."""

import ipaddress
import socket
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from cryptography import x509

from common.cert.certificate_generator import CertificateGenerator


PASSWORD = "Test-only!Password1"


def read_san(directory):
    cert = x509.load_pem_x509_certificate((directory / "server_RSA.cer").read_bytes())
    return cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value


def test_default_sans_cover_loopback(tmp_path):
    assert CertificateGenerator().generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    san = read_san(tmp_path)
    assert san.get_values_for_type(x509.DNSName) == ["localhost"]
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("127.0.0.1"), ipaddress.ip_address("::1")]


def test_explicit_sans_replace_defaults_and_deduplicate(tmp_path):
    generator = CertificateGenerator(dns_names=["ORCH.example.test", "orch.example.test"],
                                     ip_addresses=["192.0.2.10", "2001:db8::1"])
    assert generator.generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    san = read_san(tmp_path)
    assert san.get_values_for_type(x509.DNSName) == ["orch.example.test"]
    assert san.get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("192.0.2.10"), ipaddress.ip_address("2001:db8::1")]


@pytest.mark.parametrize("settings", [
    {"dns_names": []}, {"dns_names": ["https://localhost:5001"]},
    {"dns_names": ["127.0.0.1"]}, {"dns_names": ["bad name"]},
    {"ip_addresses": ["999.1.1.1"]}, {"ip_addresses": ["localhost"]},
])
def test_invalid_sans_do_not_write_credentials(tmp_path, settings):
    assert not CertificateGenerator(**settings).generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    assert list(tmp_path.iterdir()) == []


def test_data_signing_has_no_server_identity_extension(tmp_path):
    assert CertificateGenerator().generate_self_signed_cert(str(tmp_path), "dataSigning", PASSWORD)
    with pytest.raises(x509.ExtensionNotFound):
        read_san(tmp_path)


def test_existing_private_key_alone_is_never_overwritten(tmp_path):
    key = tmp_path / "server_key_RSA.pem"
    key.write_bytes(b"existing-private-key-placeholder")
    assert not CertificateGenerator().generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    assert key.read_bytes() == b"existing-private-key-placeholder"
    assert not (tmp_path / "server_RSA.cer").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits do not represent Windows ACLs")
def test_private_key_permissions_are_restricted(tmp_path):
    assert CertificateGenerator().generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    assert (tmp_path / "server_key_RSA.pem").stat().st_mode & 0o777 == 0o600


def test_cli_passes_explicit_sans_to_generator(tmp_path, monkeypatch):
    import generate_selfsign_cert as cli

    monkeypatch.setattr(sys, "argv", ["generate_selfsign_cert", str(tmp_path), "serverAuth",
                                     "--dns", "orch.example.test", "--ip", "192.0.2.10"])
    monkeypatch.setattr(cli, "input_password_with_validation", lambda prompt: PASSWORD)
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 0
    assert read_san(tmp_path).get_values_for_type(x509.DNSName) == ["orch.example.test"]
    assert read_san(tmp_path).get_values_for_type(x509.IPAddress) == [ipaddress.ip_address("192.0.2.10")]


def test_cli_rejects_sans_for_data_signing_before_password_prompt(tmp_path, monkeypatch):
    import generate_selfsign_cert as cli

    monkeypatch.setattr(sys, "argv", ["generate_selfsign_cert", str(tmp_path), "dataSigning", "--dns", "localhost"])
    monkeypatch.setattr(cli, "input_password_with_validation", lambda prompt: pytest.fail("unexpected password prompt"))
    with pytest.raises(SystemExit) as exit_info:
        cli.main()
    assert exit_info.value.code == 2
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def tls_endpoint(tmp_path):
    assert CertificateGenerator().generate_self_signed_cert(str(tmp_path), "serverAuth", PASSWORD)
    certificate = tmp_path / "server_RSA.cer"
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certificate, tmp_path / "server_key_RSA.pem", PASSWORD)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = server_context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server.server_address, ssl.create_default_context(cafile=str(certificate))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize("hostname", ["127.0.0.1", "localhost", "::1"])
def test_real_tls_validates_certificate_chain_and_hostname(tls_endpoint, hostname):
    address, context = tls_endpoint
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    with socket.create_connection(address, timeout=3) as tcp:
        with context.wrap_socket(tcp, server_hostname=hostname) as tls:
            tls.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
            assert tls.recv(1024).startswith(b"HTTP/1.0 200")


def test_real_tls_still_rejects_an_unlisted_ip(tls_endpoint):
    address, context = tls_endpoint
    with socket.create_connection(address, timeout=3) as tcp:
        with pytest.raises(ssl.SSLCertVerificationError, match="IP address mismatch"):
            context.wrap_socket(tcp, server_hostname="127.0.0.2")
