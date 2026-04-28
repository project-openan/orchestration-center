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
Persistence和Retrieval模块测试脚本
测试framework/core/persistence.py和retrieval.py的功能
"""

import sys
import os
import tempfile
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP, Task, TaskStatus, Step, StepType, JumpCondition
from orchestrate.core.persistence import WorkflowStorage, WorkflowStorageError
from orchestrate.core.retrieval import WorkflowRetrieval, WorkflowSearchResult


def create_test_preflow(name: str = "Test PreFlow", description: str = "Test description") -> PreFlow:
    """创建测试用的PreFlow对象"""
    return PreFlow(
        name=name,
        description=description,
        steps_md="# Test Process\n\nThis is a test process for unit testing.",
        tags=["test", "unit-test", "automation"]
    )


def create_test_psop(name: str = "Test PSOP", description: str = "Test PSOP description") -> PSOP:
    """创建测试用的PSOP对象"""
    # 创建任务
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
    
    # 创建步骤
    step1 = Step(
        name="analysis_step",
        type=StepType.ALL_SUCCESS,
        subtasks=[task1, task2],
        next=None  # 添加next参数
    )
    
    # 创建PSOP
    return PSOP(
        name=name,
        description=description,
        steps=[step1],
        tags=["test", "psop-test", "automation"],
        related_preflow="test_preflow_123",
        user_intent="Test user intent for unit testing"  # 添加user_intent参数
    )


def test_storage_initialization():
    """测试存储初始化"""
    print("测试存储初始化...")
    
    # 测试默认存储目录
    storage = WorkflowStorage()
    print(f"  PSOP目录: {storage.psop_dir}")
    print(f"  PreFlow目录: {storage.preflow_dir}")
    
    # 测试自定义存储目录
    with tempfile.TemporaryDirectory() as temp_dir:
        custom_storage = WorkflowStorage(storage_dir=temp_dir)
        print(f"  自定义PSOP目录: {custom_storage.psop_dir}")
        print(f"  自定义PreFlow目录: {custom_storage.preflow_dir}")
        
        # 验证目录已创建
        assert custom_storage.psop_dir.exists()
        assert custom_storage.preflow_dir.exists()
    
        print("  存储初始化测试通过 [OK]")


def test_save_and_load_preflow():
    """测试保存和加载PreFlow"""
    print("测试保存和加载PreFlow...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 创建测试PreFlow
        preflow = create_test_preflow()
        preflow_id = preflow.id
        
        # 保存PreFlow
        saved_id = storage.save_preflow(preflow)
        assert saved_id == preflow_id
        print(f"  PreFlow保存成功: {saved_id}")
        
        # 加载PreFlow
        loaded_preflow = storage.load_preflow(preflow_id)
        assert loaded_preflow is not None
        assert loaded_preflow.id == preflow_id
        assert loaded_preflow.name == preflow.name
        assert loaded_preflow.description == preflow.description
        print(f"  PreFlow加载成功: {loaded_preflow.name}")
        
        # 测试加载不存在的PreFlow
        non_existent = storage.load_preflow("non-existent-id")
        assert non_existent is None
        print("  不存在的PreFlow返回None [OK]")
    
        print("  PreFlow保存和加载测试通过 [OK]")


def test_save_and_load_psop():
    """测试保存和加载PSOP"""
    print("测试保存和加载PSOP...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 创建测试PSOP
        psop = create_test_psop()
        psop_id = psop.id
        
        # 保存PSOP
        saved_id = storage.save_psop(psop)
        assert saved_id == psop_id
        print(f"  PSOP保存成功: {saved_id}")
        
        # 加载PSOP
        loaded_psop = storage.load_psop(psop_id)
        assert loaded_psop is not None
        assert loaded_psop.id == psop_id
        assert loaded_psop.name == psop.name
        assert loaded_psop.description == psop.description
        assert len(loaded_psop.steps) == len(psop.steps)
        print(f"  PSOP加载成功: {loaded_psop.name}")
        
        # 测试加载不存在的PSOP
        non_existent = storage.load_psop("non-existent-id")
        assert non_existent is None
        print("  不存在的PSOP返回None [OK]")
    
    print("  PSOP保存和加载测试通过 [OK]")


def test_delete_workflows():
    """测试删除工作流"""
    print("测试删除工作流...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 创建并保存测试数据
        preflow = create_test_preflow()
        psop = create_test_psop()
        
        storage.save_preflow(preflow)
        storage.save_psop(psop)
        
        # 测试删除PreFlow
        delete_result = storage.delete_preflow(preflow.id)
        assert delete_result is True
        print(f"  PreFlow删除成功: {preflow.id}")
        
        # 验证已删除
        loaded = storage.load_preflow(preflow.id)
        assert loaded is None
        
        # 测试删除PSOP
        delete_result = storage.delete_psop(psop.id)
        assert delete_result is True
        print(f"  PSOP删除成功: {psop.id}")
        
        # 验证已删除
        loaded = storage.load_psop(psop.id)
        assert loaded is None
        
        # 测试删除不存在的workflow
        delete_result = storage.delete_preflow("non-existent-id")
        assert delete_result is False
        print("  删除不存在的workflow返回False [OK]")
    
    print("  工作流删除测试通过 [OK]")


def test_list_workflows():
    """测试列出工作流"""
    print("测试列出工作流...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 创建并保存多个测试数据
        preflow1 = create_test_preflow("PreFlow 1", "Description 1")
        preflow2 = create_test_preflow("PreFlow 2", "Description 2")
        psop1 = create_test_psop("PSOP 1", "PSOP Description 1")
        psop2 = create_test_psop("PSOP 2", "PSOP Description 2")
        
        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)
        
        # 列出PreFlows
        preflow_list = storage.list_preflows()
        assert len(preflow_list) == 2
        assert preflow1.id in preflow_list
        assert preflow2.id in preflow_list
        print(f"  PreFlow列表: {preflow_list}")
        
        # 列出PSOPs
        psop_list = storage.list_psops()
        assert len(psop_list) == 2
        assert psop1.id in psop_list
        assert psop2.id in psop_list
        print(f"  PSOP列表: {psop_list}")
    
    print("  工作流列表测试通过 [OK]")


def test_update_workflows():
    """测试更新工作流"""
    print("测试更新工作流...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 创建并保存测试PreFlow
        preflow = create_test_preflow("Original PreFlow", "Original description")
        storage.save_preflow(preflow)
        
        # 更新PreFlow
        preflow.name = "Updated PreFlow"
        preflow.description = "Updated description"
        update_result = storage.update_preflow(preflow)
        assert update_result is True
        
        # 验证更新
        loaded = storage.load_preflow(preflow.id)
        assert loaded is not None
        assert loaded.name == "Updated PreFlow"
        assert loaded.description == "Updated description"
        print(f"  PreFlow更新成功: {loaded.name}")
        
        # 创建并保存测试PSOP
        psop = create_test_psop("Original PSOP", "Original PSOP description")
        storage.save_psop(psop)
        
        # 更新PSOP
        psop.name = "Updated PSOP"
        psop.description = "Updated PSOP description"
        update_result = storage.update_psop(psop)
        assert update_result is True
        
        # 验证更新
        loaded = storage.load_psop(psop.id)
        assert loaded is not None
        assert loaded.name == "Updated PSOP"
        assert loaded.description == "Updated PSOP description"
        print(f"  PSOP更新成功: {loaded.name}")
        
        # 测试更新不存在的workflow
        non_existent_preflow = create_test_preflow("Non-existent", "Test")
        non_existent_preflow.id = "non-existent-id"
        update_result = storage.update_preflow(non_existent_preflow)
        assert update_result is False
        print("  更新不存在的workflow返回False [OK]")
    
    print("  工作流更新测试通过 [OK]")


def test_retrieval_by_id():
    """测试按ID检索"""
    print("测试按ID检索...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)
        
        # 创建并保存测试数据
        preflow = create_test_preflow("Test PreFlow", "Test description")
        psop = create_test_psop("Test PSOP", "Test PSOP description")
        
        storage.save_preflow(preflow)
        storage.save_psop(psop)
        
        # 按ID检索PreFlow
        retrieved_preflow = retrieval.get_preflow_by_id(preflow.id)
        assert retrieved_preflow is not None
        assert retrieved_preflow.id == preflow.id
        print(f"  PreFlow按ID检索成功: {retrieved_preflow.name}")
        
        # 按ID检索PSOP
        retrieved_psop = retrieval.get_psop_by_id(psop.id)
        assert retrieved_psop is not None
        assert retrieved_psop.id == psop.id
        print(f"  PSOP按ID检索成功: {retrieved_psop.name}")
        
        # 检索不存在的ID
        non_existent = retrieval.get_preflow_by_id("non-existent-id")
        assert non_existent is None
        print("  检索不存在的ID返回None [OK]")
    
    print("  按ID检索测试通过 [OK]")


def test_search_by_name():
    """测试按名称搜索"""
    print("测试按名称搜索...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)
        
        # 创建并保存测试数据
        preflow1 = create_test_preflow("Energy Saving Process", "Energy saving description")
        preflow2 = create_test_preflow("Fault Diagnosis Process", "Fault diagnosis description")
        psop1 = create_test_psop("Energy Saving Process PSOP", "Energy saving PSOP")
        psop2 = create_test_psop("Backup Process PSOP", "Backup process PSOP")
        
        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)
        
        # 搜索包含"energy"的名称
        results = retrieval.search_by_name("energy")
        assert len(results) == 2  # 应该找到preflow1和psop1
        print(f"  搜索'energy'找到 {len(results)} 个结果")
        
        # 搜索包含"process"的名称
        results = retrieval.search_by_name("process")
        print(f"  搜索'process'找到 {len(results)} 个结果")
        for r in results:
            print(f"    - {r.workflow_type}: {r.name}")
        # 应该找到preflow1, preflow2, psop1, psop2 (所有4个都包含"process")
        assert len(results) == 4
        
        # 只搜索PSOP类型
        results = retrieval.search_by_name("process", workflow_type="psop")
        assert len(results) == 2  # 应该只找到psop1和psop2
        print(f"  只搜索PSOP类型'process'找到 {len(results)} 个结果")
        
        # 搜索不存在的名称
        results = retrieval.search_by_name("nonexistent")
        assert len(results) == 0
        print("  搜索不存在的名称返回空列表 [OK]")
    
    print("  按名称搜索测试通过 [OK]")


def test_search_by_tags():
    """测试按标签搜索"""
    print("测试按标签搜索...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)
        
        # 创建并保存测试数据
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
        
        # 搜索包含"automation"标签的（任意匹配）
        results = retrieval.search_by_tags(["automation"])
        assert len(results) == 2  # 应该找到preflow1和preflow2
        print(f"  搜索'automation'标签找到 {len(results)} 个结果")
        
        # 搜索包含"test"标签的
        results = retrieval.search_by_tags(["test"])
        assert len(results) == 2  # 应该找到psop1和psop2
        print(f"  搜索'test'标签找到 {len(results)} 个结果")
        
        # 搜索同时包含"energy"和"test"标签的（任意匹配）
        results = retrieval.search_by_tags(["energy", "test"])
        assert len(results) == 3  # 应该找到preflow1, psop1, psop2
        print(f"  搜索'energy'或'test'标签找到 {len(results)} 个结果")
        
        # 搜索同时包含"energy"和"test"标签的（全部匹配）
        results = retrieval.search_by_tags(["energy", "test"], match_all=True)
        assert len(results) == 1  # 应该只找到psop1
        print(f"  搜索同时包含'energy'和'test'标签找到 {len(results)} 个结果")
        
        # 只搜索PSOP类型
        results = retrieval.search_by_tags(["test"], workflow_type="psop")
        assert len(results) == 2  # 应该只找到psop1和psop2
        print(f"  只搜索PSOP类型'test'标签找到 {len(results)} 个结果")
    
    print("  按标签搜索测试通过 [OK]")


def test_search_by_description():
    """测试按描述搜索"""
    print("测试按描述搜索...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)
        
        # 创建并保存测试数据
        preflow1 = create_test_preflow("PreFlow 1", "Energy saving process for data centers")
        preflow2 = create_test_preflow("PreFlow 2", "Fault diagnosis and recovery process")
        psop1 = create_test_psop("PSOP 1", "Automated energy saving process workflow")
        psop2 = create_test_psop("PSOP 2", "Backup and recovery process")
        
        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)
        
        # 搜索包含"process"的描述
        results = retrieval.search_by_description("process")
        assert len(results) == 4  # 所有4个都有"process"
        print(f"  搜索'process'描述找到 {len(results)} 个结果")
        
        # 搜索包含"energy"的描述
        results = retrieval.search_by_description("energy")
        assert len(results) == 2  # 应该找到preflow1和psop1
        print(f"  搜索'energy'描述找到 {len(results)} 个结果")
        
        # 只搜索PreFlow类型
        results = retrieval.search_by_description("process", workflow_type="preflow")
        assert len(results) == 2  # 应该只找到preflow1和preflow2
        print(f"  只搜索PreFlow类型'process'描述找到 {len(results)} 个结果")
        
        # 搜索不存在的关键词
        results = retrieval.search_by_description("nonexistent")
        assert len(results) == 0
        print("  搜索不存在的描述返回空列表 [OK]")
    
    print("  按描述搜索测试通过 [OK]")


def test_list_recent_workflows():
    """测试列出最近的工作流"""
    print("测试列出最近的工作流...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        retrieval = WorkflowRetrieval(storage)
        
        # 创建并保存测试数据
        preflow1 = create_test_preflow("PreFlow 1", "Description 1")
        preflow2 = create_test_preflow("PreFlow 2", "Description 2")
        psop1 = create_test_psop("PSOP 1", "Description 1")
        psop2 = create_test_psop("PSOP 2", "Description 2")
        
        storage.save_preflow(preflow1)
        storage.save_preflow(preflow2)
        storage.save_psop(psop1)
        storage.save_psop(psop2)
        
        # 列出所有最近的工作流
        results = retrieval.list_recent_workflows(limit=10)
        assert len(results) == 4
        print(f"  列出所有最近工作流: {len(results)} 个结果")
        
        # 限制数量
        results = retrieval.list_recent_workflows(limit=2)
        assert len(results) == 2
        print(f"  限制2个最近工作流: {len(results)} 个结果")
        
        # 只列出PSOP类型
        results = retrieval.list_recent_workflows(workflow_type="psop")
        assert len(results) == 2
        assert all(r.workflow_type == "psop" for r in results)
        print(f"  只列出PSOP类型: {len(results)} 个结果")
        
        # 只列出PreFlow类型
        results = retrieval.list_recent_workflows(workflow_type="preflow")
        assert len(results) == 2
        assert all(r.workflow_type == "preflow" for r in results)
        print(f"  只列出PreFlow类型: {len(results)} 个结果")
    
    print("  列出最近工作流测试通过 [OK]")


def test_workflow_search_result():
    """测试WorkflowSearchResult类"""
    print("测试WorkflowSearchResult类...")
    
    # 创建测试数据
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
    
    # 测试属性
    assert result.workflow_id == "test-id-123"
    assert result.workflow_type == "psop"
    assert result.name == "Test Workflow"
    assert result.description == "Test description"
    assert result.tags == ["test", "unit"]
    assert result.created_at == created_at
    assert result.score == 0.85
    
    # 测试to_dict方法
    result_dict = result.to_dict()
    assert result_dict["workflow_id"] == "test-id-123"
    assert result_dict["workflow_type"] == "psop"
    assert result_dict["name"] == "Test Workflow"
    assert result_dict["description"] == "Test description"
    assert result_dict["tags"] == ["test", "unit"]
    assert "created_at" in result_dict
    assert result_dict["score"] == 0.85
    
    print(f"  WorkflowSearchResult创建成功: {result.name}")
    print(f"  字典表示: {result_dict}")
    
    print("  WorkflowSearchResult测试通过 [OK]")


def test_error_handling():
    """测试错误处理"""
    print("测试错误处理...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        storage = WorkflowStorage(storage_dir=temp_dir)
        
        # 测试无效的文件路径
        try:
            # 尝试使用无效的workflow类型
            storage._get_file_path("test-id", "invalid-type")
            assert False, "应该抛出WorkflowStorageError"
        except WorkflowStorageError as e:
            print(f"  无效workflow类型错误处理: {e}")
            assert "Unknown workflow type" in str(e)
        
        # 测试保存时出错（模拟权限错误）
        # 创建一个只读目录来测试保存错误
        read_only_dir = os.path.join(temp_dir, "readonly")
        os.makedirs(read_only_dir)
        
        # 在Windows上设置只读属性
        if os.name == 'nt':
            import stat
            os.chmod(read_only_dir, stat.S_IREAD)
        
        try:
            readonly_storage = WorkflowStorage(storage_dir=read_only_dir)
            psop = create_test_psop()
            readonly_storage.save_psop(psop)
            print("  注意: 在Windows上可能无法创建真正的只读目录进行测试")
        except Exception as e:
            print(f"  保存错误处理: {e}")
    
    print("  错误处理测试完成 [OK]")


def main():
    """主测试函数"""
    print("=" * 60)
    print("开始测试Persistence和Retrieval模块")
    print("=" * 60)
    
    try:
        # 运行所有测试
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
        print("所有测试通过！ [OK]")
        print("=" * 60)
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())