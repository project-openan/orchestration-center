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

#!/usr/bin/env python3
"""Standalone self-signed certificate generation tool for the orchestration center.

Usage:
    python -m generate_selfsign_cert <cert_dir> <cert_usage> [--dns HOST] [--ip ADDRESS]

    cert_dir:   Certificate directory path
    cert_usage: serverAuth (TLS communication) or dataSigning (data signing)

The password for the private key is entered interactively.
serverAuth defaults to localhost, 127.0.0.1 and ::1; explicit SAN options replace these defaults.
"""

import argparse
import sys

from common.cert.certificate_generator import CertificateGenerator
from common.util.password_util import input_password_with_validation


def generate_self_signed_cert(cert_dir: str, cert_usage: str, password: str, *,
                              dns_names: list[str] | None = None,
                              ip_addresses: list[str] | None = None) -> bool:
    try:
        generator = CertificateGenerator(key_algorithm='RSA', dns_names=dns_names, ip_addresses=ip_addresses)
        success = generator.generate_self_signed_cert(cert_dir, cert_usage, password)

        if success:
            print(f"Successfully generated self-signed certificates in {cert_dir}")
            return True
        else:
            print(f"Failed to generate certificates")
            return False
    except Exception as e:
        print(f"Error generating certificates: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cert_dir", help="New certificate directory; existing files are not overwritten")
    parser.add_argument("cert_usage", choices=("serverAuth", "dataSigning"))
    parser.add_argument("--dns", action="append", help="DNS SAN; repeat for multiple hostnames")
    parser.add_argument("--ip", action="append", help="IP SAN; repeat for IPv4 or IPv6 addresses")
    args = parser.parse_args()
    if args.cert_usage == "dataSigning" and (args.dns or args.ip):
        parser.error("--dns and --ip apply only to serverAuth certificates")

    password = input_password_with_validation("Enter private key password")

    if generate_self_signed_cert(args.cert_dir, args.cert_usage, password,
                                 dns_names=args.dns, ip_addresses=args.ip):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
