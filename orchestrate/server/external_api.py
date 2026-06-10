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

"""
External API Module

Public-facing API for other systems to integrate with the Orchestration Center.
Provides SOP-based orchestration, intent-based orchestration, workflow search, and workflow execution.

Endpoints:
  POST /api/v1/orchestrate/sop           — SOP-based orchestration (JSON text or PDF/TXT/MD file upload)
  POST /api/v1/orchestrate/intent        — Intent-based orchestration
  GET  /api/v1/orchestrate/psop/{id}     — Get PSOP workflow by ID
  POST /api/v1/orchestrate/search        — Search/retrieve workflows by natural language intent
  POST /api/v1/orchestrate/execute       — Auto-orchestrate + execute (SSE)
  GET  /api/v1/orchestrate/execute/{id}  — Execute a known PSOP (SSE)
  GET  /api/v1/executions                — List execution records
  GET  /api/v1/executions/{id}           — Get execution result
"""

import os
import re
import tempfile
from typing import Any, Optional

import anyio
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, Depends
from loguru import logger
from pydantic import BaseModel, Field

from common.config import FLOW_CTL_START_PROCESS_STREAM, FLOW_CTL_PLAN, FLOW_CTL_GENERATE_PSOP, MAX_FILE_SIZE_BYTES
from common.custom.default_handle import HandlerRegistry
from common.custom.interface_type import InterfaceType
from orchestrate.core.intent_psop_generator import IntentPsopGenerator
from orchestrate.core.model.preflow import PreFlow
from orchestrate.core.model.psop import PSOP
from orchestrate.core.psop_generator import PsopGenerator
from orchestrate.server.shared_handlers import SharedHandlers
from orchestrate.server.sse_executor import run_psop_sse
from orchestrate.server.response_utils import ok, created, get_agent_cards
from orchestrate.server.middleware import RateLimiter
from orchestrate.solution_package.parse_flow import SolutionPackageParser
from common.util.config_util import get_conf

router = APIRouter(prefix="/api/v1")
config = get_conf()

execute_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_START_PROCESS_STREAM, 50)))
sop_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_PLAN, 10)))
intent_semaphore = anyio.Semaphore(int(config.get(FLOW_CTL_GENERATE_PSOP, 10)))


# ═══════════════════════════════════════════════════════════════════════════════
# Request Models
# ═══════════════════════════════════════════════════════════════════════════════

class SOPOrchestrateRequest(BaseModel):
    sop_content: str = Field(..., min_length=1, max_length=50000, description="Natural language SOP steps (markdown text)")
    name: Optional[str] = Field(None, max_length=256, description="Optional workflow name")


class IntentOrchestrateRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=10000, description="Natural language intent or task description")
    name: Optional[str] = Field(None, max_length=256, description="Optional workflow name")


class ExecuteRequest(BaseModel):
    task: str = Field(..., min_length=1, max_length=10000, description="Task description. System will search existing PSOPs first, auto-generate if none found")
    name: Optional[str] = Field(None, max_length=256, description="Optional workflow name for auto-generation")


class SearchRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=10000, description="Natural language intent to search for matching workflows")
    top_n: Optional[int] = Field(5, description="Maximum number of results to return", ge=1, le=20)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SOP-based orchestration
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/orchestrate/sop", status_code=201)
async def orchestrate_sop(
    request: Request,
    file: Optional[UploadFile] = File(None),
    name: Optional[str] = Form(None),
    _: Any = Depends(RateLimiter(config, "sop_orchestrate"))
):
    """
    SOP-based orchestration.

    Accepts either:
    - JSON body with `sop_content` (natural language SOP text)
    - File upload (PDF/TXT/MD SolutionPackage), with optional `name` form field

    When both JSON body and file are provided, the file takes precedence.

    Returns a generated PSOP workflow.
    """
    acquired = False
    try:
        sop_semaphore.acquire_nowait()
        acquired = True

        sop_text = ""
        workflow_name = name
        body = None

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                raw_body = await request.json()
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid JSON body")
            body = SOPOrchestrateRequest.model_validate(raw_body)

        if file:
            filename = file.filename or ""
            if not re.match(r'^[\w\-. ]{1,128}\.(pdf|txt|md)$', filename, re.IGNORECASE):
                raise HTTPException(status_code=400, detail=f"Invalid filename: {filename}")
            content = await file.read()
            if len(content) > MAX_FILE_SIZE_BYTES:
                raise HTTPException(status_code=413, detail="File too large")

            ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

            if ext == 'pdf':
                if not content.startswith(b'%PDF-'):
                    raise HTTPException(status_code=400, detail="Not a valid PDF file")
                tmp_file_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                        tmp_file_path = tmp.name
                        tmp.write(content)
                    parser = SolutionPackageParser()
                    pre_md = parser.parse_pdf_chapter(tmp_file_path, "5. Interaction Flow")
                    if not pre_md:
                        raise HTTPException(
                            status_code=400,
                            detail="Chapter '5. Interaction Flow' not found in PDF"
                        )
                    sop_text = pre_md
                    workflow_name = workflow_name or filename
                except HTTPException:
                    raise
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"PDF parsing failed: {e}")
                except Exception as e:
                    logger.error(f"PDF parsing failed: {e}")
                    raise HTTPException(status_code=500, detail=f"PDF parsing failed: {e}")
                finally:
                    if tmp_file_path and os.path.exists(tmp_file_path):
                        os.unlink(tmp_file_path)
            else:
                sop_text = content.decode('utf-8', errors='replace')
                workflow_name = workflow_name or filename.rsplit('.', 1)[0]
        elif body:
            sop_text = body.sop_content
            workflow_name = workflow_name or body.name
        else:
            raise HTTPException(status_code=400, detail="Either sop_content or file upload is required")

        if not sop_text or not sop_text.strip():
            raise HTTPException(status_code=400, detail="SOP content is empty")

        agent_cards = await get_agent_cards()
        preflow = PreFlow(name=workflow_name or "SOP Workflow", steps_md=sop_text)
        generator = PsopGenerator()
        psop = generator.generate_psop_workflow(preflow, agent_cards)
        psop.user_intent = sop_text[:200]
        psop.related_preflow = preflow.id

        save_handler = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        save_handler.handle(psop)
        return created(data=psop.model_dump(), message="PSOP generated and saved")
    except anyio.WouldBlock:
        raise HTTPException(status_code=503, detail="Server is busy")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"SOP orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if acquired:
            sop_semaphore.release()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Intent-based orchestration
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/orchestrate/intent", status_code=201)
async def orchestrate_intent(
    request: Request,
    body: IntentOrchestrateRequest,
    _: Any = Depends(RateLimiter(config, "intent_orchestrate"))
):
    """
    Intent-based orchestration.

    Generates a PSOP workflow directly from a natural language intent/task description.
    No SOP steps required — the LLM plans the workflow autonomously.
    """
    acquired = False
    try:
        intent_semaphore.acquire_nowait()
        acquired = True
        agent_cards = await get_agent_cards()
        generator = IntentPsopGenerator()
        psop = generator.generate_psop_from_intent(body.intent, agent_cards, body.name)

        save_handler = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
        save_handler.handle(psop)
        return created(data=psop.model_dump(), message="PSOP generated and saved")
    except anyio.WouldBlock:
        raise HTTPException(status_code=503, detail="Server is busy")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Intent orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if acquired:
            intent_semaphore.release()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Workflow retrieval
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/orchestrate/psop/{psop_id}")
async def get_psop(
    psop_id: str,
    _: Any = Depends(RateLimiter(config, "get_workflow"))
):
    """
    Get a single PSOP workflow by ID (full detail).

    Returns the complete PSOP including all steps, tasks, and conditions.
    """
    try:
        retrieval = SharedHandlers.retrieval()
        psop = retrieval.get_psop_by_id(psop_id)
        if not psop:
            raise HTTPException(status_code=404, detail=f"PSOP {psop_id} not found")
        return ok(data=psop.model_dump(), message=f"PSOP {psop_id} retrieved")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get PSOP: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get PSOP: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Search/retrieve workflows
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/orchestrate/search")
async def search_workflows(
    request: Request,
    body: SearchRequest,
    _: Any = Depends(RateLimiter(config, "retrieve_by_intent"))
):
    """
    Search for matching workflows by natural language intent.

    Returns a ranked list of the top N most relevant PSOP workflows
    (summary only: id, name, description, tags, created_at, user_intent).
    """
    try:
        retrieval = SharedHandlers.retrieval()
        results = retrieval.retrieve_psop_by_intent_topn(body.intent, body.top_n or 5)
        return ok(data=[r.to_dict() for r in results], message=f"Found {len(results)} matching workflow(s)")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Auto-orchestrate + execute (composite)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/orchestrate/execute")
