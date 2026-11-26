# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Versioned business definitions, independent of deployed AgentCards."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# Generous ceiling: covers names/descriptions/evidence digests while keeping
# a corrupt or hostile catalog file from injecting unbounded strings.
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1024)]
ReviewStatus = Literal["draft", "pending_review", "approved", "rejected"]


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleSource(CatalogModel):
    package: Identifier
    pdf: Identifier
    pdf_pages: list[Annotated[int, Field(gt=0, le=100000)]] = Field(min_length=1, max_length=10000)


class RoleSkill(CatalogModel):
    skill_id: Identifier
    name: Identifier
    description: Identifier
    source: RoleSource
    review_status: ReviewStatus = "draft"
    input_summary: Identifier | None = None
    input_source: RoleSource | None = None
    output_summary: Identifier | None = None
    output_source: RoleSource | None = None

    @model_validator(mode="after")
    def validate_evidence(self):
        for direction in ("input", "output"):
            summary = getattr(self, f"{direction}_summary")
            source = getattr(self, f"{direction}_source")
            if (summary is None) != (source is None):
                raise ValueError(f"{direction} summary and source must be supplied together")
        return self


class RoleDefinition(CatalogModel):
    role_id: Identifier
    role_version: Identifier
    name: Identifier
    description: Identifier
    source: RoleSource
    skills: list[RoleSkill] = Field(min_length=1)
    review_status: ReviewStatus = "draft"

    @model_validator(mode="after")
    def validate_skills(self):
        ids = [skill.skill_id for skill in self.skills]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate skill ID within role")
        if self.review_status == "approved" and not any(
            skill.review_status == "approved" for skill in self.skills
        ):
            raise ValueError("Approved roles require an approved skill")
        return self


class RoleCatalog(CatalogModel):
    catalog_version: Identifier
    roles: list[RoleDefinition]

    @model_validator(mode="after")
    def validate_roles(self):
        identities = [(role.role_id, role.role_version) for role in self.roles]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate role/version in catalog")
        return self

    def validate_workflow(self, psop):
        """Validate exact references; drafts never authorize workflow execution."""
        tasks = [t for s in psop.steps for t in s.subtasks if t.binding == "role"]
        if not tasks:
            return
        if psop.catalog_version != self.catalog_version:
            raise ValueError("CATALOG_VERSION_UNAVAILABLE")
        approved = {
            (role.role_id, role.role_version, skill.skill_id)
            for role in self.roles if role.review_status == "approved"
            for skill in role.skills if skill.review_status == "approved"
        }
        for task in tasks:
            if (task.agent, task.role_version, task.skill) not in approved:
                raise ValueError(f"INVALID_ROLE_SKILL: {task.task_id}")


def read_role_catalog(path: str | Path) -> RoleCatalog:
    """Read one explicitly configured release, without selecting another file."""
    return RoleCatalog.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_role_catalog(path: str | Path, expected_version: str) -> RoleCatalog:
    """Read an explicit local release; never silently fall back to latest."""
    catalog = read_role_catalog(path)
    if catalog.catalog_version != expected_version:
        raise ValueError("CATALOG_VERSION_UNAVAILABLE")
    return catalog
