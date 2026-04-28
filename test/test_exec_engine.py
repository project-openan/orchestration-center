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

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

# 待测试模块导入
from orchestrate.runtime.exec_engine import DynamicWorkflowEngine
from orchestrate.core.model.psop import (
    PSOP, Step, Task, TaskStatus, StepType, JumpCondition
)


@pytest.fixture
def mock_agent_card():
    """模拟 Agent Card 对象"""
    card = MagicMock()
    card.name = "test_agent"
    card.capabilities = MagicMock()
    card.capabilities.streaming = False
    card.url = "http://test-agent:8000"
    return card


@pytest.fixture
def mock_llm_client():
    """模拟 LLM 客户端，返回格式: (request_id, response_text)"""
    client = MagicMock()
    client.ask_llm = MagicMock(return_value=("mock_req_id", "step2"))
    return client


@pytest.fixture
def sample_task():
    """创建标准测试 Task"""
    return Task(
        description="Test energy saving analysis",
        agent="energy_agent",
        skill="best_effort_energy_saving"
    )


@pytest.fixture
def sample_step(sample_task):
    """创建标准测试 Step"""
    return Step(
        name="step1",
        type=StepType.ALL_SUCCESS,
        subtasks=[sample_task],
        next=[JumpCondition(step="step2", condition="energy saving success")]
    )


@pytest.fixture
def sample_psop(sample_step):
    """创建标准测试 PSOP"""
    return PSOP(
        name="test_workflow",
        description="Test workflow for unit testing",
        steps=[
            sample_step,
            Step(
                name="step2",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=None
            )
        ]
    )


@pytest.fixture
def mock_httpx_client():
    """模拟 httpx AsyncClient"""
    client = AsyncMock()
    client.timeout = MagicMock()
    return client


@pytest.fixture
def mock_a2a_response_task():
    """模拟 A2A 响应中的 task 对象"""
    task = MagicMock()
    task.artifacts = [MagicMock()]
    task.model_dump_json = MagicMock(return_value='{"content":"mock response"}')
    return task


