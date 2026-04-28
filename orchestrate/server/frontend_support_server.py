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
import time
import uuid
from typing import Optional, List, Any

import anyio
from a2a.types import AgentCard
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from google.protobuf.json_format import Parse
from loguru import logger
from pydantic import BaseModel
from starlette import status
from starlette.responses import Response

from common.config import (
    MAX_URL_LENGTH, MAX_REQUEST_BODY_SIZE, CONN_MAX, CONN_TIMEOUT,
    FLOW_CTL_PARALLEL_RETRIEVE_PSOP, FLOW_CTL_PARALLEL_GENERATE_PSOP,
    FLOW_CTL_PARALLEL_AGENT_CARDS, FLOW_CTL_PARALLEL_DELETE_PSOP,
    FLOW_CTL_PARALLEL_SAVE_PSOP, FLOW_CTL_PARALLEL_ONE_PSOP,
    FLOW_CTL_PARALLEL_ALL_PSOPS, FLOW_CTL_PARALLEL_PLAN, FLOW_CTL_PARALLEL_PARSE_PDF,
)
from common.custom.default_handle import HandlerRegistry
from common.custom.interface_type import InterfaceType
from common.log.audit_logger import audit_logger, OperationObject, OperationName, LogLevel, OperationResult
from common.util.config_util import get_conf
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.psop_generator import PsopGenerator
from orchestrate.core.intent_psop_generator import IntentPsopGenerator
from orchestrate.core.retrieval import WorkflowRetrieval
from orchestrate.server.middleware import ConnectionLimitMiddleware, TimeoutMiddleware, RateLimiter
from orchestrate.solution_package.parse_flow import SolutionPackageParser
from orchestrate.runtime.exec_engine import DynamicWorkflowEngine
from orchestrate.registry_client.client_factory import AgentRegistryClientFactory
from orchestrate.workflow_storage_instance import get_workflow_storage

# Create FastAPI application
app = FastAPI(title="Workflow Orchestration API", version="1.0.0")

# Configure CORS
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
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]

    client_ip = request.client.host if request.client else "unknown"
    query_params = dict(request.query_params)
    logger.info(f"[{request_id}] --> {request.method} {request.url.path} "
                f"client={client_ip}"
                f"{' params=' + str(query_params) if query_params else ''}")

    start_time = time.time()
    try:
        response = await call_next(request)
        duration = time.time() - start_time
        logger.info(f"[{request_id}] <-- {request.method} {request.url.path} "
                    f"status={response.status_code} duration={duration:.3f}s")
        return response
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"[{request_id}] <-- {request.method} {request.url.path} "
                     f"ERROR={e} duration={duration:.3f}s")
        raise


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


# Initialize storage and retrieval components
save_handle = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
delete_handle = HandlerRegistry.get_handler(InterfaceType.DELETE_PSOP)
retrieval = WorkflowRetrieval(get_workflow_storage())


