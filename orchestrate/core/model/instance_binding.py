# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Technical-pilot admission contracts; these are not capability certificates."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from orchestrate.core.model.role_catalog import CatalogModel, Identifier


class ServiceScope(CatalogModel):
    tenant: Identifier
    site: Identifier
    business_object: Identifier

    def covers(self, requested: "ServiceScope") -> bool:
        # Each record is a tuple: never form a Cartesian product of sites/objects.
        return all(
            getattr(self, key) in ("*", getattr(requested, key))
            for key in ("tenant", "site", "business_object")
        )


class SkillMapping(CatalogModel):
    role_id: Identifier
    role_version: Identifier
    skill_id: Identifier
    instance_skill_id: Identifier
    execution_skill: Identifier


class InstanceBinding(CatalogModel):
    instance_id: Identifier
    agent_name: Identifier
    endpoint: Identifier
    enabled: bool = False
    technical_status: Literal["pending", "passed", "failed"] = "pending"
    priority: int = Field(default=0, strict=True)
    scopes: list[ServiceScope] = Field(min_length=1)
    skills: list[SkillMapping] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_mappings(self):
        keys = [(s.role_id, s.role_version, s.skill_id) for s in self.skills]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate role skill mapping")
        return self


class InstanceRegistry(CatalogModel):
    config_version: Identifier
    instances: list[InstanceBinding]

    @model_validator(mode="after")
    def unique_instances(self):
        ids = [i.instance_id for i in self.instances]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate instance ID")
        return self


class ObservedInstance(CatalogModel):
    """Projection supplied by a trusted card adapter, not by an execution request.

    The adapter must validate identity, supported protocols/extensions and
    interaction prerequisites. This projection does not replace a full card
    snapshot or authenticate any endpoint.
    """

    instance_id: Identifier
    agent_name: Identifier
    endpoint: Identifier
    skills: dict[Identifier, Identifier]  # AgentCard skill.id -> execution name
    prerequisites_passed: bool = False


class ResolutionContext(CatalogModel):
    """Trusted scope and authorization results supplied by the application.

    Caller identity and object ownership must be verified before construction.
    Merely constructing this object does not perform authorization.
    """

    caller_id: Identifier
    scope: ServiceScope
    authorized_instance_ids: set[Identifier]

    @model_validator(mode="after")
    def concrete_scope(self):
        if "*" in self.scope.model_dump().values():
            raise ValueError("Execution scope must be concrete")
        return self


class ResolutionPolicy(CatalogModel):
    policy_version: Identifier
    tie_break: Literal["error", "instance_id"] = "error"
    task_overrides: dict[Identifier, Identifier] = Field(default_factory=dict)
    group_overrides: dict[Identifier, Identifier] = Field(default_factory=dict)


def load_instance_registry(path: str | Path) -> InstanceRegistry:
    return InstanceRegistry.model_validate_json(Path(path).read_text(encoding="utf-8"))