async def execute_workflow(
    request: Request,
    body: ExecuteRequest,
    lang: str = Query(None, description="Language for agent responses (zh/en)"),
    _: Any = Depends(RateLimiter(config, "ext_execute_auto"))
):
    """
    Auto-orchestrate and execute.

    Given a task description:
    1. Search for existing matching PSOPs
    2. If found, execute the best match
    3. If not found, auto-generate a new PSOP then execute it

    Returns an SSE stream with execution progress and results.
    """
    acquired = False
    try:
        execute_semaphore.acquire_nowait()
        acquired = True
        retrieval = SharedHandlers.retrieval()
        psop = retrieval.retrieve_psop_by_intent(body.task)

        if not psop:
            logger.info(f"No existing PSOP found for task, auto-generating...")
            try:
                agent_cards = await get_agent_cards()
                generator = IntentPsopGenerator()
                psop = generator.generate_psop_from_intent(body.task, agent_cards, body.name)
                save_handler = HandlerRegistry.get_handler(InterfaceType.SAVE_PSOP)
                save_handler.handle(psop)
                logger.info(f"Auto-generated PSOP: {psop.id}")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Auto-generation failed: {e}")

        agent_cards = await get_agent_cards()
        return await run_psop_sse(psop, agent_cards, runtime_intent=body.task, lang=lang)
    except anyio.WouldBlock:
        raise HTTPException(status_code=503, detail="Server is busy")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise HTTPException(status_code=500, detail="Workflow execution failed")
    finally:
        if acquired:
            execute_semaphore.release()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Execute known PSOP
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/orchestrate/execute/{psop_id}")
async def execute_psop_by_id(
    request: Request,
    psop_id: str,
    user_intent: str = Query(None, description="Runtime user intent for context injection"),
    lang: str = Query(None, description="Language for agent responses (zh/en)"),
    _: Any = Depends(RateLimiter(config, "ext_execute_by_id"))
):
    """
    Execute a known PSOP workflow by ID.

    Returns an SSE stream with execution progress and results.
    """
    acquired = False
    try:
        execute_semaphore.acquire_nowait()
        acquired = True
        retrieval = SharedHandlers.retrieval()
        psop = retrieval.get_psop_by_id(psop_id)
        if not psop:
            raise HTTPException(status_code=404, detail=f"PSOP {psop_id} not found")
        return await run_psop_sse(psop, await get_agent_cards(), runtime_intent=user_intent, lang=lang)
    except anyio.WouldBlock:
        raise HTTPException(status_code=503, detail="Server is busy")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execution by ID failed: {e}")
        raise HTTPException(status_code=500, detail="Workflow execution failed")
    finally:
        if acquired:
            execute_semaphore.release()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Execution records
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/executions")
async def list_executions(
    _: Any = Depends(RateLimiter(config, "list_executions"))
):
    """
    List execution records (summary only).

    Returns execution records sorted by start time descending.
    Each record includes: execution_id, psop_id, psop_name, status, timestamps.
    """
    try:
        handler = HandlerRegistry.get_handler(InterfaceType.LIST_EXECUTION_RECORDS)
        records = handler.handle()
        return ok(data=records, message=f"Found {len(records)} execution record(s)")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list execution records: {e}")
        raise HTTPException(status_code=500, detail="Failed to list execution records")


@router.get("/executions/{execution_id}")
async def get_execution(
    execution_id: str,
    _: Any = Depends(RateLimiter(config, "get_execution"))
):
    """
    Get execution result by execution ID.
    """
    try:
        handler = HandlerRegistry.get_handler(InterfaceType.GET_EXECUTION_RECORD)
        record = handler.handle(execution_id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")
        return ok(data=record.model_dump() if hasattr(record, 'model_dump') else record)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution record: {e}")
        raise HTTPException(status_code=500, detail="Failed to get execution record")
