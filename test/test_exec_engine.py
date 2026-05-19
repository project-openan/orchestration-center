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

# Module imports under test
from orchestrate.runtime.exec_engine import DynamicWorkflowEngine
from orchestrate.core.model.psop import (
    PSOP, Step, Task, TaskStatus, StepType, JumpCondition
)


@pytest.fixture
def mock_agent_card():
    """Mock Agent Card object"""
    card = MagicMock()
    card.name = "test_agent"
    card.capabilities = MagicMock()
    card.capabilities.streaming = False
    card.url = "http://test-agent:8000"
    return card


@pytest.fixture
def mock_llm_client():
    """Mock LLM client, returns: (request_id, response_text)"""
    client = MagicMock()
    client.ask_llm = MagicMock(return_value=("mock_req_id", "step2"))
    return client


@pytest.fixture
def sample_task():
    """Create standard test Task"""
    return Task(
        description="Test energy saving analysis",
        agent="energy_agent",
        skill="best_effort_energy_saving"
    )


@pytest.fixture
def sample_step(sample_task):
    """Create standard test Step"""
    return Step(
        name="step1",
        type=StepType.ALL_SUCCESS,
        subtasks=[sample_task],
        next=[JumpCondition(step="step2", condition="energy saving success")]
    )


@pytest.fixture
def sample_psop(sample_step):
    """Create standard test PSOP"""
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
    """Mock httpx AsyncClient"""
    client = AsyncMock()
    client.timeout = MagicMock()
    return client


@pytest.fixture
def mock_a2a_response_task():
    """Mock A2A response task object"""
    task = MagicMock()
    task.artifacts = [MagicMock()]
    task.model_dump_json = MagicMock(return_value='{"content":"mock response"}')
    return task


class TestEngineInitialization:
    """Test engine initialization related functionality"""

    def test_init_basic(self, sample_psop, mock_agent_card, mock_llm_client):
        """Test basic initialization"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            assert engine.workflow == sample_psop
            assert engine.current_step_idx == 0
            assert engine.execution_history == []
            assert engine.push_callback is None
            assert engine.llm_client == mock_llm_client

    def test_set_push_callback(self, sample_psop, mock_agent_card, mock_llm_client):
        """Test callback function setting"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            callback = MagicMock()
            engine.set_push_callback(callback)

            assert engine.push_callback == callback

    def test_push_event_with_callback(self, sample_psop, mock_agent_card, mock_llm_client):
        """Test event push successfully calls callback"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            callback = MagicMock()
            engine.set_push_callback(callback)

            engine._push_event("test_event", {"key": "value"})

            callback.assert_called_once_with("test_event", {"key": "value"})

    def test_push_event_callback_exception_handled(self, sample_psop, mock_agent_card, mock_llm_client, caplog):
        """Test callback exception is caught without affecting main flow"""
        import logging
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            def bad_callback(*args, **kwargs):
                raise RuntimeError("Callback failed")

            engine.set_push_callback(bad_callback)

            # Should not raise exception
            engine._push_event("test_event", {"key": "value"})


class TestExecuteSubtasks:
    """Test _execute_subtasks method"""

    @pytest.mark.asyncio
    async def test_execute_subtasks_success(self, sample_step, mock_agent_card, mock_llm_client):
        """Test subtask execution success"""
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
        """Test subtask execution failure"""
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
        """Test multiple subtasks all succeed"""
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
        """Test pushing PSOP status update during execution"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.model_dump_json = MagicMock(return_value='{"mock":"psop"}')
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])
            engine.send_message_to_agent = AsyncMock(return_value="OK")

            callback = MagicMock()
            engine.set_push_callback(callback)

            await engine._execute_subtasks(sample_step)

            # Verify psop_update event was pushed
            callback.assert_called()
            event_types = [call_args[0][0] for call_args in callback.call_args_list]
            assert "psop_update" in event_types


