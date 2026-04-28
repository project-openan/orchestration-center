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

import json
import os.path
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

from loguru import logger

from common.util.config_util import get_root_path, load_configs

FILE_PERMISSION_MODE = 0o600


class LogLevel:
    DANGER = "Critical"
    INFO = "Information"
    MINOR = "General"


class OperationName:
    START_SERVER = "Start Server"
    SAVE_PSOP = "Save PSOP"
    DELETE_PSOP = "Delete PSOP"
    EXECUTE_PSOP = "Execute PSOP"


class OperationObject:
    SERVER = "Server"
    PSOP = "PSOP"


class OperationResult:
    SUCCESS = "Success"
    FAILURE = "Failure"


class AuditLogger:

    def __init__(self):
        self.config = self._load_config()
        self.max_size = int(self.config.get("audit_log_max_file_size_mb", 5)) * 1024 * 1024
        self.backup_count = int(self.config.get("audit_log_backup_count", 5)) - 1
        parent_path = os.path.join(get_root_path(), "log", "audit")
        audit_log_dir = Path(parent_path)
        audit_log_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(audit_log_dir, 0o700)
        self.log_file = os.path.join(parent_path, "audit.log")
        self.lock = threading.Lock()

    @staticmethod
    def _load_config():
        root_path = get_root_path()
        log_config = {}
        log_config_path = os.path.join(root_path, "etc", "conf", "log_config.conf")

        if os.path.exists(log_config_path):
            load_configs(log_config_path, log_config)
        return log_config

    def audit(self, log_entry: Dict[str, Any]):
        log_data = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "clientIp": log_entry.get("client_ip", ""),
            "userName": log_entry.get("user_name", ""),
            "level": log_entry.get("level", LogLevel.INFO),
            "operationName": log_entry.get("operation_name"),
            "object": log_entry.get("object_name"),
            "result": log_entry.get("result"),
            "details": log_entry.get("details", {}),
        }
        self._write_log(log_data)

    def _get_file_size(self):
        return os.path.getsize(self.log_file) if os.path.exists(self.log_file) else 0

    def _rotate_logs(self):
        if self._get_file_size() < self.max_size:
            return
        oldest = f"{self.log_file}.{self.backup_count + 1}"
        if os.path.exists(oldest):
            try:
                os.remove(oldest)
            except Exception as e:
                logger.error(f"Warning:failed to remove {oldest}: {e}")
        for i in range(self.backup_count, 0, -1):
            src = f"{self.log_file}.{i}"
            dst = f"{self.log_file}.{i + 1}"
            if os.path.exists(src):
                try:
                    os.rename(src, dst)
                except Exception as e:
                    logger.error(f"Warning:failed to rename {src} to {dst}: {e}")
        if os.path.exists(self.log_file):
            try:
                os.rename(self.log_file, f"{self.log_file}.1")
            except Exception as e:
                logger.error(f"Warning:failed to rename {self.log_file} to {self.log_file}.1: {e}")
                return
        try:
            open(self.log_file, "w").close()
            os.chmod(self.log_file, FILE_PERMISSION_MODE)
        except Exception as e:
            logger.error(f"Error:failed to create new log file: {e}")

    def _write_log(self, log_data: Dict[str, Any]):
        with self.lock:
            self._rotate_logs()
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_data, ensure_ascii=False) + '\n')
            os.chmod(self.log_file, FILE_PERMISSION_MODE)


audit_logger = AuditLogger()
