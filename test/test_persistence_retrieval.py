#!/usr/bin/env python3
# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
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

"""
Persistence and Retrieval module test script
Tests for framework/core/persistence.py and retrieval.py
"""

import sys
import os
import tempfile
from datetime import datetime

# Add project root to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP, Task, TaskStatus, Step, StepType, JumpCondition
from orchestrate.core.persistence import WorkflowStorage, WorkflowStorageError
from orchestrate.core.retrieval import WorkflowRetrieval, WorkflowSearchResult


def create_test_preflow(name: str = "Test PreFlow", description: str = "Test description") -> PreFlow:
    """Create a PreFlow object for testing"""
    return PreFlow(
        name=name,
        description=description,
        steps_md="# Test Process\n\nThis is a test process for unit testing.",
        tags=["test", "unit-test", "automation"]
    )


def create_test_psop(name: str = "Test PSOP", description: str = "Test PSOP description") -> PSOP:
    """Create a PSOP object for testing"""
    # Create tasks
    task1 = Task(
        description="Execute energy saving analysis",
        agent="energy_agent",
        skill="best_effort_energy_saving",
        status=TaskStatus.PENDING
    )

    task2 = Task(
        description="Execute backup analysis",
        agent="backup_agent",
        skill="extreme_backup_energy_saving",
        status=TaskStatus.PENDING
    )

    # Create steps
    step1 = Step(
        name="analysis_step",
        type=StepType.ALL_SUCCESS,
        subtasks=[task1, task2],
        next=None  # Add next parameter
    )

    # Create PSOP
    return PSOP(
        name=name,
        description=description,
        steps=[step1],
        tags=["test", "psop-test", "automation"],
        related_preflow="test_preflow_123",
        user_intent="Test user intent for unit testing"  # Add user_intent parameter
    )


def test_storage_initialization():
    """Test storage initialization"""
    print("Testing storage initialization...")

    # Test default storage directory
    storage = WorkflowStorage()
    print(f"  PSOP directory: {storage.psop_dir}")
    print(f"  PreFlow directory: {storage.preflow_dir}")

    # Test custom storage directory
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_storage = WorkflowStorage(storage_dir=temp_dir)
        print(f"  Custom PSOP directory: {custom_storage.psop_dir}")
        print(f"  Custom PreFlow directory: {custom_storage.preflow_dir}")

        # Verify directories were created
        assert custom_storage.psop_dir.exists()
        assert custom_storage.preflow_dir.exists()

        print("  Storage initialization test passed [OK]")


