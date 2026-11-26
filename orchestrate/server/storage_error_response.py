# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Public storage errors: stable status codes, never driver details."""

from fastapi import HTTPException

from orchestrate.persistence.errors import (
    RoleReferenceError, StorageConfigError, StorageConflictError, StorageError,
    StorageUnavailableError, StorageValidationError,
)


def storage_http_exception(exc: StorageError) -> HTTPException:
    if isinstance(exc, RoleReferenceError):
        # Role-reference rejections are API-contract codes, not driver details.
        return HTTPException(422, str(exc))
    if isinstance(exc, StorageConfigError):
        return HTTPException(500, "Storage configuration error")
    if isinstance(exc, StorageUnavailableError):
        return HTTPException(503, "Storage backend unavailable")
    if isinstance(exc, StorageConflictError):
        return HTTPException(409, "Storage conflict")
    if isinstance(exc, StorageValidationError):
        return HTTPException(422, "Invalid storage operation")
    return HTTPException(500, "Storage operation failed")