class TestLLMRouteDecision:
    """Test _llm_route_decision method"""

    @pytest.mark.asyncio
    async def test_llm_decision_jump_to_next(self, sample_step, mock_llm_client):
        """Test LLM decides to jump to next step"""
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
            # Verify prompt contains key information
            prompt = mock_llm_client.ask_llm.call_args[0][0]
            assert "Current context" in prompt
            assert "Execution Result" in prompt

    @pytest.mark.asyncio
    async def test_llm_decision_end_on_error(self, sample_step, mock_llm_client):
        """Test LLM decides to end on execution error"""
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
            # Verify prompt contains error information
            prompt = mock_llm_client.ask_llm.call_args[0][0]
            assert "Execution failed" in prompt

    @pytest.mark.asyncio
    async def test_llm_decision_retry(self, sample_step, mock_llm_client):
        """Test LLM decides to retry"""
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
        """Test defaulting to end when LLM returns invalid step name"""
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
        """Test decision result is case-insensitive"""
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

            # LLM returns uppercase
            mock_llm_client.ask_llm.return_value = ("id", "STEP2")

            result = engine._llm_route_decision(sample_step, {"skill": "success"})

            assert result == "STEP2"  # Returns original value, but internal comparison is lowercase

    @pytest.mark.asyncio
    async def test_llm_decision_llm_call_failure(self, sample_step):
        """Test fault tolerance when LLM call fails"""
        mock_llm = MagicMock()
        mock_llm.ask_llm.side_effect = Exception("LLM service down")

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm):
            engine = DynamicWorkflowEngine(psop=MagicMock(steps=[sample_step]), agent_cards=[])

            result = engine._llm_route_decision(sample_step, {"skill": "success"})

            assert result == "end"

    @pytest.mark.asyncio
    async def test_llm_decision_no_llm_client(self, sample_step):
        """Test exception raised when LLM client is not initialized"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=None):
            engine = DynamicWorkflowEngine(psop=MagicMock(steps=[sample_step]), agent_cards=[])
            engine.llm_client = None

            with pytest.raises(ValueError, match="LLM Client not initialized"):
                engine._llm_route_decision(sample_step, {"skill": "success"})

    @pytest.mark.asyncio
    async def test_llm_decision_prompt_contains_conditions(self, sample_step, mock_llm_client):
        """Test prompt correctly contains jump conditions"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[])

            engine._llm_route_decision(sample_step, {"skill": "result"})

            prompt = mock_llm_client.ask_llm.call_args[0][0]
            # Verify conditions are included in prompt as JSON
            assert "step2" in prompt
            assert "energy saving success" in prompt


class TestExecuteSingleStep:
    """Test _execute_single_step method"""

    @pytest.mark.asyncio
    async def test_execute_step_success_flow(self, sample_step, mock_agent_card, mock_llm_client):
        """Test step execution succeeds and jumps"""
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
        """Test flow stops when step fails"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = MagicMock()
            psop.steps = [sample_step]
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])

            engine._execute_subtasks = AsyncMock(return_value=({"task": "error"}, False))
            engine._record_stop_event = MagicMock()

            await engine._execute_single_step()

            # Verify flow was terminated
            assert engine.current_step_idx == len(psop.steps)
            engine._record_stop_event.assert_called_once()


class TestFindStepIndex:
    """Test _find_step_index method"""

    def test_find_existing_step(self, sample_psop, mock_llm_client):
        """Test finding an existing step"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("step2")
            assert idx == 1

    def test_find_first_step(self, sample_psop, mock_llm_client):
        """Test finding the first step"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("step1")
            assert idx == 0

    def test_find_nonexistent_step(self, sample_psop, mock_llm_client):
        """Test finding a nonexistent step"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            idx = engine._find_step_index("nonexistent")
            assert idx is None

    def test_find_step_empty_psop(self, mock_llm_client):
        """Test step lookup in empty PSOP"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            empty_psop = PSOP(name="empty", steps=[])
            engine = DynamicWorkflowEngine(psop=empty_psop, agent_cards=[])

            idx = engine._find_step_index("any_step")
            assert idx is None


class TestRecordStopEvent:
    """Test _record_stop_event method"""

    def test_record_stop_event(self, sample_psop, mock_llm_client):
        """Test stop event is recorded correctly"""
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
        """Test recording multiple stop events"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[])

            engine._record_stop_event("Error1", {"code": 1})
            engine._record_stop_event("Error2", {"code": 2})

            assert len(engine.execution_history) == 2
            assert engine.execution_history[0]["reason"] == "Error1"
            assert engine.execution_history[1]["reason"] == "Error2"


