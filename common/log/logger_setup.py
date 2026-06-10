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
import sys
import zipfile

from loguru import logger
from pathlib import Path

from common.util.config_util import get_root_path

root_path = get_root_path()
_LOG_DIR = Path(root_path) / "log"
_LOG_DIR.mkdir(exist_ok=True)
os.chmod(_LOG_DIR, 0o700)

LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} - {name} - {level} - {message}"


def add_module_logger(module_prefix: str):
    def safe_compression(source_file):
        try:
            zip_file = Path(str(source_file) + ".zip")
            with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(source_file, arcname=Path(source_file).name)
            os.chmod(zip_file, 0o440)
            return zip_file
        except Exception as e:
            logger.warning(f"Log compression failed (non-fatal): {e}")
            return None

    logger.configure(extra={"request_id": ''})
    logger.remove()
    old_mask = os.umask(0o027)
    logger.add(sys.stdout, format=LOG_FORMAT, level="INFO", backtrace=False, colorize=True)

    log_file = _LOG_DIR / f"{module_prefix}_{{time:YYYY-MM-DD}}.log"
    logger.add(
        log_file,
        format=LOG_FORMAT,
        level="INFO",
        rotation="10 MB",
        retention="30 days",
        compression=safe_compression,
        encoding="utf-8",
        enqueue=True,
    )

    logger.bind(request_id='init').info("Log system initialized")
    os.umask(old_mask)
