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

import os
import tempfile
import json
import asyncio
import threading
import queue
from typing import Optional, List, Any

import anyio
from a2a.types import AgentCard
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel
from starlette import status
from starlette.responses import Response

from common.config import MAX_URL_LENGTH, MAX_REQUEST_BODY_SIZE, CONN_MAX, CONN_TIMEOUT, \
    FLOW_CTL_PARALLEL_RETRIEVE_PSOP, FLOW_CTL_PARALLEL_GENERATE_PSOP, FLOW_CTL_PARALLEL_AGENT_CARDS, \
    FLOW_CTL_PARALLEL_DELETE_PSOP, FLOW_CTL_PARALLEL_SAVE_PSOP, FLOW_CTL_PARALLEL_ONE_PSOP, FLOW_CTL_PARALLEL_ALL_PSOPS, \
    FLOW_CTL_PARALLEL_PLAN, FLOW_CTL_PARALLEL_PARSE_PDF
from common.util.config_util import get_conf
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.psop_generator import PsopGenerator
from orchestrate.core.intent_psop_generator import IntentPsopGenerator
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.core.retrieval import WorkflowRetrieval
from orchestrate.server.middleware import ConnectionLimitMiddleware, TimeoutMiddleware, RateLimiter
from orchestrate.solution_package.parse_flow import SolutionPackageParser
from orchestrate.runtime.exec_engine import DynamicWorkflowEngine
from orchestrate.registry_client.client_factory import AgentRegistryClientFactory

# 创建FastAPI应用
app = FastAPI(title="Workflow Orchestration API", version="1.0.0")

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
config = get_conf()

app.add_middleware(ConnectionLimitMiddleware, max_connections=int(config.get(CONN_MAX)))

app.add_middleware(TimeoutMiddleware, timeout_seconds=int(config.get(CONN_TIMEOUT)))


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if len(str(request.url)) > MAX_URL_LENGTH:
        return Response(
            content="URI Too Long",
            status_code=status.HTTP_414_URI_TOO_LONG
        )
    if request.method in ("POST", "PUT"):
        total_size = 0
        body_chunks = []

        try:
            async for chunk in request.stream():
                total_size += len(chunk)
                if total_size > MAX_REQUEST_BODY_SIZE:
                    return Response(
                        content=f"Request body is toll large, maximum allowed {MAX_REQUEST_BODY_SIZE // 1024} KB",
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE
                    )
                body_chunks.append(chunk)
            request._body = b''.join(body_chunks)
        except Exception as e:
            logger.error(f"Bad Request: {e}")
            return Response(
                content=f"Bad Request",
                status_code=status.HTTP_400_BAD_REQUEST
            )
    return await call_next(request)


# 初始化存储和检索组件
storage = WorkflowStorage()
retrieval = WorkflowRetrieval(storage)


# 定义请求/响应模型
class PlanRequest(BaseModel):
    preflow: dict
    agent_cards: List[dict]


class SavePSOPRequest(BaseModel):
    psop: dict


class IntentRequest(BaseModel):
    user_intent: str
    workflow_name: Optional[str] = None


class RetrieveIntentRequest(BaseModel):
    user_intent: str


class ParsePDFResponse(BaseModel):
    status: str
    message: str
    content: str


class PlanResponse(BaseModel):
    status: str
    data: str


class PSOPListResponse(BaseModel):
    status: str
    count: int
    data: List[dict]


class PSOPDetailResponse(BaseModel):
    status: str
    data: dict


class PSOPDeleteResponse(BaseModel):
    status: str
    message: str


class AgentCardResponse(BaseModel):
    status: str
    count: int
    data: List[dict]


class IntentResponse(BaseModel):
    status: str
    message: str
    data: dict


class RetrieveIntentResponse(BaseModel):
    status: str
    message: str
    data: Optional[dict] = None

parse_pdf_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_PARSE_PDF)))
@app.post("/parse-pdf", response_model=ParsePDFResponse)
async def parse_pdf(file: UploadFile = File(...), _: Any = Depends(RateLimiter(config, "parse_pdf"))):
    """
    解析PDF文件，提取工作流定义
    """
    acquired = False
    try:
        parse_pdf_semaphore.acquire_nowait()
        acquired = True

        # 验证文件类型
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_file_path = tmp.name

        parser = SolutionPackageParser()
        pre_md = parser.parse_pdf_chapter(
            tmp_file_path,
            "5. Interaction Flow"
        )
        if not pre_md:
            raise HTTPException(status_code=400, detail="PDF解析失败，未找到指定章节")

        preflow = PreFlow(
            name=file.filename,
            description=f"从PDF文件 {file.filename} 解析的工作流",
            steps_md=pre_md
        )
        return ParsePDFResponse(
            status="success",
            message="PDF文件解析成功",
            content=preflow.model_dump_json()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败：{str(e)}")
    finally:
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
        if acquired:
            parse_pdf_semaphore.release()

plan_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_PLAN)))
@app.post("/plan", response_model=PlanResponse)
async def plan(request: PlanRequest, _: Any = Depends(RateLimiter(config, "plan"))):
    """
    根据PreFlow和AgentCards生成PSOP工作流
    """
    acquired = False
    try:
        plan_semaphore.acquire_nowait()
        acquired = True
        generator = PsopGenerator()
        workflow = generator.generate_psop_workflow(
            PreFlow.model_validate(request.preflow),
            [AgentCard.model_validate(card) for card in request.agent_cards]
        )
        storage.save_psop(workflow)

        return PlanResponse(
            status="success",
            data=workflow.model_dump_json()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"规划失败 : {str(e)}")
    finally:
        if acquired:
            plan_semaphore.release()


