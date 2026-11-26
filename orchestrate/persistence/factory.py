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

"""Single selection point: persistence mode -> backend instance.

Two rules this module exists to enforce:

* the list of known modes is *imported* from
  :mod:`common.util.persistence_mode`, never copied -- a second copy of the
  enumeration is how the registry service ended up with five lists to keep in
  sync whenever a backend was added;
* driver imports happen inside the builders, so a file-mode deployment never
  loads ``psycopg2`` or ``pymysql``.
"""

from typing import Callable, Dict, Optional

from loguru import logger

from common.util.persistence_mode import DEFAULT_STORAGE_MODE, KNOWN_STORAGE_MODES, persistence_mode
from orchestrate.persistence.contracts import PersistenceBackend
from orchestrate.persistence.errors import StorageConfigError

BackendBuilder = Callable[[str, dict], PersistenceBackend]

_BUILDERS: Dict[str, BackendBuilder] = {}


def register(mode: str, builder: BackendBuilder) -> None:
    """Register (or replace) the builder for ``mode``.

    This is the supported extension point for a new backend; built-in modes are
    registered at the bottom of this module.
    """
    _BUILDERS[str(mode).lower()] = builder


def known_modes() -> frozenset:
    """Every mode this service understands (single source of truth)."""
    return KNOWN_STORAGE_MODES


def _build_file(mode: str, conf: dict) -> PersistenceBackend:
    from orchestrate.persistence.file_backend import FilePersistenceBackend

    return FilePersistenceBackend(conf)


def _build_sql(mode: str, conf: dict) -> PersistenceBackend:
    from orchestrate.persistence.sql_backend import SqlPersistenceBackend

    return SqlPersistenceBackend(mode=mode, conf=conf)


def create(mode: Optional[str] = None, conf: Optional[dict] = None) -> PersistenceBackend:
    """Build the backend for ``mode`` (default: the configured mode).

    Raises :class:`StorageConfigError` for an unknown or unregistered mode
    instead of silently falling back to file storage.
    """
    deployment = str((conf or {}).get("deployment_mode", "single")).lower()
    if deployment not in {"single", "cluster"}:
        raise StorageConfigError("deployment_mode must be single or cluster")
    selected = mode
    if selected is None:
        selected = conf["persistence_mode"] if conf is not None and "persistence_mode" in conf else persistence_mode()
    resolved = str(selected).lower()
    if resolved not in KNOWN_STORAGE_MODES:
        raise StorageConfigError(
            f"Unsupported persistence_mode '{resolved}'; expected one of {sorted(KNOWN_STORAGE_MODES)}"
        )
    if deployment == "cluster" and resolved == "file":
        raise StorageConfigError("Cluster deployment requires PostgreSQL or MySQL")
    builder = _BUILDERS.get(resolved)
    if builder is None:
        raise StorageConfigError(f"No storage backend registered for persistence_mode '{resolved}'")
    logger.info(f"[Storage] Selected '{resolved}' persistence backend")
    return builder(resolved, conf if conf is not None else {})


def build_context(mode: Optional[str] = None, conf: Optional[dict] = None):
    """Build the backend for ``mode`` and resolve its repositories.

    The single call the composition root makes; nothing else needs to know a
    backend is involved.
    """
    from orchestrate.persistence.context import StorageContext

    return StorageContext(create(mode=mode, conf=conf))


register(DEFAULT_STORAGE_MODE, _build_file)
register("postgresql", _build_sql)
register("mysql", _build_sql)
