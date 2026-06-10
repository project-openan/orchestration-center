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

class CertObj:
    subject = None
    issuer = None
    serial_number = None
    valid_from = None
    valid_to = None
    version = None
    public_key = None
    org_cert = None

    @classmethod
    def from_dict(cls, cert_dict):
        obj = cls()
        obj.subject = cert_dict.get('subject', '')
        obj.issuer = cert_dict.get('issuer', '')
        obj.serial_number = cert_dict.get('serial_number', '')
        obj.valid_from = cert_dict.get('valid_from', '')
        obj.valid_to = cert_dict.get('valid_to', '')
        obj.version = cert_dict.get('version', '')
        obj.public_key = cert_dict.get('public_key', None)
        obj.org_cert = cert_dict.get('org_cert', None)
        return obj


class X509Obj:
    private_key = None
    public_key = None
    cert_list = []

    def __init__(self, cert_list, private_key=None, public_key=None):
        self.cert_list = cert_list
        self.private_key = private_key
        self.public_key = public_key
