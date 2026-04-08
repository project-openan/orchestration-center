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

from a2a.types import AgentCard
from flask import Flask, request, jsonify
from loguru import logger
from flask_cors import CORS

from framework.orchestration.model.preflow import PreFlow
from framework.orchestration.model.psop import PSOP
from framework.orchestration.psop_generator import PsopGenerator
from framework.orchestration.intent_psop_generator import IntentPsopGenerator
from framework.orchestration.persistence import WorkflowStorage
from framework.orchestration.retrieval import WorkflowRetrieval
from framework.solution_package.parse_flow import SolutionPackageParser
from framework.agentcard_lib import AgentCardLib

app = Flask(__name__)
CORS(app)

storage = WorkflowStorage()
retrieval = WorkflowRetrieval(storage)
agent_lib = AgentCardLib()


@app.route('/parse-pdf', methods=['POST'])
def parse_pdf():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "File name is empty"}), 400
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "Only PDF files are supported"}), 400
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        file.save(tmp.name)
        tmp_file_path = tmp.name

    try:
        parser = SolutionPackageParser()
        pre_md = parser.parse_pdf_chapter(
            tmp_file_path,
            "5. Interaction Flow"
        )
        if not pre_md:
            return jsonify({"error": "PDF parsing failed, specified chapter not found"}), 400
        
        preflow = PreFlow(
            name=file.filename,
            description=f"Workflow parsed from PDF file {file.filename}",
            steps_md=pre_md
        )
        return {
            "status": "success",
            "message": "PDF file parsed successfully",
            "content": preflow.model_dump_json()
        }, 200
    except Exception as e:
        return jsonify({"error": f"Parsing failed: {str(e)}"}), 500
    finally:
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)


@app.route('/plan', methods=['POST'])
def plan():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is empty"}), 400
        preflow_dict = data.get("preflow")
        agent_cards_list = data.get("agent_cards")

        if not preflow_dict or not agent_cards_list:
            return jsonify({
                "error": "Missing required fields: task and steps must be provided"
            }), 400
        generator = PsopGenerator()
        workflow = generator.generate_psop_workflow(PreFlow.model_validate(preflow_dict),
                                                    [AgentCard.model_validate(card) for card in agent_cards_list])
        return jsonify({
            "status": "success",
            "data": workflow.model_dump_json()
        }), 200
    except Exception as e:
        return jsonify({"error": f"Planning failed: {str(e)}"}), 500


@app.route('/psops', methods=['GET'])
def get_all_psops():
    try:
        limit = request.args.get('limit', default=10, type=int)
        workflow_type = request.args.get('workflow_type', default='psop', type=str)
        
        recent_workflows = retrieval.list_recent_workflows(limit=limit, workflow_type=workflow_type)
        
        return jsonify({
            "status": "success",
            "count": len(recent_workflows),
            "data": [wf.to_dict() for wf in recent_workflows]
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get PSOP list: {str(e)}"}), 500


@app.route('/psops/<workflow_id>', methods=['GET'])
def get_psop_by_id(workflow_id):
    try:
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            return jsonify({"error": f"PSOP with ID {workflow_id} not found"}), 404
        
        return jsonify({
            "status": "success",
            "data": psop.model_dump()
        }), 200
    except Exception as e:
        return jsonify({"error": f"Failed to get PSOP details: {str(e)}"}), 500


@app.route('/psops', methods=['POST'])
def save_psop():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is empty"}), 400
        
        psop = PSOP.model_validate(data)
        saved_id = storage.save_psop(psop)
        
        return jsonify({
            "status": "success",
            "message": "PSOP saved successfully",
            "workflow_id": saved_id
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to save PSOP: {str(e)}"}), 500


@app.route('/agent-cards', methods=['GET'])
def get_all_agent_cards():
    """
    Get full list of AgentCards.
    
    Logic:
    1. Read configuration file config/agent_cards.yaml
    2. If the configuration file contains source_url field, fetch AgentCards from that URL
    3. Otherwise, use the agents field in the configuration file
    
    Returns:
        JSON response containing AgentCard list and source information
    """
    try:
        # Get all AgentCards
        agent_cards = agent_lib.get_all_agent_cards()
        
        # Convert AgentCards to dictionary format
        agent_cards_data = []
        for card in agent_cards:
            card_dict = card.model_dump()
            agent_cards_data.append(card_dict)

        return jsonify({
            "status": "success",
            "count": len(agent_cards_data),
            "data": agent_cards_data
        }), 200
        
    except FileNotFoundError as e:
        return jsonify({
            "error": f"Configuration file not found: {str(e)}"
        }), 404
    except ValueError as e:
        return jsonify({
            "error": f"Data format error: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "error": f"Failed to get AgentCard: {str(e)}"
        }), 500


@app.route('/generate-from-intent', methods=['POST'])
def generate_psop_from_intent():
    """
    Generate PSOP workflow from natural language intent.
    
    Request body format:
    {
        "user_intent": "Business intent described in natural language",
        "workflow_name": "Optional workflow name"
    }
    
    Returns:
        JSON response containing the generated PSOP workflow
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body is empty"}), 400
        
        user_intent = data.get("user_intent")
        workflow_name = data.get("workflow_name")
        
        if not user_intent:
            return jsonify({"error": "Missing required field: user_intent"}), 400
        
        # Get AgentCards (reuse logic from agent-cards endpoint)
        agent_cards = agent_lib.get_all_agent_cards()
        if not agent_cards:
            return jsonify({"error": "No available AgentCard found"}), 404
        
        # 使用IntentPsopGenerator生成PSOP
        generator = IntentPsopGenerator()
        psop = generator.generate_psop_from_intent(
            user_intent=user_intent,
            agent_cards=agent_cards,
            workflow_name=workflow_name
        )
        
        # Optional: automatically save the generated PSOP
        try:
            storage.save_psop(psop)
        except Exception as save_error:
            logger.warning(f"Failed to save PSOP (does not affect response): {save_error}")
        
        return jsonify({
            "status": "success",
            "message": "PSOP generated successfully",
            "data": psop.model_dump()
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to generate PSOP based on intent: {e}")
        return jsonify({"error": f"Failed to generate PSOP: {str(e)}"}), 500


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info(" PSOP Server Interface")
    logger.info("=" * 50)
    logger.info(" POST /parse-pdf - Upload PDF file and parse")
    logger.info(" POST /plan - Submit task and steps, get planning result")
    logger.info("")
    logger.info(" PSOP Management Endpoints:")
    logger.info(" GET /psops - Get PSOP list")
    logger.info(" GET /psops/<id> - Get PSOP details by ID")
    logger.info(" POST /psops - Save PSOP")
    logger.info("")
    logger.info(" AgentCard Management Endpoints:")
    logger.info(" GET /agent-cards - Get full list of AgentCards")
    logger.info("")
    logger.info(" Intent Generation Endpoint:")
    logger.info(" POST /generate-from-intent - Generate PSOP from natural language intent")
    logger.info("")
    logger.info(" Server running at: http://localhost:60000")
    logger.info(" For detailed documentation, please refer to: PSOP_API_DOCUMENTATION.md")
    logger.info("=" * 50)
    app.run(host='localhost', port=60000, debug=True)
