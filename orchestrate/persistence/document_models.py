# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Typed repositories on the operational document storage port."""

from orchestrate.core.model.preflow import PreFlow
from orchestrate.persistence.contracts import PreflowRepository
from orchestrate.persistence.errors import StorageCorruptionError


class DocumentPreflowRepository(PreflowRepository):
    def __init__(self, documents):
        self.documents = documents

    def save(self, preflow):
        self.documents.save("preflows", preflow.id, preflow.model_dump(mode="json"))
        return preflow.id

    def get(self, preflow_id):
        value = self.documents.get("preflows", preflow_id)
        if value is None:
            return None
        try:
            return PreFlow.model_validate(value)
        except ValueError as exc:
            raise StorageCorruptionError("Stored PreFlow is invalid") from exc

    def list_ids(self):
        try:
            return [PreFlow.model_validate(value).id for value in self.documents.list("preflows")]
        except ValueError as exc:
            raise StorageCorruptionError("Stored PreFlow is invalid") from exc

    def delete(self, preflow_id):
        return self.documents.delete("preflows", preflow_id)
