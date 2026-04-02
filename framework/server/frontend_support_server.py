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
        return jsonify({'error': '未提供文件'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "文件名为空"}), 400
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        return jsonify({"error": "仅支持 PDF 文件"}), 400
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
            return jsonify({"error": "PDF解析失败，未找到指定章节"}), 400
        
        preflow = PreFlow(
            name=file.filename,
            description=f"从PDF文件 {file.filename} 解析的工作流",
            steps_md=pre_md
        )
        return {
            "status": "success",
            "message": "PDF文件解析成功",
            "content": preflow.model_dump_json()
        }, 200
    except Exception as e:
        return jsonify({"error": f"解析失败：{str(e)}"}), 500
    finally:
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)


@app.route('/plan', methods=['POST'])
def plan():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400
        preflow_dict = data.get("preflow")
        agent_cards_list = data.get("agent_cards")

        if not preflow_dict or not agent_cards_list:
            return jsonify({
                "error": "缺少必要字段: task 和 steps 必须提供"
            }), 400
        generator = PsopGenerator()
        workflow = generator.generate_psop_workflow(PreFlow.model_validate(preflow_dict),
                                                    [AgentCard.model_validate(card) for card in agent_cards_list])
        return jsonify({
            "status": "success",
            "data": workflow.model_dump_json()
        }), 200
    except Exception as e:
        return jsonify({"error": f"规划失败 : {str(e)}"}), 500


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
        return jsonify({"error": f"获取PSOP列表失败: {str(e)}"}), 500


@app.route('/psops/<workflow_id>', methods=['GET'])
def get_psop_by_id(workflow_id):
    try:
        psop = retrieval.get_psop_by_id(workflow_id)
        if not psop:
            return jsonify({"error": f"未找到ID为 {workflow_id} 的PSOP"}), 404
        
        return jsonify({
            "status": "success",
            "data": psop.model_dump()
        }), 200
    except Exception as e:
        return jsonify({"error": f"获取PSOP详情失败: {str(e)}"}), 500


@app.route('/psops', methods=['POST'])
def save_psop():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400
        
        psop = PSOP.model_validate(data)
        saved_id = storage.save_psop(psop)
        
        return jsonify({
            "status": "success",
            "message": "PSOP保存成功",
            "workflow_id": saved_id
        }), 201
    except Exception as e:
        return jsonify({"error": f"保存PSOP失败: {str(e)}"}), 500


@app.route('/agent-cards', methods=['GET'])
def get_all_agent_cards():
    """
    获取全量AgentCard列表。
    
    逻辑：
    1. 读取配置文件 config/agent_cards.yaml
    2. 如果配置文件中包含 source_url 字段，则从该URL获取AgentCard
    3. 否则，使用配置文件中的 agents 字段
    
    Returns:
        JSON响应，包含AgentCard列表和来源信息
    """
    try:
        # 获取所有AgentCard
        agent_cards = agent_lib.get_all_agent_cards()
        
        # 将AgentCard转换为字典格式
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
            "error": f"配置文件不存在: {str(e)}"
        }), 404
    except ValueError as e:
        return jsonify({
            "error": f"数据格式错误: {str(e)}"
        }), 400
    except Exception as e:
        return jsonify({
            "error": f"获取AgentCard失败: {str(e)}"
        }), 500


@app.route('/generate-from-intent', methods=['POST'])
def generate_psop_from_intent():
    """
    根据自然语言意图生成PSOP工作流。
    
    请求体格式:
    {
        "user_intent": "自然语言描述的业务意图",
        "workflow_name": "可选的工作流名称"
    }
    
    返回:
        JSON响应，包含生成的PSOP工作流
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "请求体为空"}), 400
        
        user_intent = data.get("user_intent")
        workflow_name = data.get("workflow_name")
        
        if not user_intent:
            return jsonify({"error": "缺少必要字段: user_intent"}), 400
        
        # 获取AgentCards（复用agent-cards接口的逻辑）
        agent_cards = agent_lib.get_all_agent_cards()
        if not agent_cards:
            return jsonify({"error": "未找到可用的AgentCard"}), 404
        
        # 使用IntentPsopGenerator生成PSOP
        generator = IntentPsopGenerator()
        psop = generator.generate_psop_from_intent(
            user_intent=user_intent,
            agent_cards=agent_cards,
            workflow_name=workflow_name
        )
        
        # 可选：自动保存生成的PSOP
        try:
            storage.save_psop(psop)
        except Exception as save_error:
            logger.warning(f"Failed to save PSOP (does not affect response): {save_error}")
        
        return jsonify({
            "status": "success",
            "message": "PSOP生成成功",
            "data": psop.model_dump()
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to generate PSOP based on intent: {e}")
        return jsonify({"error": f"生成PSOP失败: {str(e)}"}), 500


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