class TestEngineInitialization:
    """测试引擎初始化相关功能"""

    def test_init_basic(self, sample_psop, mock_agent_card, mock_llm_client):
        """测试基础初始化"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            assert engine.workflow == sample_psop
            assert engine.current_step_idx == 0
            assert engine.execution_history == []
            assert engine.push_callback is None
            assert engine.llm_client == mock_llm_client

    def test_set_push_callback(self, sample_psop, mock_agent_card, mock_llm_client):
        """测试回调函数设置"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            callback = MagicMock()
            engine.set_push_callback(callback)

            assert engine.push_callback == callback

    def test_push_event_with_callback(self, sample_psop, mock_agent_card, mock_llm_client):
        """测试事件推送成功调用回调"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            callback = MagicMock()
            engine.set_push_callback(callback)

            engine._push_event("test_event", {"key": "value"})

            callback.assert_called_once_with("test_event", {"key": "value"})

    def test_push_event_callback_exception_handled(self, sample_psop, mock_agent_card, mock_llm_client, caplog):
        """测试回调异常时被捕获不影响主流程"""
        import logging
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            def bad_callback(*args, **kwargs):
                raise RuntimeError("Callback failed")

            engine.set_push_callback(bad_callback)

            # 不应抛出异常
            engine._push_event("test_event", {"key": "value"})


class TestExecuteSubtasks:
    """测试 _execute_subtasks 方法"""

    @pytest.mark.asyncio
    async def test_execute_subtasks_success(self, sample_step, mock_agent_card, mock_llm_client):
        """测试子任务执行成功"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])
            engine.send_message_to_agent = AsyncMock(return_value="Success output")

            results, success = await engine._execute_subtasks(sample_step)

            assert success is True
            assert sample_step.subtasks[0].status == TaskStatus.SUCCESS
            assert "Test energy saving analysis" in results
            assert results["Test energy saving analysis"] == "Success output"
            assert len(engine.execution_history) == 1
            assert engine.execution_history[0]["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_execute_subtasks_failure(self, sample_step, mock_agent_card, mock_llm_client):
        """测试子任务执行失败"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])
            engine.send_message_to_agent = AsyncMock(side_effect=RuntimeError("Connection failed"))

            results, success = await engine._execute_subtasks(sample_step)

            assert success is False
            assert sample_step.subtasks[0].status == TaskStatus.FAILED
            assert len(engine.execution_history) == 1
            assert engine.execution_history[0]["status"] == "FAILED"
            assert "Connection failed" in engine.execution_history[0]["output"]

    @pytest.mark.asyncio
    async def test_execute_subtasks_multiple_tasks_all_success(self, mock_agent_card, mock_llm_client):
        """测试多个子任务全部成功"""
        step = Step(
            name="multi_step",
            type=StepType.ALL_SUCCESS,
            subtasks=[
                Task(description="Task A", agent="agent1", skill="skill_a"),
                Task(description="Task B", agent="agent2", skill="skill_b"),
            ],
            next=None
        )

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])
            engine.send_message_to_agent = AsyncMock(side_effect=lambda agent, desc: f"OK-{desc}")

            results, success = await engine._execute_subtasks(step)

            assert success is True
            assert all(t.status == TaskStatus.SUCCESS for t in step.subtasks)
            assert len(results) == 2
            assert "Task A" in results and "Task B" in results

    @pytest.mark.asyncio
    async def test_execute_subtasks_push_psop_update(self, sample_step, mock_agent_card, mock_llm_client):
        """测试执行时推送 PSOP 状态更新"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.model_dump_json = MagicMock(return_value='{"mock":"psop"}')
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])
            engine.send_message_to_agent = AsyncMock(return_value="OK")

            callback = MagicMock()
            engine.set_push_callback(callback)

            await engine._execute_subtasks(sample_step)

            # 验证推送了 psop_update 事件
            callback.assert_called()
            event_types = [call_args[0][0] for call_args in callback.call_args_list]
            assert "psop_update" in event_types


