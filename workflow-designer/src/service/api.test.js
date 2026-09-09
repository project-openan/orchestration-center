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
  shouldDefaultToGateway,
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
  deleteExecutionRecord,
  setApiClient,
  authCheck,
  login,
  logout,
  register,
  listUsers,
  deleteUser,
  changePassword
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
    it('should return the gateway URL when localStorage is empty', () => {
      const url = getBaseUrl();
      expect(url).toBe(defaultGateway);
    });

    it('should return custom URL when localStorage has config', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({ mode: 'ip', ip: '192.168.1.1', port: '8080' }));
      const url = getBaseUrl();
      expect(url).toBe('http://192.168.1.1:8080');
    });

    it('should return default IP if port is missing in config', () => {
      mockLocalStorage.setItem('server_config', JSON.stringify({ mode: 'ip', ip: '192.168.1.1' }));
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

    describe('with no saved config, on a non-standard port', () => {
      // Regression coverage for 9b: the session cookie only attaches on a
      // same-origin request, so the gateway path (proxied by nginx in
      // docker-compose, or by Vite's dev server for `npm run dev`) must be
      // the default everywhere -- including localhost:3003, which used to
      // default to a cross-origin direct-IP call that a cookie can't reach.
      const originalLocation = window.location;

      const setHostname = (hostname) => {
        Object.defineProperty(window, 'location', {
          value: { ...originalLocation, hostname, port: '3003', protocol: 'http:' },
          configurable: true,
        });
      };

      afterEach(() => {
        Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
      });

      it('uses the gateway for a remote hostname (regression: was defaulting to 127.0.0.1, unreachable from a real client)', () => {
        setHostname('10.220.239.88');
        expect(shouldDefaultToGateway()).toBe(true);
        expect(getBaseUrl()).toBe(defaultGateway);
      });

      it('uses the gateway when loaded from localhost (local `npm run dev` workflow, proxied by vite.config.js)', () => {
        setHostname('localhost');
        expect(shouldDefaultToGateway()).toBe(true);
        expect(getBaseUrl()).toBe(defaultGateway);
      });

      it('uses the gateway when loaded from 127.0.0.1', () => {
        setHostname('127.0.0.1');
        expect(shouldDefaultToGateway()).toBe(true);
        expect(getBaseUrl()).toBe(defaultGateway);
      });
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

  describe('More api instance requests', () => {
    it('parsePdf should handle successful response', async () => {
      const mockApi = axios.create();
      const mockFile = new File([''], 'test.pdf', { type: 'application/pdf' });
      const mockContent = { key: 'value' };
      mockApi.post.mockResolvedValue({ status: 'success', data: mockContent });

      const result = await parsePdf(mockFile);
      expect(result).toEqual({ key: 'value' });
      // No explicit Content-Type: passing a FormData body lets axios generate
      // the multipart boundary itself. A manually-set header without one
      // would break multipart parsing server-side.
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/parse-pdf'),
        expect.any(FormData)
      );
    });

    it('parsePdf should throw error when status is not success', async () => {
      const mockApi = axios.create();
      const mockFile = new File([''], 'test.pdf', { type: 'application/pdf' });
      mockApi.post.mockResolvedValue({ status: 'error', message: 'Parse failed' });

      await expect(parsePdf(mockFile)).rejects.toThrow('Parse failed');
    });

    it('handlePlan should handle successful response', async () => {
      const mockApi = axios.create();
      const preflow = {};
      const agentCards = [];
      const mockData = { plan: 'test' };
      mockApi.post.mockResolvedValue({ status: 'success', data: mockData });

      const result = await handlePlan(preflow, agentCards);
      expect(result).toEqual({ plan: 'test' });
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/generate-from-preflow'),
        { preflow, agent_cards: agentCards }
      );
    });

    it('handlePlan should throw error when status is not success', async () => {
      const mockApi = axios.create();
      mockApi.post.mockResolvedValue({ status: 'error', message: 'Plan failed' });

      await expect(handlePlan({}, [])).rejects.toThrow('Plan failed');
    });

    it('generateWorkflowFromIntent should handle successful response', async () => {
      const mockApi = axios.create();
      const intent = 'test intent';
      const mockWorkflow = { id: 1 };
      mockApi.post.mockResolvedValue({ status: 'success', data: mockWorkflow });

      const result = await generateWorkflowFromIntent(intent);
      expect(result).toEqual(mockWorkflow);
      expect(mockApi.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/v1/orchestrate/generate-from-intent'),
        { user_intent: intent, workflow_name: "Generated Workflow" }
      );
    });

    it('generateWorkflowFromIntent should throw error when response indicates failure', async () => {
      const mockApi = axios.create();
      mockApi.post.mockResolvedValue({ status: 'error', message: 'Generation failed' });

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

    it('matchWorkflows should call api.post and return parsed results', async () => {
      const mockApi = axios.create();
      const intent = 'energy saving';
      mockApi.post.mockResolvedValue({
        status: 'success',
        data: [{ id: 'wf1', name: 'ES Workflow', description: 'desc', tags: ['RAN'] }]
      });

      const result = await matchWorkflows(intent);
      expect(result).toEqual([{ workflow_id: 'wf1', name: 'ES Workflow', description: 'desc', tags: ['RAN'] }]);
      expect(mockApi.post).toHaveBeenCalledWith(
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

  // Regression coverage for #16: this file previously had zero tests for
  // login/register/changePassword or the response interceptor, despite
  // #9 (9a) changing exactly what these functions send over the wire.
  // Regression coverage for 9b: the session token moved from a JSON body
  // field (read into localStorage, replayed as an Authorization header) to
  // an httpOnly cookie the browser handles entirely on its own -- api.js no
  // longer touches the token value at all, so there's nothing left here to
  // assert about token storage or a request interceptor (both removed).
  describe('Access authentication', () => {
    // The response interceptor is registered once, at module import time --
    // before any beforeEach in this suite runs and calls vi.clearAllMocks().
    // Capture the real callback here, during test collection, not inside an it().
    const mockApi = axios.create();
    const [responseSuccessInterceptor, responseErrorInterceptor] = mockApi.interceptors.response.use.mock.calls[0];

    describe('response interceptor', () => {
      it('unwraps response.data on success', () => {
        const result = responseSuccessInterceptor({ data: { status: 'success' } });
        expect(result).toEqual({ status: 'success' });
      });

      it('dispatches auth-expired on a 401', async () => {
        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
        const error = { response: { status: 401 } };

        await expect(responseErrorInterceptor(error)).rejects.toBe(error);
        expect(dispatchSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'auth-expired' }));
        dispatchSpy.mockRestore();
      });

      it('does not dispatch auth-expired on a non-401 error', async () => {
        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
        const error = { response: { status: 500 } };

        await expect(responseErrorInterceptor(error)).rejects.toBe(error);
        expect(dispatchSpy).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'auth-expired' }));
        dispatchSpy.mockRestore();
      });

      it('does not dispatch auth-expired on a network error with no response', async () => {
        const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
        const error = {};

        await expect(responseErrorInterceptor(error)).rejects.toBe(error);
        expect(dispatchSpy).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'auth-expired' }));
        dispatchSpy.mockRestore();
      });
    });

    describe('login/register/changePassword send plaintext (regression for #9)', () => {
      it('login sends the password as-is, not a SHA-256 digest of it', async () => {
        mockApi.post.mockResolvedValue({ data: { username: 'alice', role: 'user' } });

        await login('alice', 'MyRealPassword1!');
        expect(mockApi.post).toHaveBeenCalledWith(
          expect.stringContaining('/auth/login'),
          { username: 'alice', password: 'MyRealPassword1!' }
        );
      });

      it('login returns the response data as-is (the session token is a cookie, never in this body)', async () => {
        mockApi.post.mockResolvedValue({ data: { username: 'alice', role: 'user' } });

        const result = await login('alice', 'MyRealPassword1!');
        expect(result).toEqual({ username: 'alice', role: 'user' });
      });

      it('register sends the password as-is, not a SHA-256 digest of it', async () => {
        mockApi.post.mockResolvedValue({ data: { username: 'alice' } });

        await register('alice', 'MyRealPassword1!');
        expect(mockApi.post).toHaveBeenCalledWith(
          expect.stringContaining('/auth/register'),
          { username: 'alice', password: 'MyRealPassword1!' }
        );
      });

      it('changePassword sends both passwords as-is, not SHA-256 digests', async () => {
        mockApi.post.mockResolvedValue({ data: {} });

        await changePassword('OldPassword1!', 'NewPassword1!');
        expect(mockApi.post).toHaveBeenCalledWith(
          expect.stringContaining('/auth/change-password'),
          { old_password: 'OldPassword1!', new_password: 'NewPassword1!' }
        );
      });
    });

    describe('other auth endpoints', () => {
      it('authCheck calls GET /auth/check', async () => {
        mockApi.get.mockResolvedValue({ data: { authenticated: false } });
        const result = await authCheck();
        expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/auth/check'));
        expect(result).toEqual({ authenticated: false });
      });

      it('logout posts to /auth/logout (the server clears the cookie via Set-Cookie)', async () => {
        mockApi.post.mockResolvedValue({ data: {} });

        await logout();
        expect(mockApi.post).toHaveBeenCalledWith(expect.stringContaining('/auth/logout'));
      });

      it('logout propagates a request failure', async () => {
        mockApi.post.mockRejectedValue(new Error('network error'));

        await expect(logout()).rejects.toThrow('network error');
      });

      it('listUsers calls GET /auth/users', async () => {
        mockApi.get.mockResolvedValue({ data: [{ username: 'alice' }] });
        const result = await listUsers();
        expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/auth/users'));
        expect(result).toEqual([{ username: 'alice' }]);
      });

      it('deleteUser calls DELETE /auth/users/{username}', async () => {
        mockApi.delete.mockResolvedValue({ data: {} });
        await deleteUser('alice');
        expect(mockApi.delete).toHaveBeenCalledWith(expect.stringContaining('/auth/users/alice'));
      });
    });
  });

  describe('OpenAN Portal plugin mode', () => {
    afterEach(() => {
      // Remove the Portal context global so later tests run standalone.
      delete window.__OPENAN_PORTAL_CONTEXT__;
    });

    it('always routes through the relative gateway when the Portal context is present', async () => {
      // Simulate the Portal shell on a non-standard port (:9000) with a saved
      // direct-IP server config — the plugin must ignore both and use the
      // relative gateway on the Portal's own origin.
      const mockApi = axios.create();
      mockLocalStorage.setItem('server_config', JSON.stringify({ mode: 'ip', ip: '192.168.1.1', port: '8080' }));
      window.__OPENAN_PORTAL_CONTEXT__ = { theme: {}, auth: {} };
      mockApi.get.mockResolvedValue({ data: [] });

      await getAgentCards();

      const calledUrl = mockApi.get.mock.calls[0][0];
      expect(calledUrl.startsWith('/api/orchestrate/rest/v1/')).toBe(true);
    });

    it('falls back to getBaseUrl() when no Portal context is present (standalone)', async () => {
      const mockApi = axios.create();
      mockLocalStorage.setItem('server_config', JSON.stringify({ mode: 'ip', ip: '192.168.1.1', port: '8080' }));
      mockApi.get.mockResolvedValue({ data: [] });

      await getAgentCards();

      const calledUrl = mockApi.get.mock.calls[0][0];
      expect(calledUrl.startsWith('http://192.168.1.1:8080/rest/v1/')).toBe(true);
    });

    it('setApiClient reroutes requests through the injected Portal client', async () => {
      const portalClient = { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn(), delete: vi.fn() };
      setApiClient(portalClient);

      await getAgentCards();
      expect(portalClient.get).toHaveBeenCalledWith(expect.stringContaining('/rest/v1/orchestrate/agent-cards'));

      // Restore the local client for subsequent tests.
      setApiClient(axios.create());
    });
  });
});
