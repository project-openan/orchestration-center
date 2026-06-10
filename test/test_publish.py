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

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from orchestrate.core.model.psop import PSOP, Task, Step, StepType, TaskStatus
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.publish import (
    WorkflowPublisher, PublishedWorkflow, PublishStatus, WorkflowPublishError,
    REGISTRY_FILENAME
)
from orchestrate.core.persistence import WorkflowStorage


@pytest.fixture
def temp_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = WorkflowStorage(storage_dir=tmpdir)
        yield storage


@pytest.fixture
def sample_psop():
    return PSOP(
        name="Test PSOP Workflow",
        description="A test PSOP for publishing",
        steps=[
            Step(
                name="step1",
                type=StepType.ALL_SUCCESS,
                subtasks=[
                    Task(description="Test task", agent="TestAgent", skill="test_skill")
                ]
            )
        ],
        tags=["test", "psop"]
    )


@pytest.fixture
def sample_preflow():
    return PreFlow(
        name="Test PreFlow",
        description="A test PreFlow for publishing",
        steps_md="# Test\n\nTest step"
    )


class TestPublishedWorkflow:
    def test_to_dict(self):
        from datetime import datetime, timezone
        dt = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
        pwf = PublishedWorkflow(
            workflow_id="wf-001", workflow_type="psop", name="TestWF",
            version="1.0.0", status=PublishStatus.PUBLISHED,
            published_at=dt, published_by="admin", description="desc"
        )
        d = pwf.to_dict()
        assert d["workflow_id"] == "wf-001"
        assert d["workflow_type"] == "psop"
        assert d["name"] == "TestWF"
        assert d["version"] == "1.0.0"
        assert d["status"] == "published"
        assert d["published_at"] == "2026-05-21T12:00:00+00:00"
        assert d["published_by"] == "admin"
        assert d["description"] == "desc"

    def test_to_dict_null_published_at(self):
        pwf = PublishedWorkflow(
            workflow_id="wf-002", workflow_type="preflow", name="TestPF",
            version="0.1.0", status=PublishStatus.DRAFT,
            published_at=None, published_by=None
        )
        d = pwf.to_dict()
        assert d["published_at"] is None
        assert d["published_by"] is None
        assert d["description"] is None