class TestLLMRouteDecision:
    """测试 _llm_route_decision 方法"""

    @pytest.mark.asyncio
    async def test_llm_decision_jump_to_next(self, sample_step, mock_llm_client):
        """测试 LLM 决定跳转到下一步"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step, Step(
                name="step2",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=[JumpCondition(step="end", condition="energy saving success")]
            )]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            mock_llm_client.ask_llm.return_value = ("id", "step2")

            result = engine._llm_route_decision(
                sample_step,
                {"test_skill": "execution success"}
            )

            assert result == "step2"
            mock_llm_client.ask_llm.assert_called_once()
            # 验证 prompt 包含关键信息
            prompt = mock_llm_client.ask_llm.call_args[0][0]
            assert "Current context" in prompt
            assert "Execution Result" in prompt

    @pytest.mark.asyncio
    async def test_llm_decision_end_on_error(self, sample_step, mock_llm_client):
        """测试执行错误时 LLM 决定结束"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            mock_llm_client.ask_llm.return_value = ("id", "end")

            result = engine._llm_route_decision(
                sample_step,
                {"test_skill": {"error": "Agent timeout"}}
            )

            assert result == "end"
            # 验证 prompt 包含错误信息
            prompt = mock_llm_client.ask_llm.call_args[0][0]
            assert "执行失败" in prompt

    @pytest.mark.asyncio
    async def test_llm_decision_retry(self, sample_step, mock_llm_client):
        """测试 LLM 决定重试"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            mock_llm_client.ask_llm.return_value = ("id", "retry")

            result = engine._llm_route_decision(sample_step, {"skill": "ambiguous result"})

            assert result == "retry"

    @pytest.mark.asyncio
    async def test_llm_decision_invalid_step_name(self, sample_step, mock_llm_client):
        """测试 LLM 返回非法步骤名时默认结束"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            mock_llm_client.ask_llm.return_value = ("id", "nonexistent_step")

            result = engine._llm_route_decision(sample_step, {"skill": "success"})

            assert result == "end"

    @pytest.mark.asyncio
    async def test_llm_decision_case_insensitive(self, sample_step, mock_llm_client):
        """测试决策结果大小写不敏感"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step, Step(
                name="step2",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=[JumpCondition(step="end", condition="energy saving success")]
            )]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            # LLM 返回大写
            mock_llm_client.ask_llm.return_value = ("id", "STEP2")

            result = engine._llm_route_decision(sample_step, {"skill": "success"})

            assert result == "STEP2"  # 返回原始值，但内部比较时转小写

    @pytest.mark.asyncio
    async def test_llm_decision_llm_call_failure(self, sample_step):
        """测试 LLM 调用失败时的容错"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("LLM service down")

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm):
            engine = DynamicWorkflowEngine(psop=MagicMock(steps=[sample_step]), agent_cards=[])

            result = engine._llm_route_decision(sample_step, {"skill": "success"})

            assert result == "end"

    @pytest.mark.asyncio
    async def test_llm_decision_no_llm_client(self, sample_step):
        """测试未初始化 LLM 客户端时抛出异常"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=None):
            engine = DynamicWorkflowEngine(psop=MagicMock(steps=[sample_step]), agent_cards=[])
            engine.llm_client = None

            with pytest.raises(ValueError, match="LLM Client not initialized"):
                engine._llm_route_decision(sample_step, {"skill": "success"})

    @pytest.mark.asyncio
    async def test_llm_decision_prompt_contains_conditions(self, sample_step, mock_llm_client):
        """测试 prompt 正确包含跳转条件"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            engine._llm_route_decision(sample_step, {"skill": "result"})

            prompt = mock_llm_client.ask_llm.call_args[0][0]
            # 验证条件以 JSON 格式包含在 prompt 中
            assert "step2" in prompt
            assert "energy saving success" in prompt


class TestExecuteSingleStep:
    """测试 _execute_single_step 方法"""

    @pytest.mark.asyncio
    async def test_execute_step_success_flow(self, sample_step, mock_agent_card, mock_llm_client):
        """测试步骤成功执行并跳转"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step, Step(
                name="step2",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=[JumpCondition(step="end", condition="energy saving success")]
            )]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])

            engine._execute_subtasks = AsyncMock(return_value=({"task": "ok"}, True))
            engine._process_llm_decision = AsyncMock()

            await engine._execute_single_step()

            engine._execute_subtasks.assert_called_once_with(sample_step)
            engine._process_llm_decision.assert_called_once_with(
                sample_step, {"task": "ok"}
            )

    @pytest.mark.asyncio
    async def test_execute_step_failure_stops_flow(self, sample_step, mock_agent_card, mock_llm_client):
        """测试步骤失败时流程停止"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])

            engine._execute_subtasks = AsyncMock(return_value=({"task": "error"}, False))
            engine._record_stop_event = MagicMock()

            await engine._execute_single_step()

            # 验证流程被终止
            assert engine.current_step_idx == len(psop.steps)
            engine._record_stop_event.assert_called_once()


class TestFindStepIndex:
    """测试 _find_step_index 方法"""

    def test_find_existing_step(self, sample_psop, mock_llm_client):
        """测试找到存在的步骤"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("step2")
            assert idx == 1

    def test_find_first_step(self, sample_psop, mock_llm_client):
        """测试找到第一个步骤"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("step1")
            assert idx == 0

    def test_find_nonexistent_step(self, sample_psop, mock_llm_client):
        """测试查找不存在的步骤"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("nonexistent")
            assert idx is None

    def test_find_step_empty_psop(self, mock_llm_client):
        """测试空 PSOP 的步骤查找"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            empty_psop = PSOP(name="empty", steps=[])
            engine = DynamicWorkflowEngine(psop=empty_psop, agent_cards=[])

            idx = engine._find_step_index("any_step")
            assert idx is None


