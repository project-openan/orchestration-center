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

import os
import ssl

from common.util.constant_param import ROOT_PATH

DEFAULT_IP = "127.0.0.1"
DEFAULT_PORT = 5001
DEFAULT_SSL_CERT_FILE = 'etc/ssl/server.cer'
DEFAULT_SSL_KEYFILE = 'etc/ssl/server_key.pem'
DEFAULT_KEY_PASSWORD = 'etc/conf/cert_pwd'
DEFAULT_SSL_CA_CERTS = 'etc/ssl/trust.cer'
DEFAULT_SSL_CRLFILE = 'etc/ssl/revocationlist.crl'
DEFAULT_VERIFY_CLIENT = ssl.CERT_REQUIRED


def as_absolute_path(path):
    new_path = path
    if path.startswith('etc/'):
        new_path = os.path.join(ROOT_PATH, path)
    new_path = os.path.normpath(new_path)
    return new_path


class ConfObj:
    ip = DEFAULT_IP
    port = DEFAULT_PORT
    ssl_certfile = DEFAULT_SSL_CERT_FILE
    ssl_keyfile = DEFAULT_SSL_KEYFILE
    ssl_keyfile_password = DEFAULT_KEY_PASSWORD
    ssl_ca_certs = DEFAULT_SSL_CA_CERTS
    ssl_crl_file = DEFAULT_SSL_CRLFILE
    verify_client = DEFAULT_VERIFY_CLIENT
    crl_list_data = None

    @classmethod
    def as_object(cls, in_dict: dict):
        obj = cls()
        obj.ip = in_dict.get('ip', DEFAULT_IP)
        port = in_dict.get('port', DEFAULT_PORT)
        if isinstance(port, str):
            port = int(port)
        obj.port = port
        obj.ssl_certfile = as_absolute_path(in_dict.get('ssl_certfile', DEFAULT_SSL_CERT_FILE))
        obj.ssl_keyfile = as_absolute_path(in_dict.get('ssl_keyfile', DEFAULT_SSL_KEYFILE))
        obj.ssl_keyfile_password = as_absolute_path(in_dict.get('ssl_keyfile_password', DEFAULT_KEY_PASSWORD))
        obj.ssl_ca_certs = as_absolute_path(in_dict.get('ssl_ca_certs', DEFAULT_SSL_CA_CERTS))

        crl_path = in_dict.get('ssl_crl_file', "")
        obj.ssl_crl_file = as_absolute_path(crl_path) if len(crl_path) > 0 else crl_path

        not_verified = in_dict.get('verify_client', "").lower() == 'false'
        obj.verify_client = ssl.CERT_NONE if not_verified else ssl.CERT_REQUIRED
        return obj

    def get_crl_list(self):
        if self.crl_list_data is None:
            return []
        crl_list = []
        for one_crl in self.crl_list_data:
            crl_list.append(hex(one_crl.serial_number))
        return crl_list