# Define request/response models
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
    Parse PDF file and extract workflow definition
    """
    acquired = False
    tmp_file_path = None
    try:
        parse_pdf_semaphore.acquire_nowait()
        acquired = True

        filename = file.filename or "unknown"
        logger.info(f"Parsing PDF file: {filename}, size: {file.size or 'unknown'}")

        # Validate file type
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            logger.warning(f"Invalid file type: {file.filename}")
            raise HTTPException(status_code=400, detail="Only PDF files are supported")

        # Save temporary file
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
            logger.warning(f"No '5. Interaction Flow' chapter found in PDF: {filename}")
            raise HTTPException(status_code=400, detail="PDF parsing failed, specified chapter not found")

        preflow = PreFlow(
            name=file.filename,
            description=f"Workflow parsed from PDF file {file.filename}",
            steps_md=pre_md
        )
        logger.info(f"PDF parsed successfully: {filename}, preflow_id={preflow.id}")
        return ParsePDFResponse(
            status="success",
            message="PDF file parsed successfully",
            content=preflow.model_dump_json()
        )
    except anyio.WouldBlock as e:
        logger.error(f"PDF parse server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF parsing failed: {str(e)}")
    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)
        if acquired:
            parse_pdf_semaphore.release()

plan_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_PLAN)))
@app.post("/plan", response_model=PlanResponse)
async def plan(request: PlanRequest, _: Any = Depends(RateLimiter(config, "plan"))):
    """
    Generate PSOP workflow from PreFlow and AgentCards
    """
    acquired = False
    try:
        plan_semaphore.acquire_nowait()
        acquired = True
        preflow_name = request.preflow.get("name", "unknown")
        agent_count = len(request.agent_cards)
        logger.info(f"Planning workflow from PreFlow: {preflow_name}, agent_cards={agent_count}")

        generator = PsopGenerator()
        workflow = generator.generate_psop_workflow(
            PreFlow.model_validate(request.preflow),
            [Parse(json.dumps(card), AgentCard()) for card in request.agent_cards]
        )
        save_handle.handle(workflow)
        logger.info(f"Workflow planned and saved: id={workflow.id}, name={workflow.name}, steps={len(workflow.steps)}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.SAVE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.SUCCESS,
            'details': workflow.model_dump(),
        })
        return PlanResponse(
            status="success",
            data=workflow.model_dump_json()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Plan server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        logger.error(f"Workflow planning failed: {e}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.SAVE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.FAILURE,
            'details': {"message": "PSOP planning failed"},
        })
        raise HTTPException(status_code=500, detail=f"PSOP planning failed: {str(e)}")
    finally:
        if acquired:
            plan_semaphore.release()


all_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_ALL_PSOPS)))


@app.get("/psops", response_model=PSOPListResponse)
async def get_all_psops(limit: int = 10, workflow_type: str = 'psop',
                        _: Any = Depends(RateLimiter(config, "get_all_psops"))):
    """
    Get all PSOP workflow list
    """
    acquired = False
    try:
        all_psop_semaphore.acquire_nowait()
        acquired = True
        logger.info(f"Listing PSOPs: limit={limit}, type={workflow_type}")
        recent_workflows = retrieval.list_recent_workflows(limit=limit, workflow_type=workflow_type)
        logger.info(f"Retrieved {len(recent_workflows)} PSOPs")

        return PSOPListResponse(
            status="success",
            count=len(recent_workflows),
            data=[wf.to_dict() for wf in recent_workflows]
        )
    except anyio.WouldBlock as e:
        logger.error(f"List PSOPs server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to list PSOPs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve PSOP list: {str(e)}")
    finally:
        if acquired:
            all_psop_semaphore.release()


one_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_ONE_PSOP)))


@app.get("/psops/{workflow_id}", response_model=PSOPDetailResponse)
async def get_psop_by_id(workflow_id: str, _: Any = Depends(RateLimiter(config, "get_psop_by_id"))):
    """
    Get PSOP workflow details by ID
    """
    acquired = False
    try:
        one_psop_semaphore.acquire_nowait()
        acquired = True
        logger.info(f"Getting PSOP by ID: {workflow_id}")
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            logger.warning(f"PSOP not found: {workflow_id}")
            raise HTTPException(status_code=404, detail=f"PSOP with ID {workflow_id} not found")

        logger.info(f"PSOP retrieved: id={workflow_id}, name={psop.name}")
        return PSOPDetailResponse(
            status="success",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Get PSOP server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PSOP {workflow_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve PSOP details: {str(e)}")
    finally:
        if acquired:
            one_psop_semaphore.release()


save_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_SAVE_PSOP)))


@app.post("/psops", status_code=201)
async def save_psop(request: SavePSOPRequest, _: Any = Depends(RateLimiter(config, "save_psop"))):
    """
    Save PSOP workflow
    """
    acquired = False
    try:
        save_psop_semaphore.acquire_nowait()
        acquired = True
        psop = PSOP.model_validate(request.psop)
        psop_name = psop.name or "unknown"
        logger.info(f"Saving PSOP: name={psop_name}, id={psop.id}")
        saved_id = save_handle.handle(psop)
        logger.info(f"PSOP saved successfully: id={saved_id}, name={psop_name}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.SAVE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.SUCCESS,
            'details': psop.model_dump(),
        })
        return JSONResponse(
            status_code=201,
            content={
                "status": "success",
                "message": "PSOP saved successfully",
                "workflow_id": saved_id
            }
        )
    except anyio.WouldBlock as e:
        logger.error(f"Save PSOP server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to save PSOP: {e}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.SAVE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.FAILURE,
            'details': {"message": "Failed to save PSOP"},
        })
        raise HTTPException(status_code=500, detail=f"Failed to save PSOP: {str(e)}")
    finally:
        if acquired:
            save_psop_semaphore.release()


delete_psop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_DELETE_PSOP)))


@app.delete("/psops/{workflow_id}", response_model=PSOPDeleteResponse)
async def delete_psop(workflow_id: str, _: Any = Depends(RateLimiter(config, "delete_psop"))):
    """
    Delete PSOP workflow by specified ID
    """
    acquired = False
    try:
        delete_psop_semaphore.acquire_nowait()
        acquired = True
        logger.info(f"Deleting PSOP: {workflow_id}")
        # First check if PSOP exists
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            logger.warning(f"PSOP not found for deletion: {workflow_id}")
            raise HTTPException(status_code=404, detail=f"PSOP with ID {workflow_id} not found")

        # Delete PSOP
        deleted = delete_handle.handle(workflow_id)
        if not deleted:
            raise HTTPException(status_code=500, detail="Failed to delete PSOP: file might not exist")

        logger.info(f"PSOP deleted successfully: {workflow_id}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.DELETE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.SUCCESS,
            'details': {"workflow_id": workflow_id, "name": psop.name},
        })
        return PSOPDeleteResponse(
            status="success",
            message=f"PSOP {workflow_id} deleted successfully"
        )
    except anyio.WouldBlock as e:
        logger.error(f"Delete PSOP server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete PSOP {workflow_id}: {e}")
        audit_logger.audit({
            'object_name': OperationObject.PSOP,
            'operation_name': OperationName.DELETE_PSOP,
            'level': LogLevel.MINOR,
            'result': OperationResult.FAILURE,
            'details': {"workflow_id": workflow_id, "error": str(e)},
        })
        raise HTTPException(status_code=500, detail=f"Failed to delete PSOP: {str(e)}")
    finally:
        if acquired:
            delete_psop_semaphore.release()


agent_cards_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_AGENT_CARDS)))


@app.get("/agent-cards", response_model=AgentCardResponse)
async def get_all_agent_cards(_: Any = Depends(RateLimiter(config, "get_all_agent_cards"))):
    """
    Get complete AgentCard list
    """
    acquired = False
    try:
        agent_cards_semaphore.acquire_nowait()
        acquired = True
        logger.info("Fetching agent cards")
        # Get all AgentCards
        agent_registry_factory = AgentRegistryClientFactory()
        agent_cards = agent_registry_factory.create_from_env().list_exact()
        logger.info(f"Retrieved {len(agent_cards)} agent cards")

        return AgentCardResponse(
            status="success",
            count=len(agent_cards),
            data=agent_cards
        )
    except anyio.WouldBlock as e:
        logger.error(f"List agent cards server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except FileNotFoundError as e:
        logger.error(f"Agent card config not found: {e}")
        raise HTTPException(status_code=404, detail=f"Configuration file not found: {str(e)}")
    except ValueError as e:
        logger.error(f"Agent card data format error: {e}")
        raise HTTPException(status_code=400, detail=f"Data format error: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to fetch agent cards: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve AgentCards: {str(e)}")
    finally:
        if acquired:
            agent_cards_semaphore.release()


generate_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_GENERATE_PSOP)))


@app.post("/generate-from-intent", response_model=IntentResponse)
async def generate_psop_from_intent(request: IntentRequest,
                                    _: Any = Depends(RateLimiter(config, "generate_psop_from_intent"))):
    """
    Generate PSOP workflow from natural language intent
    """
    acquired = False
    try:
        generate_semaphore.acquire_nowait()
        acquired = True
        intent_preview = request.user_intent[:80] + "..." if len(request.user_intent) > 80 else request.user_intent
        logger.info(f"Generating PSOP from intent: {intent_preview}")

        # Get AgentCards
        agent_registry_factory = AgentRegistryClientFactory()
        agent_cards = agent_registry_factory.create_from_env().list_exact()
        if not agent_cards:
            logger.warning("No agent cards available for intent generation")
            raise HTTPException(status_code=404, detail="No available AgentCards found")

        # Generate PSOP using IntentPsopGenerator
        generator = IntentPsopGenerator()
        psop = generator.generate_psop_from_intent(
            user_intent=request.user_intent,
            agent_cards=[Parse(json.dumps(agent), AgentCard()) for agent in agent_cards],
            workflow_name=request.workflow_name
        )
        logger.info(f"PSOP generated from intent: id={psop.id}, name={psop.name}, steps={len(psop.steps)}")

        # Optional: auto-save generated PSOP
        try:
            save_handle.handle(psop)
            logger.info(f"PSOP auto-saved: id={psop.id}")
            audit_logger.audit({
                'object_name': OperationObject.PSOP,
                'operation_name': OperationName.SAVE_PSOP,
                'level': LogLevel.MINOR,
                'result': OperationResult.SUCCESS,
                'details': psop.model_dump(),
            })
        except Exception as save_error:
            logger.warning(f"PSOP auto-save failed (does not affect response): {save_error}")
            audit_logger.audit({
                'object_name': OperationObject.PSOP,
                'operation_name': OperationName.SAVE_PSOP,
                'level': LogLevel.MINOR,
                'result': OperationResult.FAILURE,
                'details': {"message": "Failed to save PSOP"},
            })
        return IntentResponse(
            status="success",
            message="PSOP generated successfully",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Generate PSOP from intent server busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate PSOP from intent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate PSOP: {str(e)}")
    finally:
        if acquired:
            generate_semaphore.release()


retrieve_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PARALLEL_RETRIEVE_PSOP)))


@app.post("/retrieve-by-intent", response_model=RetrieveIntentResponse)
async def retrieve_psop_by_intent(request: RetrieveIntentRequest,
                                  _: Any = Depends(RateLimiter(config, "retrieve_psop_by_intent"))):
    """
    Retrieve the most suitable PSOP workflow based on natural language intent
    """
    acquired = False
    try:
        retrieve_semaphore.acquire_nowait()
        acquired = True
        logger.info(f"Starting PSOP retrieval based on intent: {request.user_intent}")

        # Use WorkflowRetrieval.retrieve_psop_by_intent method
        psop = retrieval.retrieve_psop_by_intent(request.user_intent)

        if not psop:
            return RetrieveIntentResponse(
                status="success",
                message="No matching PSOP found",
                data=None
            )

        logger.info(f"Successfully retrieved PSOP: {psop.name} (ID: {psop.id})")

        return RetrieveIntentResponse(
            status="success",
            message="PSOP retrieved successfully",
            data=psop.model_dump()
        )
    except anyio.WouldBlock as e:
        logger.error(f"Server is busy: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"Server is busy: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to retrieve PSOP based on intent: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve PSOP: {str(e)}")
    finally:
        if acquired:
            retrieve_semaphore.release()


@app.get("/rest/start_process_stream")
async def start_process_stream(psop_id: str):
    """
    SSE streaming workflow execution
    """
    if not psop_id:
        logger.warning("start_process_stream called without psop_id")
        raise HTTPException(status_code=400, detail="Missing psop_id parameter")

    logger.info(f"Starting workflow execution stream: psop_id={psop_id}")
    psop = retrieval.get_psop_by_id(psop_id)
    if not psop:
        logger.warning(f"PSOP not found for execution: {psop_id}")
        raise HTTPException(status_code=404, detail=f"PSOP with ID {psop_id} not found")

    logger.info(f"Workflow loaded: name={psop.name}, steps={len(psop.steps)}")
    agent_registry_factory = AgentRegistryClientFactory()
    all_agent_cards = agent_registry_factory.create_from_env().list_exact()
    agent_cards = [Parse(json.dumps(agent), AgentCard())  for agent in all_agent_cards]
    if not agent_cards:
        logger.warning("No agent cards available for workflow execution")
        raise HTTPException(status_code=404, detail="No available AgentCards found")

    async def event_generator():
        event_queue = queue.Queue()

        def push_callback(event_type: str, data: dict):
            try:
                # Serialize data, handle non-JSON-serializable objects
                serializable_data = {}
                for key, value in data.items():
                    if hasattr(value, 'model_dump'):
                        # If Pydantic model, use model_dump()
                        serializable_data[key] = value.model_dump()
                    elif hasattr(value, '__dict__'):
                        # If regular object, try to convert to dict
                        try:
                            serializable_data[key] = value.__dict__
                        except Exception:
                            serializable_data[key] = str(value)
                    elif isinstance(value, (tuple, list)):
                        # Handle lists and tuples
                        serializable_data[key] = []
                        for item in value:
                            if hasattr(item, 'model_dump'):
                                serializable_data[key].append(item.model_dump())
                            elif hasattr(item, '__dict__'):
                                try:
                                    serializable_data[key].append(item.__dict__)
                                except Exception:
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
                    "data": {"psop_id": psop_id, "message": "Starting workflow execution"}
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

        # Send initialization message
        init_event = {'type': 'init', 'data': {'psop_id': psop_id, 'message': 'Initializing execution engine'}}
        yield f"data: {json.dumps(init_event)}\n\n"

        # Keep sending events until workflow completes
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