class TestRecordStopEvent:
    """测试 _record_stop_event 方法"""

    def test_record_stop_event(self, sample_psop, mock_llm_client):
        """测试停止事件正确记录"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            engine._record_stop_event("Timeout", {"detail": "max retries exceeded"})

            assert len(engine.execution_history) == 1
            event = engine.execution_history[0]
            assert event["event"] == "STOPPED"
            assert event["reason"] == "Timeout"
            assert event["details"] == {"detail": "max retries exceeded"}

    def test_record_multiple_stop_events(self, sample_psop, mock_llm_client):
        """测试多次记录停止事件"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            engine._record_stop_event("Error1", {"code": 1})
            engine._record_stop_event("Error2", {"code": 2})

            assert len(engine.execution_history) == 2
            assert engine.execution_history[0]["reason"] == "Error1"
            assert engine.execution_history[1]["reason"] == "Error2"


class TestSendMessageToAgent:
    """测试 send_message_to_agent 方法"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_agent_card, mock_llm_client, mock_a2a_response_task):
        """测试成功发送消息并接收响应"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient') as mock_client_cls, \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory, \
                    patch('orchestrate.runtime.exec_engine.get_message_text',
                          return_value="Agent response text"):
                mock_client_instance = AsyncMock()
                mock_client_cls.return_value = mock_client_instance

                mock_a2a_client = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a_client

                async def mock_stream(request):
                    yield (mock_a2a_response_task, {})

                mock_a2a_client.send_message = mock_stream

                result = await engine.send_message_to_agent(
                    "test_agent",
                    "Test task description"
                )

                assert result == "Agent response text"

    @pytest.mark.asyncio
    async def test_send_message_agent_not_found(self, mock_llm_client):
        """测试 Agent 未找到时抛出异常"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])

            with pytest.raises(RuntimeError, match="未找到Agent"):
                await engine.send_message_to_agent("nonexistent_agent", "task")

    @pytest.mark.asyncio
    async def test_send_message_timeout(self, mock_agent_card, mock_llm_client):
        """测试超时异常处理"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_factory.return_value.create.return_value.send_message.side_effect = \
                    httpx.TimeoutException("Request timed out")

                with pytest.raises(RuntimeError, match="timed out"):
                    await engine.send_message_to_agent("test_agent", "task")

    @pytest.mark.asyncio
    async def test_send_message_connect_error(self, mock_agent_card, mock_llm_client):
        """测试连接错误处理"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_factory.return_value.create.return_value.send_message.side_effect = \
                    httpx.ConnectError("Connection refused")

                with pytest.raises(RuntimeError, match="Faild to connect"):
                    await engine.send_message_to_agent("test_agent", "task")

    @pytest.mark.asyncio
    async def test_send_message_push_events(self, mock_agent_card, mock_llm_client, mock_a2a_response_task):
        """测试通信时事件推送"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            callback = MagicMock()
            engine.set_push_callback(callback)

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory, \
                    patch('orchestrate.runtime.exec_engine.get_message_text',
                          return_value="response"):
                mock_a2a = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a

                async def mock_stream(request):
                    yield (mock_a2a_response_task, {})

                mock_a2a.send_message = mock_stream

                await engine.send_message_to_agent("test_agent", "test task")

                event_types = [call_args[0][0] for call_args in callback.call_args_list]
                assert "agent_request" in event_types
                assert "agent_response" in event_types

    @pytest.mark.asyncio
    async def test_send_message_no_artifacts_fallback(self, mock_agent_card, mock_llm_client):
        """测试无 artifacts 时的降级处理"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_a2a = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a

                # 模拟 task 无 artifacts
                mock_task = MagicMock()
                mock_task.artifacts = None
                mock_task.__str__ = MagicMock(return_value="fallback string")

                async def mock_stream(request):
                    yield (mock_task, {})

                mock_a2a.send_message = mock_stream

                result = await engine.send_message_to_agent("test_agent", "task")

                assert result == "fallback string"

    @pytest.mark.asyncio
    async def test_send_message_empty_response(self, mock_agent_card, mock_llm_client):
        """测试空响应时的异常处理"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_a2a = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a

                # 模拟空迭代
                async def mock_empty_stream(request):
                    return
                    yield  # 使函数成为生成器

                mock_a2a.send_message = mock_empty_stream

                with pytest.raises(RuntimeError, match="no response received"):
                    await engine.send_message_to_agent("test_agent", "task")