all_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_ALL_PSOPS)))


@app.get("/psops", response_model=PSOPListResponse)
async def get_all_psops(limit: int = 10, workflow_type: str = 'psop',
                        _: Any = Depends(RateLimiter(config, "get_all_psops"))):
    """
    获取所有PSOP工作流列表
    """
    acquired = False
    try:
        all_psop_semaphore.acquire_nowait()
        acquired = True
        recent_workflows = retrieval.list_recent_workflows(limit=limit, workflow_type=workflow_type)

        return PSOPListResponse(
            status="success",
            count=len(recent_workflows),
            data=[wf.to_dict() for wf in recent_workflows]
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取PSOP列表失败: {str(e)}")
    finally:
        if acquired:
            all_psop_semaphore.release()


one_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_ONE_PSOP)))


@app.get("/psops/{workflow_id}", response_model=PSOPDetailResponse)
async def get_psop_by_id(workflow_id: str, _: Any = Depends(RateLimiter(config, "get_psop_by_id"))):
    """
    根据ID获取PSOP工作流详情
    """
    acquired = False
    try:
        one_psop_semaphore.acquire_nowait()
        acquired = True
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            raise HTTPException(status_code=404, detail=f"未找到ID为 {workflow_id} 的PSOP")

        return PSOPDetailResponse(
            status="success",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取PSOP详情失败: {str(e)}")
    finally:
        if acquired:
            one_psop_semaphore.release()


save_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_SAVE_PSOP)))


@app.post("/psops", status_code=201)
async def save_psop(request: SavePSOPRequest, _: Any = Depends(RateLimiter(config, "save_psop"))):
    """
    保存PSOP工作流
    """
    acquired = False
    try:
        save_psop_semaphore.acquire_nowait()
        acquired = True
        psop = PSOP.model_validate(request.psop)
        saved_id = storage.save_psop(psop)

        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "PSOP保存成功",
                "workflow_id": saved_id
            }
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存PSOP失败: {str(e)}")
    finally:
        if acquired:
            save_psop_semaphore.release()


delete_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_DELETE_PSOP)))


@app.delete("/psops/{workflow_id}", response_model=PSOPDeleteResponse)
async def delete_psop(workflow_id: str, _: Any = Depends(RateLimiter(config, "delete_psop"))):
    """
    删除指定ID的PSOP工作流
    """
    acquired = False
    try:
        delete_psop_semaphore.acquire_nowait()
        acquired = True
        # 先检查PSOP是否存在
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            raise HTTPException(status_code=404, detail=f"未找到ID为 {workflow_id} 的PSOP")

        # 删除PSOP
        deleted = storage.delete_psop(workflow_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="删除PSOP失败: 文件可能不存在")

        return PSOPDeleteResponse(
            status="success",
            message=f"PSOP {workflow_id} 删除成功"
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除PSOP失败: {str(e)}")
    finally:
        if acquired:
            delete_psop_semaphore.release()


agent_cards_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_AGENT_CARDS)))


@app.get("/agent-cards", response_model=AgentCardResponse)
async def get_all_agent_cards(_: Any = Depends(RateLimiter(config, "get_all_agent_cards"))):
    """
    获取全量AgentCard列表
    """
    acquired = False
    try:
        agent_cards_semaphore.acquire_nowait()
        acquired = True
        # 获取所有AgentCard
        agent_registry_factory = AgentRegistryClientFactory()
        agent_cards = agent_registry_factory.create_from_env().list_exact()

        # 将AgentCard转换为字典格式
        agent_cards_data = [card.model_dump() for card in agent_cards]

        return AgentCardResponse(
            status="success",
            count=len(agent_cards_data),
            data=agent_cards_data
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"配置文件不存在: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取AgentCard失败: {str(e)}")
    finally:
        if acquired:
            agent_cards_semaphore.release()


generate_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_GENERATE_PSOP)))