class TestWorkflowPublisher:
    def test_init_creates_empty_registry_when_no_file(self, temp_storage):
        publisher = WorkflowPublisher(temp_storage)
        assert publisher._published_registry == {}
        assert publisher._version_registry == {}

    def test_publish_psop(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0", published_by="tester")

        assert isinstance(result, PublishedWorkflow)
        assert result.workflow_type == "psop"
        assert result.name == "Test PSOP Workflow"
        assert result.version == "1.0.0"
        assert result.status == PublishStatus.PUBLISHED
        assert result.published_by == "tester"
        assert result.published_at is not None

    def test_publish_preflow(self, temp_storage, sample_preflow):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_preflow(sample_preflow, version="2.0.0", published_by="tester")

        assert result.workflow_type == "preflow"
        assert result.name == "Test PreFlow"
        assert result.version == "2.0.0"
        assert result.status == PublishStatus.PUBLISHED

    def test_get_published_versions(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        publisher.publish_psop(sample_psop, version="1.0.0")
        publisher.publish_psop(sample_psop, version="2.0.0")

        versions = publisher.get_published_versions("Test PSOP Workflow", "psop")
        assert len(versions) == 2
        assert versions[0].version == "1.0.0"
        assert versions[1].version == "2.0.0"

    def test_get_latest_version(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        publisher.publish_psop(sample_psop, version="1.0.0")
        publisher.publish_psop(sample_psop, version="3.0.0")

        latest = publisher.get_latest_version("Test PSOP Workflow", "psop")
        assert latest is not None
        assert latest.version == "3.0.0"

    def test_get_latest_version_nonexistent(self, temp_storage):
        publisher = WorkflowPublisher(temp_storage)
        assert publisher.get_latest_version("Nonexistent", "psop") is None

    def test_deprecate_workflow(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0")
        success = publisher.deprecate_workflow(result.workflow_id, "psop")
        assert success is True

        versions = publisher.get_published_versions("Test PSOP Workflow", "psop")
        assert len(versions) == 1
        assert versions[0].status == PublishStatus.DEPRECATED

    def test_deprecate_nonexistent(self, temp_storage):
        publisher = WorkflowPublisher(temp_storage)
        assert publisher.deprecate_workflow("nonexistent-id", "psop") is False

    def test_archive_workflow(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0")
        success = publisher.archive_workflow(result.workflow_id, "psop")
        assert success is True

        versions = publisher.get_published_versions("Test PSOP Workflow", "psop")
        assert len(versions) == 1
        assert versions[0].status == PublishStatus.ARCHIVED

    def test_is_published(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0")
        assert publisher.is_published(result.workflow_id) is True
        assert publisher.is_published("nonexistent-id") is False

    def test_list_published_filter_by_type(self, temp_storage, sample_psop, sample_preflow):
        publisher = WorkflowPublisher(temp_storage)
        publisher.publish_psop(sample_psop, version="1.0.0")
        publisher.publish_preflow(sample_preflow, version="1.0.0")

        psops = publisher.list_published(workflow_type="psop")
        preflows = publisher.list_published(workflow_type="preflow")
        assert len(psops) == 1
        assert len(preflows) == 1

    def test_list_published_filter_by_status(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        r1 = publisher.publish_psop(sample_psop, version="1.0.0")
        publisher.deprecate_workflow(r1.workflow_id, "psop")

        published = publisher.list_published(status=PublishStatus.PUBLISHED)
        deprecated = publisher.list_published(status=PublishStatus.DEPRECATED)
        assert len(published) == 0
        assert len(deprecated) == 1


class TestPublishPersistence:
    def test_registry_saved_to_disk(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        publisher.publish_psop(sample_psop, version="1.0.0")
        registry_file = temp_storage.psop_dir.parent / REGISTRY_FILENAME
        assert registry_file.exists()
        with open(registry_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "published" in data
        assert "versions" in data
        assert len(data["versions"]) == 1

    def test_registry_survives_restart(self, temp_storage, sample_psop):
        publisher1 = WorkflowPublisher(temp_storage)
        result = publisher1.publish_psop(sample_psop, version="1.0.0")

        publisher2 = WorkflowPublisher(temp_storage)
        versions = publisher2.get_published_versions("Test PSOP Workflow", "psop")
        assert len(versions) == 1
        assert versions[0].workflow_id == result.workflow_id
        assert versions[0].status == PublishStatus.PUBLISHED

    def test_deprecate_persists_across_restart(self, temp_storage, sample_psop):
        publisher1 = WorkflowPublisher(temp_storage)
        result = publisher1.publish_psop(sample_psop, version="1.0.0")
        publisher1.deprecate_workflow(result.workflow_id, "psop")

        publisher2 = WorkflowPublisher(temp_storage)
        versions = publisher2.get_published_versions("Test PSOP Workflow", "psop")
        assert len(versions) == 1
        assert versions[0].status == PublishStatus.DEPRECATED

    def test_empty_registry_when_no_file(self, temp_storage):
        publisher = WorkflowPublisher(temp_storage)
        assert publisher.list_published() == []
        assert publisher._published_registry == {}

    def test_registry_with_both_status_and_type_filter(self, temp_storage, sample_psop, sample_preflow):
        publisher = WorkflowPublisher(temp_storage)
        publisher.publish_psop(sample_psop, version="1.0.0")
        publisher.publish_preflow(sample_preflow, version="1.0.0")

        result = publisher.list_published(status=PublishStatus.PUBLISHED, workflow_type="psop")
        assert len(result) == 1
        assert result[0].workflow_type == "psop"

    def test_deprecate_who_workflow_type_mismatch(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0")
        assert publisher.deprecate_workflow(result.workflow_id, "preflow") is False

    def test_archive_who_workflow_type_mismatch(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        result = publisher.publish_psop(sample_psop, version="1.0.0")
        assert publisher.archive_workflow(result.workflow_id, "preflow") is False

    def test_corrupt_registry_file_falls_back_to_empty(self, temp_storage):
        registry_file = temp_storage.psop_dir.parent / REGISTRY_FILENAME
        registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(registry_file, "w", encoding="utf-8") as f:
            f.write("not valid json {{{")

        publisher = WorkflowPublisher(temp_storage)
        assert publisher._published_registry == {}

    def test_publish_psop_storage_error_wraps(self, temp_storage, sample_psop):
        publisher = WorkflowPublisher(temp_storage)
        with patch.object(temp_storage, 'save_psop', side_effect=RuntimeError("disk full")):
            with pytest.raises(WorkflowPublishError, match="Failed to publish PSOP"):
                publisher.publish_psop(sample_psop)

    def test_publish_preflow_storage_error_wraps(self, temp_storage, sample_preflow):
        publisher = WorkflowPublisher(temp_storage)
        with patch.object(temp_storage, 'save_preflow', side_effect=RuntimeError("disk full")):
            with pytest.raises(WorkflowPublishError, match="Failed to publish PreFlow"):
                publisher.publish_preflow(sample_preflow)