def test_save_and_load_preflow():
    """Test saving and loading PreFlow"""
    print("Testing saving and loading PreFlow...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Create test PreFlow
        preflow = create_test_preflow()
        preflow_id = preflow.id

        # Save PreFlow
        saved_id = storage.save_preflow(preflow)
        assert saved_id == preflow_id
        print(f"  PreFlow saved successfully: {saved_id}")

        # Load PreFlow
        loaded_preflow = storage.load_preflow(preflow_id)
        assert loaded_preflow is not None
        assert loaded_preflow.id == preflow_id
        assert loaded_preflow.name == preflow.name
        assert loaded_preflow.description == preflow.description
        print(f"  PreFlow loaded successfully: {loaded_preflow.name}")

        # Test loading non-existent PreFlow
        non_existent = storage.load_preflow("non-existent-id")
        assert non_existent is None
        print("  Non-existent PreFlow returns None [OK]")

        print("  PreFlow save and load test passed [OK]")


def test_save_and_load_psop():
    """Test saving and loading PSOP"""
    print("Testing saving and loading PSOP...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Create test PSOP
        psop = create_test_psop()
        psop_id = psop.id

        # Save PSOP
        saved_id = storage.save_psop(psop)
        assert saved_id == psop_id
        print(f"  PSOP saved successfully: {saved_id}")

        # Load PSOP
        loaded_psop = storage.load_psop(psop_id)
        assert loaded_psop is not None
        assert loaded_psop.id == psop_id
        assert loaded_psop.name == psop.name
        assert loaded_psop.description == psop.description
        assert len(loaded_psop.steps) == len(psop.steps)
        print(f"  PSOP loaded successfully: {loaded_psop.name}")

        # Test loading non-existent PSOP
        non_existent = storage.load_psop("non-existent-id")
        assert non_existent is None
        print("  Non-existent PSOP returns None [OK]")

    print("  PSOP save and load test passed [OK]")


def test_delete_workflows():
    """Test deleting workflows"""
    print("Testing deleting workflows...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Create and save test data
        preflow = create_test_preflow()
        psop = create_test_psop()

        storage.save_preflow(preflow)
        storage.save_psop(psop)

        # Test deleting PreFlow
        delete_result = storage.delete_preflow(preflow.id)
        assert delete_result is True
        print(f"  PreFlow deleted successfully: {preflow.id}")

        # Verify deleted
        loaded = storage.load_preflow(preflow.id)
        assert loaded is None

        # Test deleting PSOP
        delete_result = storage.delete_psop(psop.id)
        assert delete_result is True
        print(f"  PSOP deleted successfully: {psop.id}")

        # Verify deleted
        loaded = storage.load_psop(psop.id)
        assert loaded is None

        # Test deleting non-existent workflow
        delete_result = storage.delete_preflow("non-existent-id")
        assert delete_result is False
        print("  Deleting non-existent workflow returns False [OK]")

    print("  Workflow deletion test passed [OK]")


def test_list_workflows():
    """Test listing workflows"""
    print("Testing listing workflows...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Create and save multiple test data
        preflow1 = create_test_preflow("PreFlow 1", "Description 1")
        preflow2 = create_test_preflow("PreFlow 2", "Description 2")
        psop1 = create_test_psop("PSOP 1", "PSOP Description 1")
        psop2 = create_test_psop("PSOP 2", "PSOP Description 2")

        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)

        # List PreFlows
        preflow_list = storage.list_preflows()
        assert len(preflow_list) == 2
        assert preflow1.id in preflow_list
        assert preflow2.id in preflow_list
        print(f"  PreFlow list: {preflow_list}")

        # List PSOPs
        psop_list = storage.list_psops()
        assert len(psop_list) == 2
        assert psop1.id in psop_list
        assert psop2.id in psop_list
        print(f"  PSOP list: {psop_list}")

    print("  Workflow listing test passed [OK]")


def test_update_workflows():
    """Test updating workflows"""
    print("Testing updating workflows...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Create and save test PreFlow
        preflow = create_test_preflow("Original PreFlow", "Original description")
        storage.save_preflow(preflow)

        # Update PreFlow
        preflow.name = "Updated PreFlow"
        preflow.description = "Updated description"
        update_result = storage.update_preflow(preflow)
        assert update_result is True

        # Verify update
        loaded = storage.load_preflow(preflow.id)
        assert loaded is not None
        assert loaded.name == "Updated PreFlow"
        assert loaded.description == "Updated description"
        print(f"  PreFlow updated successfully: {loaded.name}")

        # Create and save test PSOP
        psop = create_test_psop("Original PSOP", "Original PSOP description")
        storage.save_psop(psop)

        # Update PSOP
        psop.name = "Updated PSOP"
        psop.description = "Updated PSOP description"
        update_result = storage.update_psop(psop)
        assert update_result is True

        # Verify update
        loaded = storage.load_psop(psop.id)
        assert loaded is not None
        assert loaded.name == "Updated PSOP"
        assert loaded.description == "Updated PSOP description"
        print(f"  PSOP updated successfully: {loaded.name}")

        # Test updating non-existent workflow
        non_existent_preflow = create_test_preflow("Non-existent", "Test")
        non_existent_preflow.id = "non-existent-id"
        update_result = storage.update_preflow(non_existent_preflow)
        assert update_result is False
        print("  Updating non-existent workflow returns False [OK]")

    print("  Workflow update test passed [OK]")


def test_retrieval_by_id():
    """Test retrieval by ID"""
    print("Testing retrieval by ID...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)

        # Create and save test data
        preflow = create_test_preflow("Test PreFlow", "Test description")
        psop = create_test_psop("Test PSOP", "Test PSOP description")

        storage.save_preflow(preflow)
        storage.save_psop(psop)

        # Retrieve PreFlow by ID
        retrieved_preflow = retrieval.get_preflow_by_id(preflow.id)
        assert retrieved_preflow is not None
        assert retrieved_preflow.id == preflow.id
        print(f"  PreFlow retrieved by ID: {retrieved_preflow.name}")

        # Retrieve PSOP by ID
        retrieved_psop = retrieval.get_psop_by_id(psop.id)
        assert retrieved_psop is not None
        assert retrieved_psop.id == psop.id
        print(f"  PSOP retrieved by ID: {retrieved_psop.name}")

        # Retrieve non-existent ID
        non_existent = retrieval.get_preflow_by_id("non-existent-id")
        assert non_existent is None
        print("  Retrieving non-existent ID returns None [OK]")

    print("  Retrieval by ID test passed [OK]")


def test_search_by_name():
    """Test search by name"""
    print("Testing search by name...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)

        # Create and save test data
        preflow1 = create_test_preflow("Energy Saving Process", "Energy saving description")
        preflow2 = create_test_preflow("Fault Diagnosis Process", "Fault diagnosis description")
        psop1 = create_test_psop("Energy Saving Process PSOP", "Energy saving PSOP")
        psop2 = create_test_psop("Backup Process PSOP", "Backup process PSOP")

        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)

        # Search for names containing "energy"
        results = retrieval.search_by_name("energy")
        assert len(results) == 2  # Should find preflow1 and psop1
        print(f"  Search 'energy' found {len(results)} results")

        # Search for names containing "process"
        results = retrieval.search_by_name("process")
        print(f"  Search 'process' found {len(results)} results")
        for r in results:
            print(f"    - {r.workflow_type}: {r.name}")
        # Should find preflow1, preflow2, psop1, psop2 (all 4 contain "process")
        assert len(results) == 4

        # Search only PSOP type
        results = retrieval.search_by_name("process", workflow_type="psop")
        assert len(results) == 2  # Should only find psop1 and psop2
        print(f"  Search PSOP type 'process' found {len(results)} results")

        # Search non-existent name
        results = retrieval.search_by_name("nonexistent")
        assert len(results) == 0
        print("  Searching non-existent name returns empty list [OK]")

    print("  Search by name test passed [OK]")


def test_search_by_tags():
    """Test search by tags"""
    print("Testing search by tags...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)

        # Create and save test data
        preflow1 = create_test_preflow("PreFlow 1", "Description 1")
        preflow1.tags = ["energy", "saving", "automation"]

        preflow2 = create_test_preflow("PreFlow 2", "Description 2")
        preflow2.tags = ["fault", "diagnosis", "automation"]

        psop1 = create_test_psop("PSOP 1", "Description 1")
        psop1.tags = ["energy", "backup", "test"]

        psop2 = create_test_psop("PSOP 2", "Description 2")
        psop2.tags = ["fault", "recovery", "test"]

        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)

        # Search for "automation" tag (any match)
        results = retrieval.search_by_tags(["automation"])
        assert len(results) == 2  # Should find preflow1 and preflow2
        print(f"  Search 'automation' tag found {len(results)} results")

        # Search for "test" tag
        results = retrieval.search_by_tags(["test"])
        assert len(results) == 2  # Should find psop1 and psop2
        print(f"  Search 'test' tag found {len(results)} results")

        # Search for "energy" or "test" tag (any match)
        results = retrieval.search_by_tags(["energy", "test"])
        assert len(results) == 3  # Should find preflow1, psop1, psop2
        print(f"  Search 'energy' or 'test' tag found {len(results)} results")

        # Search for both "energy" and "test" tags (match all)
        results = retrieval.search_by_tags(["energy", "test"], match_all=True)
        assert len(results) == 1  # Should only find psop1
        print(f"  Search both 'energy' and 'test' tags found {len(results)} results")

        # Search only PSOP type
        results = retrieval.search_by_tags(["test"], workflow_type="psop")
        assert len(results) == 2  # Should only find psop1 and psop2
        print(f"  Search PSOP type 'test' tag found {len(results)} results")

    print("  Search by tags test passed [OK]")


def test_search_by_description():
    """Test search by description"""
    print("Testing search by description...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)

        # Create and save test data
        preflow1 = create_test_preflow("PreFlow 1", "Energy saving process for data centers")
        preflow2 = create_test_preflow("PreFlow 2", "Fault diagnosis and recovery process")
        psop1 = create_test_psop("PSOP 1", "Automated energy saving process workflow")
        psop2 = create_test_psop("PSOP 2", "Backup and recovery process")

        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)

        # Search descriptions containing "process"
        results = retrieval.search_by_description("process")
        assert len(results) == 4  # All 4 have "process"
        print(f"  Search 'process' in descriptions found {len(results)} results")

        # Search descriptions containing "energy"
        results = retrieval.search_by_description("energy")
        assert len(results) == 2  # Should find preflow1 and psop1
        print(f"  Search 'energy' in descriptions found {len(results)} results")

        # Search only PreFlow type
        results = retrieval.search_by_description("process", workflow_type="preflow")
        assert len(results) == 2  # Should only find preflow1 and preflow2
        print(f"  Search PreFlow type 'process' in descriptions found {len(results)} results")

        # Search non-existent keyword
        results = retrieval.search_by_description("nonexistent")
        assert len(results) == 0
        print("  Searching non-existent description returns empty list [OK]")

    print("  Search by description test passed [OK]")


def test_list_recent_workflows():
    """Test listing recent workflows"""
    print("Testing listing recent workflows...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)

        # Create and save test data
        preflow1 = create_test_preflow("PreFlow 1", "Description 1")
        preflow2 = create_test_preflow("PreFlow 2", "Description 2")
        psop1 = create_test_psop("PSOP 1", "Description 1")
        psop2 = create_test_psop("PSOP 2", "Description 2")

        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)

        # List all recent workflows
        results = retrieval.list_recent_workflows(limit=10)
        assert len(results) == 4
        print(f"  Listing all recent workflows: {len(results)} results")

        # Limit results
        results = retrieval.list_recent_workflows(limit=2)
        assert len(results) == 2
        print(f"  Limit to 2 recent workflows: {len(results)} results")

        # List only PSOP type
        results = retrieval.list_recent_workflows(workflow_type="psop")
        assert len(results) == 2
        assert all(r.workflow_type == "psop" for r in results)
        print(f"  Listing only PSOP type: {len(results)} results")

        # List only PreFlow type
        results = retrieval.list_recent_workflows(workflow_type="preflow")
        assert len(results) == 2
        assert all(r.workflow_type == "preflow" for r in results)
        print(f"  Listing only PreFlow type: {len(results)} results")

    print("  List recent workflows test passed [OK]")


def test_workflow_search_result():
    """Test WorkflowSearchResult class"""
    print("Testing WorkflowSearchResult class...")

    # Create test data
    created_at = datetime.now()
    result = WorkflowSearchResult(
        workflow_id="test-id-123",
        workflow_type="psop",
        name="Test Workflow",
        description="Test description",
        tags=["test", "unit"],
        created_at=created_at,
        score=0.85
    )

    # Test properties
    assert result.workflow_id == "test-id-123"
    assert result.workflow_type == "psop"
    assert result.name == "Test Workflow"
    assert result.description == "Test description"
    assert result.tags == ["test", "unit"]
    assert result.created_at == created_at
    assert result.score == 0.85

    # Test to_dict method
    result_dict = result.to_dict()
    assert result_dict["workflow_id"] == "test-id-123"
    assert result_dict["workflow_type"] == "psop"
    assert result_dict["name"] == "Test Workflow"
    assert result_dict["description"] == "Test description"
    assert result_dict["tags"] == ["test", "unit"]
    assert "created_at" in result_dict
    assert result_dict["score"] == 0.85

    print(f"  WorkflowSearchResult created successfully: {result.name}")
    print(f"  Dict representation: {result_dict}")

    print("  WorkflowSearchResult test passed [OK]")


def test_error_handling():
    """Test error handling"""
    print("Testing error handling...")

    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)

        # Test invalid file path
        try:
            # Try to use invalid workflow type
            storage._get_file_path("test-id", "invalid-type")
            assert False, "Should raise WorkflowStorageError"
        except WorkflowStorageError as e:
            print(f"  Invalid workflow type error handling: {e}")
            assert "Unknown workflow type" in str(e)

        # Test save error (simulate permission error)
        # Create a read-only directory to test save error
        read_only_dir = os.path.join(temp_dir, "readonly")
        os.makedirs(read_only_dir)

        # Set read-only attribute on Windows
        if os.name == 'nt':
            import stat
            os.chmod(read_only_dir, stat.S_IREAD)

        try:
            readonly_storage = WorkflowStorage(storage_dir=read_only_dir)
            psop = create_test_psop()
            readonly_storage.save_psop(psop)
            print("  Note: On Windows, may not be able to create a truly read-only directory for testing")
        except Exception as e:
            print(f"  Save error handling: {e}")

    print("  Error handling test completed [OK]")


def main():
    """Main test function"""
    print("=" * 60)
    print("Starting Persistence and Retrieval module tests")
    print("=" * 60)

    try:
        # Run all tests
        test_storage_initialization()
        print()

        test_save_and_load_preflow()
        print()

        test_save_and_load_psop()
        print()

        test_delete_workflows()
        print()

        test_list_workflows()
        print()

        test_update_workflows()
        print()

        test_retrieval_by_id()
        print()

        test_search_by_name()
        print()

        test_search_by_tags()
        print()

        test_search_by_description()
        print()

        test_list_recent_workflows()
        print()

        test_workflow_search_result()
        print()

        test_error_handling()
        print()

        print("=" * 60)
        print("All tests passed! [OK]")
        print("=" * 60)

    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
