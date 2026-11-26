# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Save-time authorization gate for role-bound workflows.

Workflows without role tasks pass unchanged. A workflow with role tasks may
only be persisted when its exact catalog release is configured and every
(role, version, skill) reference is approved there: drafts never authorize,
and a missing catalog must never fail open.
"""

from typing import Callable

from loguru import logger

from orchestrate.core.model.psop import PSOP
from orchestrate.core.model.role_catalog import RoleCatalog, load_role_catalog
from orchestrate.persistence.errors import RoleReferenceError


def configured_catalog_path() -> str | None:
    """server.conf key ``role_catalog_path``; unset means no catalog release."""
    from common.util.config_util import get_conf

    value = get_conf().get("role_catalog_path")
    if value is None:
        return None
    return str(value).strip() or None


def has_role_tasks(psop: PSOP) -> bool:
    return any(task.binding == "role" for step in psop.steps for task in step.subtasks)


def load_approved_catalog(
    catalog_path: str | None, expected_version: str | None,
    subject: str = "catalog release",
) -> RoleCatalog:
    """Load the exact configured release or fail closed.

    ``subject`` carries operator context (workflow identity, caller) into the
    rejection logs; the raised messages stay caller-safe and never name local
    paths. Shared by the save gate and the dispatch adapter.
    """
    if not catalog_path:
        logger.warning(
            "[CatalogGate] Rejected {}: no role catalog configured "
            "(server.conf key role_catalog_path)", subject,
        )
        raise RoleReferenceError(
            "CATALOG_VERSION_UNAVAILABLE: no role catalog configured "
            "(server.conf key role_catalog_path)"
        )
    try:
        return load_role_catalog(catalog_path, expected_version)
    except (OSError, ValueError) as error:
        # Missing/unreadable file, corrupt JSON and invalid catalog structure
        # are all "the requested release is unavailable"; the original error
        # stays as the internal cause instead of leaking local paths or full
        # validation payloads to callers. Server-side logs still name the
        # configured path so operators can fix the release file.
        logger.warning(
            "[CatalogGate] Rejected {}: catalog release {!r} cannot be loaded ({!r})",
            subject, catalog_path, error,
        )
        raise RoleReferenceError(
            "CATALOG_VERSION_UNAVAILABLE: requested catalog cannot be loaded"
        ) from error


def ensure_role_references_authorized(psop: PSOP, catalog_path: str | None) -> None:
    """Reject persistence of role workflows that no approved release authorizes."""
    if not has_role_tasks(psop):
        return
    subject = (
        f"role workflow id={psop.id} name={psop.name!r} "
        f"catalog_version={psop.catalog_version}"
    )
    catalog = load_approved_catalog(catalog_path, psop.catalog_version, subject=subject)
    try:
        catalog.validate_workflow(psop)
    except ValueError as error:
        logger.warning(
            "[CatalogGate] Rejected role workflow id={} catalog_version={}: {}",
            psop.id, psop.catalog_version, error,
        )
        raise RoleReferenceError(str(error)) from error


class CatalogGate:
    """Handler wrapper: authorize before delegating to the storage handler.

    ``path_resolver`` defaults to a call-time lookup of
    ``configured_catalog_path`` so configuration changes and test overrides
    take effect without rebuilding the (cached) gate.
    """

    def __init__(self, storage, path_resolver: Callable[[], str | None] | None = None):
        self._storage = storage
        self._path_resolver = path_resolver

    def handle(self, psop: PSOP):
        # Only real PSOP instances can carry role references; storage-layer
        # probes and internal plumbing pass other payloads straight through.
        if isinstance(psop, PSOP):
            resolver = self._path_resolver or configured_catalog_path
            ensure_role_references_authorized(psop, resolver())
        return self._storage.handle(psop)
