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

# tests/test_frontend_support_server.py
import pytest
import json
from unittest.mock import patch, MagicMock
from io import BytesIO

# 在导入app之前设置测试配置
import os

os.environ['TESTING'] = 'True'

from orchestrate.server.frontend_support_server import app


@pytest.fixture
def client():
    """创建Flask测试客户端"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_storage():
    """模拟WorkflowStorage"""
    with patch('orchestrate.server.frontend_support_server.storage') as mock:
        yield mock


@pytest.fixture
def mock_retrieval():
    """模拟WorkflowRetrieval"""
    with patch('orchestrate.server.frontend_support_server.retrieval') as mock:
        yield mock


@pytest.fixture
def mock_agent_lib():
    """模拟AgentCardLib"""
    with patch('orchestrate.server.frontend_support_server.agent_lib') as mock:
        yield mock


@pytest.fixture
def mock_parser():
    """模拟SolutionPackageParser"""
    with patch('orchestrate.server.frontend_support_server.SolutionPackageParser') as MockParser:
        mock_instance = MockParser.return_value
        yield mock_instance


class TestParsePdfEndpoint:
    """测试 /parse-pdf 端点"""

    def test_parse_pdf_missing_file(self, client):
        """测试未提供文件"""
        response = client.post('/parse-pdf')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data

    def test_parse_pdf_empty_filename(self, client):
        """测试空文件名"""
        response = client.post('/parse-pdf', data={'file': (BytesIO(), '')})
        assert response.status_code == 400

    def test_parse_pdf_wrong_extension(self, client):
        """测试非PDF文件"""
        response = client.post('/parse-pdf', data={
            'file': (BytesIO(b'test'), 'test.txt')
        })
        assert response.status_code == 400
        data = json.loads(response.data)
        assert '仅支持 PDF' in data['error']

    def test_parse_pdf_success(self, client, mock_parser):
        """测试成功解析PDF"""
        mock_parser.parse_pdf_chapter.return_value = "# Test Markdown"

        with patch('orchestrate.server.frontend_support_server.PreFlow') as MockPreFlow:
            mock_preflow = MagicMock()
            mock_preflow.model_dump_json.return_value = '{"name": "test"}'
            MockPreFlow.return_value = mock_preflow

            response = client.post('/parse-pdf', data={
                'file': (BytesIO(b'%PDF-1.4 test'), 'test.pdf')
            })

            # 注意：原代码返回的是dict而非jsonify，这里测试实际行为
            assert response.status_code == 200

    def test_parse_pdf_parse_failure(self, client, mock_parser):
        """测试解析失败"""
        mock_parser.parse_pdf_chapter.return_value = None

        response = client.post('/parse-pdf', data={
            'file': (BytesIO(b'%PDF-1.4 test'), 'test.pdf')
        })

        assert response.status_code == 400
        data = json.loads(response.data)
        assert '解析失败' in data['error']


class TestPlanEndpoint:
    """测试 /plan 端点"""

    def test_plan_empty_content(self, client):
        """测试空请求体"""
        response = client.post('/plan', content_type='application/json')
        assert response.status_code == 500

    def test_plan_empty_body(self, client):
        """测试空请求体"""
        response = client.post('/plan', data=json.dumps({}), content_type='application/json')
        assert response.status_code == 400

    def test_plan_missing_fields(self, client):
        """测试缺少必要字段"""
        response = client.post('/plan',
                               data=json.dumps({"preflow": {}}),
                               content_type='application/json'
                               )
        assert response.status_code == 400

    def test_plan_success(self, client, mock_storage):
        """测试成功规划"""
        with patch('orchestrate.server.frontend_support_server.PsopGenerator') as MockGen, \
                patch('orchestrate.server.frontend_support_server.PreFlow') as MockPreFlow, \
                patch('orchestrate.server.frontend_support_server.AgentCard') as MockCard:
            mock_gen = MockGen.return_value
            mock_workflow = MagicMock()
            mock_workflow.model_dump_json.return_value = '{"id": "123"}'
            mock_gen.generate_psop_workflow.return_value = mock_workflow
            mock_storage.save_psop.return_value = "123"

            MockPreFlow.model_validate.return_value = MagicMock()
            MockCard.model_validate.return_value = MagicMock()

            response = client.post('/plan',
                                   data=json.dumps({
                                       "preflow": {"name": "test", "description": "desc", "steps_md": "# test"},
                                       "agent_cards": [{"name": "agent1"}]
                                   }),
                                   content_type='application/json'
                                   )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['status'] == 'success'


class TestPsopsEndpoints:
    """测试 /psops 相关端点"""

    def test_get_psops_list(self, client, mock_retrieval):
        """测试获取PSOP列表"""
        mock_wf = MagicMock()
        mock_wf.to_dict.return_value = {"id": "123", "name": "test"}
        mock_retrieval.list_recent_workflows.return_value = [mock_wf]

        response = client.get('/psops?limit=5&workflow_type=psop')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 1

    def test_get_psop_by_id_found(self, client, mock_retrieval):
        """测试根据ID获取存在的PSOP"""
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = {"id": "123", "name": "test"}
        mock_retrieval.get_psop_by_id.return_value = mock_psop

        response = client.get('/psops/123')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

    def test_get_psop_by_id_not_found(self, client, mock_retrieval):
        """测试根据ID获取不存在的PSOP"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.get('/psops/nonexistent')
        assert response.status_code == 404

    def test_save_psop_success(self, client, mock_storage):
        """测试保存PSOP"""
        with patch('orchestrate.server.frontend_support_server.PSOP') as MockPSOP:
            mock_psop = MagicMock()
            mock_psop.model_dump.return_value = {"id": "123"}
            MockPSOP.model_validate.return_value = mock_psop
            mock_storage.save_psop.return_value = "123"

            response = client.post('/psops',
                                   data=json.dumps({"id": "123", "name": "test"}),
                                   content_type='application/json'
                                   )

            assert response.status_code == 201

    def test_delete_psop_success(self, client, mock_retrieval, mock_storage):
        """测试删除PSOP"""
        mock_psop = MagicMock()
        mock_retrieval.get_psop_by_id.return_value = mock_psop
        mock_storage.delete_psop.return_value = True

        response = client.delete('/psops/123')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

    def test_delete_psop_not_found(self, client, mock_retrieval):
        """测试删除不存在的PSOP"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.delete('/psops/nonexistent')
        assert response.status_code == 404


class TestAgentCardsEndpoint:
    """测试 /agent-cards 端点"""

    def test_get_agent_cards_success(self, client, mock_agent_lib):
        """测试成功获取AgentCard列表"""
        mock_card = MagicMock()
        mock_card.model_dump.return_value = {"name": "agent1", "url": "http://test"}
        mock_agent_lib.get_all_agent_cards.return_value = [mock_card]

        response = client.get('/agent-cards')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['count'] == 1
        assert data['data'][0]['name'] == 'agent1'

    def test_get_agent_cards_config_not_found(self, client, mock_agent_lib):
        """测试配置文件不存在"""
        mock_agent_lib.get_all_agent_cards.side_effect = FileNotFoundError("config not found")

        response = client.get('/agent-cards')
        assert response.status_code == 404

    def test_get_agent_cards_value_error(self, client, mock_agent_lib):
        """测试数据格式错误"""
        mock_agent_lib.get_all_agent_cards.side_effect = ValueError("invalid format")

        response = client.get('/agent-cards')
        assert response.status_code == 400


class TestIntentEndpoints:
    """测试意图相关端点"""

    def test_generate_from_intent_success(self, client, mock_agent_lib):
        """测试根据意图生成PSOP成功"""
        mock_card = MagicMock()
        mock_card.model_dump.return_value = {"name": "agent1"}
        mock_agent_lib.get_all_agent_cards.return_value = [mock_card]

        with patch('orchestrate.server.frontend_support_server.IntentPsopGenerator') as MockGen:
            mock_gen = MockGen.return_value
            mock_psop = MagicMock()
            mock_psop.model_dump.return_value = {"id": "123", "name": "generated"}
            mock_gen.generate_psop_from_intent.return_value = mock_psop

            response = client.post('/generate-from-intent',
                                   data=json.dumps({"user_intent": "帮我创建一个工作流"}),
                                   content_type='application/json'
                                   )

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['status'] == 'success'

    def test_generate_from_intent_missing_intent(self, client):
        """测试缺少user_intent字段"""
        response = client.post('/generate-from-intent',
                               data=json.dumps({}),
                               content_type='application/json'
                               )
        assert response.status_code == 400

    def test_retrieve_by_intent_success(self, client, mock_retrieval):
        """测试根据意图检索成功"""
        mock_psop = MagicMock()
        mock_psop.model_dump.return_value = {"id": "123", "name": "matched"}
        mock_psop.id = "123"
        mock_psop.name = "matched"
        mock_retrieval.retrieve_psop_by_intent.return_value = mock_psop

        response = client.post('/retrieve-by-intent',
                               data=json.dumps({"user_intent": "查找工作流"}),
                               content_type='application/json'
                               )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'success'

    def test_retrieve_by_intent_no_match(self, client, mock_retrieval):
        """测试根据意图检索无匹配"""
        mock_retrieval.retrieve_psop_by_intent.return_value = None

        response = client.post('/retrieve-by-intent',
                               data=json.dumps({"user_intent": "找不到"}),
                               content_type='application/json'
                               )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['data'] is None


class TestStartProcessStreamEndpoint:
    """测试 /rest/start_process_stream 端点"""

    def test_stream_missing_psop_id(self, client):
        """测试缺少psop_id参数"""
        response = client.get('/rest/start_process_stream')
        assert response.status_code == 400

    def test_stream_psop_not_found(self, client, mock_retrieval):
        """测试PSOP不存在"""
        mock_retrieval.get_psop_by_id.return_value = None

        response = client.get('/rest/start_process_stream?psop_id=nonexistent')
        assert response.status_code == 404

    def test_stream_no_agent_cards(self, client, mock_retrieval, mock_agent_lib):
        """测试没有可用的AgentCard"""
        mock_psop = MagicMock()
        mock_retrieval.get_psop_by_id.return_value = mock_psop
        mock_agent_lib.get_all_agent_cards.return_value = []

        response = client.get('/rest/start_process_stream?psop_id=123')
        assert response.status_code == 404

    def test_stream_response_format(self, client, mock_retrieval, mock_agent_lib):
        """测试SSE响应格式"""
        mock_psop = MagicMock()
        mock_retrieval.get_psop_by_id.return_value = mock_psop

        mock_card = MagicMock()
        mock_agent_lib.get_all_agent_cards.return_value = [mock_card]

        # 模拟引擎执行
        with patch('orchestrate.server.frontend_support_server.DynamicWorkflowEngine') as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.run = MagicMock()
            mock_engine.run.return_value = []

            response = client.get('/rest/start_process_stream?psop_id=123')

            assert response.status_code == 200
            assert response.mimetype == 'text/event-stream'
            assert response.headers['Cache-Control'] == 'no-cache'
