# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Sandbox capability guards, before registry access or execution scheduling."""

from orchestrate.core.catalog_gate import has_role_tasks
from orchestrate.core.model.psop import PSOP

ROLE_SANDBOX_NOT_SUPPORTED = "ROLE_SANDBOX_NOT_SUPPORTED"


def require_instance_workflow(psop: PSOP) -> None:
    """Unresolved role identities must never be treated as Stub agent names."""
    if has_role_tasks(psop):
        raise ValueError(f"{ROLE_SANDBOX_NOT_SUPPORTED}: Role workflows require verified Host execution")