class TestSendMessageToAgent:
    """Test send_message_to_agent method"""

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_agent_card, mock_llm_client, mock_a2a_response_task):
        """Test successfully sending a message and receiving a response"""
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
        """Test exception raised when Agent is not found"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])

            with pytest.raises(RuntimeError, match="Agent not found"):
                await engine.send_message_to_agent("nonexistent_agent", "task")

    @pytest.mark.asyncio
    async def test_send_message_timeout(self, mock_agent_card, mock_llm_client):
        """Test timeout exception handling"""
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
        """Test connection error handling"""
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
        """Test event push during communication"""
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
        """Test fallback when there are no artifacts"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_a2a = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a

                # Mock task with no artifacts
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
        """Test exception handling for empty response"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[mock_agent_card])

            with patch('httpx.AsyncClient'), \
                    patch('orchestrate.runtime.exec_engine.ClientFactory') as mock_factory:
                mock_a2a = AsyncMock()
                mock_factory.return_value.create.return_value = mock_a2a

                # Mock empty iteration
                async def mock_empty_stream(request):
                    return
                    yield  # Make function a generator

                mock_a2a.send_message = mock_empty_stream

                with pytest.raises(RuntimeError, match="no response received"):
                    await engine.send_message_to_agent("test_agent", "task")


class TestRunWorkflow:
    """Test run main method"""

    @pytest.mark.asyncio
    async def test_run_empty_workflow(self, mock_llm_client):
        """Test empty workflow execution"""
        empty_psop = PSOP(name="empty", steps=[])

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=empty_psop, agent_cards=[])

            result = await engine.run()

            assert result == []
            assert engine.current_step_idx == 0

    @pytest.mark.asyncio
    async def test_run_single_step_workflow(self, sample_step, mock_agent_card, mock_llm_client):
        """Test single-step workflow execution"""
        psop = PSOP(name="single", steps=[sample_step])

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_agent_card])

            # Mock dependent methods
            engine._execute_subtasks = AsyncMock(return_value=({"t": "ok"}, True))
            engine._process_llm_decision = AsyncMock(side_effect=lambda s, r: setattr(engine, 'current_step_idx', 999))

            result = await engine.run()

            assert engine.current_step_idx == 999
            engine._execute_subtasks.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_exception_handling(self, sample_psop, mock_agent_card, mock_llm_client, caplog):
        """Test exception capture in run method"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            # Mock internal method throwing exception
            engine._execute_single_step = AsyncMock(side_effect=RuntimeError("Unexpected error"))

            with pytest.raises(RuntimeError, match="Unexpected error"):
                await engine.run()


class TestIntegration:
    """End-to-end integration test"""

    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, mock_llm_client):
        """Test complete workflow execution flow: step1 -> step2 -> end"""

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

            # Mock external calls
            async def mock_send(agent, task_desc):
                return f"Result from {agent}: {task_desc}"

            engine.send_message_to_agent = mock_send

            # Mock LLM decisions: step1->step2, step2->end
            decisions = iter(["step2", "end"])
            mock_llm_client.ask_llm = MagicMock(side_effect=lambda p: ("id", next(decisions)))

            # Execute workflow
            history = await engine.run()

            # Verify execution results
            assert engine.current_step_idx == len(psop.steps)
            assert len(history) == 2

            # Verify task statuses
            assert psop.steps[0].subtasks[0].status.value == "success"
            assert psop.steps[1].subtasks[0].status.value == "success"

    @pytest.mark.asyncio
    async def test_workflow_early_termination_on_failure(self, mock_llm_client):
        """Test workflow early termination on task failure"""

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

            # Verify flow terminated after step1 failure
            assert len(history) == 2
            assert history[0]["status"] == "FAILED"
            assert engine.current_step_idx == len(psop.steps)

    @pytest.mark.asyncio
    async def test_event_callback_integration(self, mock_llm_client):
        """Test complete event callback integration"""

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
    """Boundary conditions and exception scenario tests"""

    @pytest.mark.asyncio
    async def test_any_success_step_type(self, mock_llm_client):
        """Test StepType.ANY_SUCCESS logic (current implementation executes subtasks sequentially)"""
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
            # First fails, second succeeds
            engine.send_message_to_agent = AsyncMock(side_effect=[
                RuntimeError("fail"),
                "success"
            ])

            results, success = await engine._execute_subtasks(step)

            # Note: current implementation breaks on first task failure, so success is False
            # This is an implementation detail; the test documents current behavior
            assert success is False

    @pytest.mark.asyncio
    async def test_empty_subtasks_step(self, mock_llm_client):
        """Test step with empty subtask list"""
        step = Step(name="empty_step", type=StepType.ALL_SUCCESS, subtasks=[], next=None)

        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])

            results, success = await engine._execute_subtasks(step)

            assert success is True
            assert results == {}

    @pytest.mark.asyncio
    async def test_llm_decision_with_special_characters(self, sample_step, mock_llm_client):
        """Test LLM decision handling special characters"""
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

            # Returns step name with special characters
            mock_llm_client.ask_llm.return_value = ("id", "step-2_with.special")

            result = engine._llm_route_decision(sample_step, {"skill": "ok"})

            assert result == "step-2_with.special"

    @pytest.mark.asyncio
    async def test_push_event_callback_exception_not_propagated(self, sample_psop, mock_agent_card, mock_llm_client):
        """Test callback exception in _push_event does not affect main flow"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=sample_psop, agent_cards=[mock_agent_card])

            def failing_callback(*args, **kwargs):
                raise ValueError("Callback error")

            engine.set_push_callback(failing_callback)

            # Should not raise exception
            engine._push_event("test", {"data": 123})

            # Can continue normal execution
            assert engine.push_callback is not None


class TestCrossLayerOrchestration:
    """Cross-layer orchestration tests - context passing between steps"""

    @pytest.mark.asyncio
    async def test_build_context_for_step_empty(self, mock_llm_client):
        """Test _build_context_for_step returns empty when no context_from"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])
            step = Step(
                name="step1",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=None
            )
            result = engine._build_context_for_step(step)
            assert result == ""

    def test_build_context_for_step_with_refs(self, mock_llm_client):
        """Test _build_context_for_step builds context from referenced steps"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])
            engine.step_outputs = {
                "step1": {"task_a": "result from a", "task_b": "result from b"},
                "step2": {"task_c": "result from c"},
            }
            step = Step(
                name="step3",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=None,
                layer=1,
                context_from=["step1", "step2"]
            )
            result = engine._build_context_for_step(step)
            assert "step1" in result
            assert "step2" in result
            assert "task_a" in result
            assert "result from a" in result
            assert "task_b" in result
            assert "result from b" in result
            assert "task_c" in result
            assert "result from c" in result

    def test_build_context_for_step_missing_ref(self, mock_llm_client):
        """Test _build_context_for_step handles missing referenced steps gracefully"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            engine = DynamicWorkflowEngine(psop=MagicMock(), agent_cards=[])
            engine.step_outputs = {
                "step1": {"task_a": "result"},
            }
            step = Step(
                name="step3",
                type=StepType.ALL_SUCCESS,
                subtasks=[],
                next=None,
                layer=1,
                context_from=["step1", "step2"]
            )
            result = engine._build_context_for_step(step)
            assert "step1" in result
            assert "step2" not in result

    def test_build_task_message_without_context(self):
        """Test _build_task_message returns just description when no context"""
        task = Task(description="do something", agent="agent1", skill="skill1")
        result = DynamicWorkflowEngine._build_task_message(task, "")
        assert result == "do something"

    def test_build_task_message_with_context(self):
        """Test _build_task_message prepends context to task description"""
        task = Task(description="summarize findings", agent="agent1", skill="skill1")
        context = "## 前置步骤执行结果\n### step1 结果\n- 任务: \"analyze\"\n  输出: OK"
        result = DynamicWorkflowEngine._build_task_message(task, context)
        assert context in result
        assert task.description in result
        assert "当前任务" in result

    @pytest.mark.asyncio
    async def test_step_outputs_accumulation(self, mock_llm_client):
        """Test that step outputs are accumulated in step_outputs dict"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = PSOP(
                name="accum_test",
                steps=[
                    Step(name="step1", type=StepType.ALL_SUCCESS,
                         subtasks=[Task(description="t1", agent="a1", skill="s1")],
                         next=[JumpCondition(step="step2", condition="")]),
                    Step(name="step2", type=StepType.ALL_SUCCESS,
                         subtasks=[Task(description="t2", agent="a2", skill="s2")],
                         next=None, layer=1, context_from=["step1"])
                ]
            )

            mock_card1 = MagicMock(name="a1")
            mock_card1.name = "a1"
            mock_card1.capabilities = MagicMock(streaming=False)

            mock_card2 = MagicMock(name="a2")
            mock_card2.name = "a2"
            mock_card2.capabilities = MagicMock(streaming=False)

            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_card1, mock_card2])

            async def mock_send(agent, task_desc):
                return f"Result from {agent}"

            engine.send_message_to_agent = mock_send

            decisions = iter(["step2", "end"])
            mock_llm_client.ask_llm = MagicMock(side_effect=lambda p: ("id", next(decisions)))

            await engine.run()

            assert "step1" in engine.step_outputs
            assert "step2" in engine.step_outputs
            assert engine.step_outputs["step1"]["t1"] == "Result from a1"

    @pytest.mark.asyncio
    async def test_context_injected_to_downstream_agent(self, mock_llm_client):
        """Test that context from upstream steps is injected to downstream agent"""
        with patch('orchestrate.runtime.exec_engine.get_llm_instance',
                   return_value=mock_llm_client):
            psop = PSOP(
                name="context_inject_test",
                steps=[
                    Step(name="step1", type=StepType.ALL_SUCCESS,
                         subtasks=[Task(description="analyze data", agent="analyzer", skill="analyze")],
                         next=[JumpCondition(step="step2", condition="")]),
                    Step(name="step2", type=StepType.ALL_SUCCESS, layer=1,
                         context_from=["step1"],
                         subtasks=[Task(description="summarize all", agent="summarizer", skill="summarize")],
                         next=None)
                ]
            )

            mock_card = MagicMock()
            mock_card.name = "analyzer"
            mock_card.capabilities = MagicMock(streaming=False)

            mock_card2 = MagicMock()
            mock_card2.name = "summarizer"
            mock_card2.capabilities = MagicMock(streaming=False)

            engine = DynamicWorkflowEngine(psop=psop, agent_cards=[mock_card, mock_card2])

            captured_messages = []

            async def mock_send(agent, task_desc):
                captured_messages.append((agent, task_desc))
                return f"Result from {agent}"

            engine.send_message_to_agent = mock_send

            decisions = iter(["step2", "end"])
            mock_llm_client.ask_llm = MagicMock(side_effect=lambda p: ("id", next(decisions)))

            await engine.run()

            assert len(captured_messages) == 2
            step2_message = captured_messages[1][1]
            assert "前置步骤执行结果" in step2_message
            assert "step1" in step2_message
            assert "analyze data" in step2_message
            assert "当前任务" in step2_message
            assert "summarize all" in step2_message

    @pytest.mark.asyncio
    async def test_layer_field_default_value(self):
        """Test that layer field defaults to 0"""
        step = Step(
            name="test",
            type=StepType.ALL_SUCCESS,
            subtasks=[],
            next=None
        )
        assert step.layer == 0
        assert step.context_from is None

    @pytest.mark.asyncio
    async def test_psop_model_serialization_with_layer(self):
        """Test that PSOP model with layer and context_from serializes correctly"""
        psop = PSOP(
            name="cross_layer_test",
            steps=[
                Step(name="step1", type=StepType.ALL_SUCCESS,
                     subtasks=[Task(description="t1", agent="a1", skill="s1")],
                     next=[JumpCondition(step="end", condition="")], layer=0),
                Step(name="step2", type=StepType.ALL_SUCCESS, layer=1,
                     context_from=["step1"],
                     subtasks=[Task(description="t2", agent="a2", skill="s2")],
                     next=None)
            ]
        )
        data = psop.model_dump()
        assert data["steps"][0]["layer"] == 0
        assert data["steps"][0]["context_from"] is None
        assert data["steps"][1]["layer"] == 1
        assert data["steps"][1]["context_from"] == ["step1"]