class TestRunWorkflow:
    """测试 run 主方法"""

    @pytest.mark.asyncio
    async def test_run_empty_workflow(self, mock_llm_client):
        """测试空工作流执行"""
        empty_psop = PSOP(name="empty", steps=[])

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=empty_psop, agent_cards=[])

            result = await engine.run()

            assert result == []
            assert engine.current_step_idx == 0

    @pytest.mark.asyncio
    async def test_run_single_step_workflow(self, sample_step, mock_agent_card, mock_llm_client):
        """测试单步骤工作流执行"""
        psop = PSOP(name="single", steps=[sample_step])

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])

            # Mock 依赖方法
            engine._execute_subtasks = AsyncMock(return_value=({"t": "ok"}, True))
            engine._process_llm_decision = AsyncMock(side_effect=lambda s, r: setattr(engine, 'current_step_idx', 999))

            result = await engine.run()

            assert engine.current_step_idx == 999
            engine._execute_subtasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_exception_handling(self, sample_psop, mock_agent_card, mock_llm_client, caplog):
        """测试 run 方法异常捕获"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            # 模拟内部方法抛出异常
            engine._execute_single_step = AsyncMock(side_effect=RuntimeError("Unexpected error"))

            with pytest.raises(RuntimeError, match="Unexpected error"):
                await engine.run()


class TestIntegration:
    """端到端集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, mock_llm_client):
        """测试完整工作流执行流程: step1 -> step2 -> end"""

        psop = PSOP(
            name="integration_test",
            steps=[
                Step(
                    name="step1",
                    type=StepType.ALL_SUCCESS,
                    subtasks=[Task(description="Task A", agent="agent1", skill="skill_a")],
                    next=[JumpCondition(step="step2", condition="")]
                ),
                Step(
                    name="step2",
                    type=StepType.ALL_SUCCESS,
                    subtasks=[Task(description="Task B", agent="agent2", skill="skill_b")],
                    next=None
                )
            ]
        )

        mock_card1 = MagicMock(name="agent1")
        mock_card1.name = "agent1"
        mock_card1.capabilities = MagicMock(streaming=False)

        mock_card2 = MagicMock(name="agent2")
        mock_card2.name = "agent2"
        mock_card2.capabilities = MagicMock(streaming=False)

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_card1, mock_card2])

            # Mock 外部调用
            async def mock_send(agent, task_desc):
                return f"Result from {agent}: {task_desc}"

            engine.send_message_to_agent = mock_send

            # Mock LLM 决策: step1->step2, step2->end
            decisions = iter(["step2", "end"])
            mock_llm_client.ask_llm = MagicMock(side_effect=lambda p: ("id", next(decisions)))

            # 执行工作流
            history = await engine.run()

            # 验证执行结果
            assert engine.current_step_idx == len(psop.steps)
            assert len(history) == 2

            # 验证任务状态
            assert psop.steps[0].subtasks[0].status.value == "success"
            assert psop.steps[1].subtasks[0].status.value == "success"

    @pytest.mark.asyncio
    async def test_workflow_early_termination_on_failure(self, mock_llm_client):
        """测试任务失败时工作流提前终止"""

        psop = PSOP(
            name="fail_test",
            steps=[
                Step(
                    name="step1",
                    type=StepType.ALL_SUCCESS,
                    subtasks=[Task(description="Fail task", agent="agent1", skill="skill_x")],
                    next=[JumpCondition(step="step2", condition="always")]
                ),
                Step(name="step2", type=StepType.ALL_SUCCESS, subtasks=[])
            ]
        )

        mock_card = MagicMock(name="agent1")
        mock_card.name = "agent1"
        mock_card.capabilities = MagicMock(streaming=False)

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_card])
            engine.send_message_to_agent = AsyncMock(side_effect=RuntimeError("Agent down"))

            history = await engine.run()

            # 验证流程在 step1 失败后终止
            assert len(history) == 2
            assert history[0]["status"] == "FAILED"
            assert engine.current_step_idx == len(psop.steps)

    @pytest.mark.asyncio
    async def test_event_callback_integration(self, mock_llm_client):
        """测试事件回调完整集成"""

        psop = PSOP(name="callback_test", steps=[
            Step(name="s1", type=StepType.ALL_SUCCESS,
                 subtasks=[Task(description="t1", agent="a1", skill="s1")],
                 next=None)
        ])

        mock_card = MagicMock(name="a1")
        mock_card.name = "a1"
        mock_card.capabilities = MagicMock(streaming=False)

        callback_events = []

        def capture_callback(event_type, data):
            callback_events.append((event_type, data))

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_card])
            engine.set_push_callback(capture_callback)
            engine.send_message_to_agent = AsyncMock(return_value="OK")
            mock_llm_client.ask_llm = MagicMock(return_value=("id", "end"))

            await engine.run()

            event_types = [e[0] for e in callback_events]
            assert "psop_update" in event_types


