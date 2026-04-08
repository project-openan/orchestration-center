import asyncio
import uuid
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Task, TaskStatus, TaskState, Artifact, TextPart, Part,
)

from framework.llm import get_or_create_deepseek_llm_instance


class EnergySavingIntentAgentExecutor(AgentExecutor):

    def __init__(self) -> None:
        self.llm = get_or_create_deepseek_llm_instance()

    async def execute(
            self,
            context: RequestContext,
            event_queue: EventQueue,
    ) -> None:
        prompt = context.get_user_input()
        response = await asyncio.to_thread(self.answer_query, prompt)
        task = Task(
            id=context.task_id,
            context_id=context.context_id,
            status=TaskStatus(state=TaskState.completed),
            artifacts=[
                Artifact(artifact_id=str(uuid.uuid4()), parts=[Part(root=TextPart(text=response))])
            ]
        )
        await event_queue.enqueue_event(task)

    def answer_query(self, user_message: str):
        prompt = f"""
        你是电信领域的无线意图处理agent模拟器，请根据收到的用户任务，模拟一个靠谱的成功响应。
        
        任务如下: {user_message}
        直接输出中文响应，不用输出其他内容。/no_think
        """
        _, res = self.llm.ask_llm(prompt)
        return res

    async def cancel(
            self,
            context: RequestContext,
            event_queue: EventQueue,
    ) -> None:
        pass