@app.post("/generate-from-intent", response_model=IntentResponse)
async def generate_psop_from_intent(request: IntentRequest,
                                    _: Any = Depends(RateLimiter(config, "generate_psop_from_intent"))):
    """
    根据自然语言意图生成PSOP工作流
    """
    acquired = False
    try:
        generate_semaphore.acquire_nowait()
        acquired = True
        # 获取AgentCards
        agent_registry_factory = AgentRegistryClientFactory()
        agent_cards = agent_registry_factory.create_from_env().list_exact()
        if not agent_cards:
            raise HTTPException(status_code=404, detail="未找到可用的AgentCard")

        # 使用IntentPsopGenerator生成PSOP
        generator = IntentPsopGenerator()
        psop = generator.generate_psop_from_intent(
            user_intent=request.user_intent,
            agent_cards=agent_cards,
            workflow_name=request.workflow_name
        )

        # 可选：自动保存生成的PSOP
        try:
            storage.save_psop(psop)
        except Exception as save_error:
            logger.warning(f"PSOP save failed (does not affect response): {save_error}")

        return IntentResponse(
            status="success",
            message="PSOP生成成功",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate PSOP from intent: {e}")
        raise HTTPException(status_code=500, detail=f"生成PSOP失败: {str(e)}")
    finally:
        if acquired:
            generate_semaphore.release()


retrieve_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_RETRIEVE_PSOP)))


@app.post("/retrieve-by-intent", response_model=RetrieveIntentResponse)
async def retrieve_psop_by_intent(request: RetrieveIntentRequest,
                                  _: Any = Depends(RateLimiter(config, "retrieve_psop_by_intent"))):
    """
    根据自然语言意图检索最合适的PSOP工作流
    """
    acquired = False
    try:
        retrieve_semaphore.acquire_nowait()
        acquired = True
        logger.info(f"Starting PSOP retrieval based on intent: {request.user_intent}")

        # 使用WorkflowRetrieval的retrieve_psop_by_intent方法
        psop = retrieval.retrieve_psop_by_intent(request.user_intent)

        if not psop:
            return RetrieveIntentResponse(
                status="success",
                message="未找到匹配的PSOP",
                data=None
            )

        logger.info(f"Successfully retrieved PSOP: {psop.name} (ID: {psop.id})")

        return RetrieveIntentResponse(
            status="success",
            message="PSOP检索成功",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to retrieve PSOP based on intent: {e}")
        raise HTTPException(status_code=500, detail=f"检索PSOP失败: {str(e)}")
    finally:
        if acquired:
            retrieve_semaphore.release()


@app.get("/rest/start_process_stream")
async def start_process_stream(psop_id: str):
    """
    SSE流式执行工作流
    """
    if not psop_id:
        raise HTTPException(status_code=400, detail="缺少psop_id参数")

    psop = retrieval.get_psop_by_id(psop_id)
    if not psop:
        raise HTTPException(status_code=404, detail=f"未找到ID为 {psop_id} 的PSOP")

    agent_registry_factory = AgentRegistryClientFactory()
    agent_cards = agent_registry_factory.create_from_env().list_exact()
    if not agent_cards:
        raise HTTPException(status_code=404, detail="未找到可用的AgentCard")

    async def event_generator():
        event_queue = queue.Queue()

        def push_callback(event_type: str, data: dict):
            try:
                # 序列化数据，处理无法JSON序列化的对象
                serializable_data = {}
                for key, value in data.items():
                    if hasattr(value, 'model_dump'):
                        # 如果是Pydantic模型，使用model_dump()
                        serializable_data[key] = value.model_dump()
                    elif hasattr(value, '__dict__'):
                        # 如果是普通对象，尝试转换为字典
                        try:
                            serializable_data[key] = value.__dict__
                        except:
                            serializable_data[key] = str(value)
                    elif isinstance(value, (tuple, list)):
                        # 处理列表和元组
                        serializable_data[key] = []
                        for item in value:
                            if hasattr(item, 'model_dump'):
                                serializable_data[key].append(item.model_dump())
                            elif hasattr(item, '__dict__'):
                                try:
                                    serializable_data[key].append(item.__dict__)
                                except:
                                    serializable_data[key].append(str(item))
                            else:
                                serializable_data[key].append(item)
                    else:
                        serializable_data[key] = value

                event_data = {
                    "type": event_type,
                    "data": serializable_data,
                    "timestamp": asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
                }
                event_queue.put(event_data)
            except Exception as e:
                logger.error(f"Failed to push event to queue: {e}")

        async def run_workflow_async():
            try:
                engine = DynamicWorkflowEngine(psop, agent_cards)
                engine.set_push_callback(push_callback)

                event_queue.put({
                    "type": "start",
                    "data": {"psop_id": psop_id, "message": "开始执行工作流"}
                })

                execution_history = await engine.run()

                event_queue.put({
                    "type": "complete",
                    "data": {"psop_id": psop_id, "execution_history": execution_history}
                })

            except Exception as e:
                logger.error(f"Workflow execution failed: {e}")
                event_queue.put({
                    "type": "error",
                    "data": {"psop_id": psop_id, "error": str(e)}
                })

        def run_workflow():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(run_workflow_async())
            finally:
                loop.close()

        workflow_thread = threading.Thread(target=run_workflow)
        workflow_thread.daemon = True
        workflow_thread.start()

        # 发送初始化消息
        yield f"data: {json.dumps({'type': 'init', 'data': {'psop_id': psop_id, 'message': '初始化执行引擎'}})}\n\n"

        # 持续发送事件直到工作流完成
        while workflow_thread.is_alive() or not event_queue.empty():
            try:
                event = event_queue.get(timeout=1)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Failed to process event: {e}")

        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )
