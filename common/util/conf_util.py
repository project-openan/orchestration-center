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

import configparser
import os.path
import platform
import stat
import errno

from loguru import logger

from common.util import cipher_util
from common.util.conf_obj import ConfObj
from common.util.constant_param import SSL_PATH, CONFIG_FILE_PATH

_conf_singleton_obj: ConfObj | None = None

def get_conf_singleton() -> ConfObj:
    """Lazy-initialised singleton for the server configuration object."""
    global _conf_singleton_obj
    if _conf_singleton_obj is None:
        _conf_singleton_obj = load_conf_object(CONFIG_FILE_PATH)
    return _conf_singleton_obj

def load_conf_as_dict(conf_file: str) -> dict:
    config = configparser.ConfigParser()
    try:
        with open(conf_file, "r", encoding='utf-8') as f:
            config.read_string('[DEFAULT]\n' + f.read())
            return dict(config['DEFAULT'])
    except Exception as e:
        logger.error(f"load config failed, {e}")
        return {}

def load_conf_object(conf_file: str) -> ConfObj:
    config_dict = load_conf_as_dict(conf_file)
    from common.util.config_util import apply_env_overrides
    apply_env_overrides(config_dict)
    return ConfObj.as_object(config_dict)

def load_cert_password(password_path: str) -> bytes:
    if not os.path.exists(password_path):
        return b''
    with open(password_path, 'r', encoding='utf-8') as f:
        str_content = f.read().strip()
        return cipher_util.decrypt(str_content)

def set_ssl_folder_permissions():
    if platform.system().lower() != "linux":
        logger.info(f"current system type is: {platform.system().lower()}")
        return
    _restrict_ssl_permissions(SSL_PATH, 0o700)
    for root, _, files in os.walk(SSL_PATH):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            _restrict_ssl_permissions(file_path, 0o600)


def _restrict_ssl_permissions(path, desired_mode):
    current = stat.S_IMODE(os.stat(path).st_mode)
    if current == desired_mode:
        return
    try:
        os.chmod(path, desired_mode)
    except OSError as exc:
        if exc.errno not in (errno.EROFS, errno.EPERM, errno.EACCES):
            raise
        if current & (stat.S_IRWXO | stat.S_IWGRP):
            raise PermissionError(f"Unsafe permissions on TLS mount: {path}") from exc
        logger.info(f"Using deployment-managed TLS permissions on {path}")
# Backward-compatible alias - prefer get_conf_singleton() in new code.
conf_singleton_obj = None  # type: ignore[assignment]

def __getattr__(name: str):
    """Module-level __getattr__ to lazily resolve conf_singleton_obj."""
    if name == "conf_singleton_obj":
        return get_conf_singleton()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
