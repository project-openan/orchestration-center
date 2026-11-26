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

"""Storage failure types, owned by the application, raised by every backend.

Callers must be able to tell three situations apart, which the previous code
conflated: "not found" is a normal ``None``/``False`` return; "unavailable"
means a dependency is down and must never masquerade as an empty result; and
"corrupt" means stored data no longer decodes into the domain model.
"""


class StorageError(Exception):
    """Base class for every storage failure."""


class StorageUnavailableError(StorageError, RuntimeError):
    """The backend could not be reached: connect failure, pool exhaustion, timeouts.

    Also a ``RuntimeError`` for compatibility with existing authentication
    guards. Operation boundaries must raise this instead of returning empty
    results; exception inheritance alone does not classify database failures.
    """


class StorageConflictError(StorageError):
    """A constraint conflict, e.g. a duplicate key or a lost compare-and-swap."""


class StorageCorruptionError(StorageError):
    """Stored data cannot be decoded back into the domain model."""


class StorageValidationError(StorageError):
    """The caller passed a value this backend cannot store (e.g. an over-long id)."""


class RoleReferenceError(StorageValidationError):
    """A role-bound workflow references an unauthorized catalog entry.

    Raised by the save-time catalog gate: the exact catalog release is not
    configured/readable (``CATALOG_VERSION_UNAVAILABLE``) or a reference is
    not approved (``INVALID_ROLE_SKILL``). Drafts never authorize, so the
    workflow must not be persisted as an executable template.
    """


class StorageConfigError(StorageValidationError):
    """The persistence configuration is missing or invalid; fail fast at startup."""
