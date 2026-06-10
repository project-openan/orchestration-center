// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
//
//    Licensed under the Apache License, Version 2.0 (the "License"); you may
//    not use this file except in compliance with the License. You may obtain
//    a copy of the License at
//
//         http://www.apache.org/licenses/LICENSE-2.0
//
//    Unless required by applicable law or agreed to in writing, software
//    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
//    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
//    License for the specific language governing permissions and limitations
//    under the License.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';
import {
  getBaseUrl,
  defaultIp,
  defaultPort,
  defaultGateway,
  getAgentCards,
  getWorkflow,
  getWorkflowById,
  createWorkflow,
  delWorkflowById,
  getTemplates,
  importTemplate,
  parsePdf,
  handlePlan,
  generateWorkflowFromIntent,
  getStartProcessStreamUrl,
  matchWorkflows,
  getExecutionRecords,
  getExecutionRecord,
  deleteExecutionRecord
} from './api';

// Mock axios
vi.mock('axios', () => {
  const mockApi = {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  };
  return {
    default: {
      create: vi.fn(() => mockApi),
      get: vi.fn(),
      post: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    }
  };
});

describe('api service', () => {
  const mockLocalStorage = (() => {
    let store = {};
    return {
      getItem: vi.fn((key) => store[key] || null),
      setItem: vi.fn((key, value) => { store[key] = value.toString(); }),
      removeItem: vi.fn((key) => { delete store[key]; }),
      clear: vi.fn(() => { store = {}; }),
    };
  })();

  beforeEach(() => {
    vi.stubGlobal('localStorage', mockLocalStorage);
    vi.clearAllMocks();
    mockLocalStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('getBaseUrl', () => {
    it('should return default URL when localStorage is empty', () => {
      const url = getBaseUrl();
      expect(url).toBe(`http://${defaultIp}:${defaultPort}`);
    });

    it('should return custom URL when localStorage has config', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({ ip: '192.168.1.1', port: '8080' }));
      const url = getBaseUrl();
      expect(url).toBe('http://192.168.1.1:8080');
    });

    it('should return default IP if port is missing in config', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({ ip: '192.168.1.1' }));
      const url = getBaseUrl();
      expect(url).toBe(`http://192.168.1.1:${defaultPort}`);
    });

    it('should use independent nginx URL when mode is nginx', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({
        mode: 'nginx',
        ip: '192.168.1.1',
        port: '8080',
        nginxUrl: 'http://gateway.example.com/orchestration/'
      }));
      const url = getBaseUrl();
      expect(url).toBe('http://gateway.example.com/orchestration');
    });

    it('should use default gateway when nginx URL is missing', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({
        mode: 'nginx',
        ip: '192.168.1.1',
        port: '8080'
      }));
      const url = getBaseUrl();
      expect(url).toBe(defaultGateway);
    });

    it('should handle malformed JSON in localStorage', () => {
      mockLocalStorage.setItem('server_config', 'invalid json');
      const url = getBaseUrl();
      expect(url).toBe(`http://${defaultIp}:${defaultPort}`);
    });
  });

  describe('API requests using the api instance', () => {
    // Note: The 'api' instance is created inside api.js. 
    // Since vi.mock('axios') is hoisted, axios.create will return our mockApi.
    // However, the interceptors are applied at module load time.

    it('getAgentCards should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: 'cards' });

      await getAgentCards();
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/agent-cards'));
    });

    it('getWorkflow should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: 'workflows' });

      await getWorkflow();
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/rest/v1/orchestrate/workflows'));
    });

    it('getWorkflowById should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: 'workflow' });
      const testId = '123';

      await getWorkflowById(testId);
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining(`/rest/v1/orchestrate/workflows/${testId}`));
    });

    it('createWorkflow should call api.post with correct URL and data', async () => {
      const mockApi = axios.create();
      mockApi.post.mockResolvedValue({ data: 'created' });
      const testData = { name: 'New Workflow' };

      await createWorkflow(testData);
      expect(mockApi.post).toHaveBeenCalledWith(expect.stringContaining('/rest/v1/orchestrate/workflows'), { psop: testData });
    });

    it('delWorkflowById should call api.delete with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.delete.mockResolvedValue({ data: 'ok' });
      const testId = 'abc-123';

      await delWorkflowById(testId);
      expect(mockApi.delete).toHaveBeenCalledWith(expect.stringContaining(`/rest/v1/orchestrate/workflows/${testId}`));
    });
  });

  describe('Direct axios requests', () => {
    it('parsePdf should handle successful response', async () => {
      const mockFile = new File([''], 'test.pdf', { type: 'application/pdf' });
      const mockContent = { key: 'value' };
      axios.post.mockResolvedValue({
        data: { status: 'success', data: mockContent }
      });

      const result = await parsePdf(mockFile);
      expect(result).toEqual({ key: 'value' });
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/parse-pdf'),
        expect.any(FormData),
        expect.objectContaining({
          headers: { 'Content-Type': 'multipart/form-data' }
        })
      );
    });

    it('parsePdf should throw error when status is not success', async () => {
      const mockFile = new File([''], 'test.pdf', { type: 'application/pdf' });
      axios.post.mockResolvedValue({
        data: { status: 'error', message: 'Parse failed' }
      });

      await expect(parsePdf(mockFile)).rejects.toThrow('Parse failed');
    });

    it('handlePlan should handle successful response', async () => {
      const preflow = {};
      const agentCards = [];
      const mockData = { plan: 'test' };
      axios.post.mockResolvedValue({
        data: { status: 'success', data: mockData }
      });

      const result = await handlePlan(preflow, agentCards);
      expect(result).toEqual({ plan: 'test' });
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/generate-from-preflow'),
        { preflow, agent_cards: agentCards }
      );
    });

    it('handlePlan should throw error when status is not success', async () => {
      axios.post.mockResolvedValue({
        data: { status: 'error', message: 'Plan failed' }
      });

      await expect(handlePlan({}, [])).rejects.toThrow('Plan failed');
    });

    it('generateWorkflowFromIntent should handle successful response', async () => {
      const intent = 'test intent';
      const mockWorkflow = { id: 1 };
      axios.post.mockResolvedValue({
        status: 200,
        data: { status: 'success', data: mockWorkflow }
      });

      const result = await generateWorkflowFromIntent(intent);
      expect(result).toEqual(mockWorkflow);
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/generate-from-intent'),
        { user_intent: intent, workflow_name: "Generated Workflow" }
      );
    });

    it('generateWorkflowFromIntent should throw error when response indicates failure', async () => {
      axios.post.mockResolvedValue({
        data: { status: 'error', message: 'Generation failed' }
      });

      await expect(generateWorkflowFromIntent('intent')).rejects.toThrow('Generation failed');
    });

    it('getTemplates should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: [] });

      await getTemplates();
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/rest/v1/orchestrate/templates'));
    });

    it('importTemplate should call api.post with correct URL and template id', async () => {
      const mockApi = axios.create();
      mockApi.post.mockResolvedValue({ data: {} });
      const tplId = 'template_ran_energy_saving';

      await importTemplate(tplId);
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining(`/rest/v1/orchestrate/templates/${tplId}/import`)
      );
    });

    it('matchWorkflows should call axios.post and return parsed results', async () => {
      const intent = 'energy saving';
      axios.post.mockResolvedValue({
        status: 200,
        data: {
          status: 'success',
          data: [{ id: 'wf1', name: 'ES Workflow', description: 'desc', tags: ['RAN'] }]
        }
      });

      const result = await matchWorkflows(intent);
      expect(result).toEqual([{ workflow_id: 'wf1', name: 'ES Workflow', description: 'desc', tags: ['RAN'] }]);
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/retrieve-by-intent'),
        { user_intent: intent }
      );
    });

    it('getExecutionRecords should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: [] });

      await getExecutionRecords();
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/rest/v1/orchestrate/execution-records'));
    });

    it('getExecutionRecord should call api.get with execution id', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: {} });
      const execId = 'exec-001';

      await getExecutionRecord(execId);
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining(`/rest/v1/orchestrate/execution-records/${execId}`));
    });

    it('deleteExecutionRecord should call api.delete with execution id', async () => {
      const mockApi = axios.create();
      mockApi.delete.mockResolvedValue({ data: 'ok' });
      const execId = 'exec-002';

      await deleteExecutionRecord(execId);
      expect(mockApi.delete).toHaveBeenCalledWith(expect.stringContaining(`/rest/v1/orchestrate/execution-records/${execId}`));
    });
    it('getStartProcessStreamUrl should build correct SSE URL', () => {
      const url1 = getStartProcessStreamUrl('psop-123');
      expect(url1).toContain('/rest/v1/orchestrate/execute?psop_id=psop-123');
      expect(url1).not.toContain('user_intent');

      const url2 = getStartProcessStreamUrl('psop-456', 'test intent with spaces');
      expect(url2).toContain('/rest/v1/orchestrate/execute?psop_id=psop-456');
      expect(url2).toContain('user_intent=');
    });
  });
});
