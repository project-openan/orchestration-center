# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""HTTP translation shared by internal and public role generation routes."""

from fastapi import HTTPException
from orchestrate.core.model.psop import PSOP
from orchestrate.core.role_generation import (
    RoleGenerationError, assemble_role_workflow, load_generation_context, validate_current_catalog,
    GenerationOptions, RoleGenerationContext, generation_stage,
)


def prepare_generation(options: GenerationOptions, entry: str) -> RoleGenerationContext | None:
    return load_generation_context(options.catalog_version, entry=entry) if options.binding == "role" else None


def role_arguments(context: RoleGenerationContext | None) -> dict:
    # Omit new keywords entirely on the legacy path to preserve embedders.
    return {} if context is None else {"binding": "role", "role_context": context}


def validate_before_save(workflow: PSOP, context: RoleGenerationContext | None) -> None:
    if context is None:
        return
    with generation_stage(context, "validate_save"):
        assemble_role_workflow(workflow.model_dump(mode="json"), context)
        validate_current_catalog(context)


def generation_http_exception(error):
    if isinstance(error, RoleGenerationError):
        return HTTPException(status_code=422, detail={"code": error.code, "message": error.message})
    return HTTPException(status_code=500, detail="Role generation service failed")