class TestEdgeCases:
    """边界条件和异常场景测试"""

    @pytest.mark.asyncio
    async def test_any_success_step_type(self, mock_llm_client):
        """测试 StepType.ANY_SUCCESS 逻辑（当前实现中子任务是顺序执行）"""
        step = Step(
            name="any_step",
            type=StepType.ANY_SUCCESS,
            subtasks=[
                Task(description="Task1", agent="a1", skill="s1"),
                Task(description="Task2", agent="a2", skill="s2"),
            ],
            next=None
        )

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])
            # 第一个失败，第二个成功
            engine.send_message_to_agent = AsyncMock(side_effect=[
                RuntimeError("fail"),
                "success"
            ])

            results, success = await engine._execute_subtasks(step)

            # 注意：当前实现在第一个任务失败时就 break，所以 success 为 False
            # 这是实现细节，测试用于文档化当前行为
            assert success is False

    @pytest.mark.asyncio
    async def test_empty_subtasks_step(self, mock_llm_client):
        """测试空子任务列表的步骤"""
        step = Step(name="empty_step", type=StepType.ALL_SUCCESS, subtasks=[], next=None)

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])

            results, success = await engine._execute_subtasks(step)

            assert success is True
            assert results == {}

    @pytest.mark.asyncio
    async def test_llm_decision_with_special_characters(self, sample_step, mock_llm_client):
        """测试 LLM 决策处理特殊字符"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step, Step(
                name="step-2_with.special",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=[JumpCondition(step="end", condition="energy saving success")]
            )]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            # 返回带特殊字符的步骤名
            mock_llm_client.ask_llm.return_value = ("id", "step-2_with.special")

            result = engine._llm_route_decision(sample_step, {"skill": "ok"})

            assert result == "step-2_with.special"

    @pytest.mark.asyncio
    async def test_push_event_callback_exception_not_propagated(self, sample_psop, mock_agent_card, mock_llm_client):
        """测试 _push_event 中回调异常不影响主流程"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            def failing_callback(*args, **kwargs):
                raise ValueError("Callback error")

            engine.set_push_callback(failing_callback)

            # 不应抛出异常
            engine._push_event("test", {"data": 123})

            # 可以继续正常执行
            assert engine.push_callback is not None
