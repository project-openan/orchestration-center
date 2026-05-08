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
  switchLanguage,
  parsePdf,
  handlePlan,
  generateWorkflowFromIntent
} from './api';

// Mock axios
vi.mock('axios', () => {
  const mockApi = {
    get: vi.fn(),
    post: vi.fn(),
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
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining('/psops'));
    });

    it('getWorkflowById should call api.get with correct URL', async () => {
      const mockApi = axios.create();
      mockApi.get.mockResolvedValue({ data: 'workflow' });
      const testId = '123';

      await getWorkflowById(testId);
      expect(mockApi.get).toHaveBeenCalledWith(expect.stringContaining(`/psops/${testId}`));
    });

    it('createWorkflow should call api.post with correct URL and data', async () => {
      const mockApi = axios.create();
      mockApi.post.mockResolvedValue({ data: 'created' });
      const testData = { name: 'New Workflow' };

      await createWorkflow(testData);
      expect(mockApi.post).toHaveBeenCalledWith(expect.stringContaining('/psops'), testData);
    });
  });

  describe('Direct axios requests', () => {
    it('switchLanguage should call axios.post with correct params', async () => {
      const testLocale = 'zh';
      axios.post.mockResolvedValue({ data: 'ok' });

      await switchLanguage(testLocale);
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/rest/agents/switch-language'),
        { language: testLocale }
      );
    });

    it('parsePdf should handle successful response', async () => {
      const mockFile = new File([''], 'test.pdf', { type: 'application/pdf' });
      const mockContent = JSON.stringify({ key: 'value' });
      axios.post.mockResolvedValue({
        data: { status: 'success', content: mockContent }
      });

      const result = await parsePdf(mockFile);
      expect(result).toEqual({ key: 'value' });
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/parse-pdf'),
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
      const mockData = JSON.stringify({ plan: 'test' });
      axios.post.mockResolvedValue({
        data: { status: 'success', data: mockData }
      });

      const result = await handlePlan(preflow, agentCards);
      expect(result).toEqual({ plan: 'test' });
      expect(axios.post).toHaveBeenCalledWith(
        expect.stringContaining('/plan'),
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
        expect.stringContaining('/generate-from-intent'),
        { user_intent: intent, workflow_name: "AI Generated Workflow" }
      );
    });

    it('generateWorkflowFromIntent should throw error when response indicates failure', async () => {
      axios.post.mockResolvedValue({
        data: { status: 'error', message: 'Generation failed' }
      });

      await expect(generateWorkflowFromIntent('intent')).rejects.toThrow('Generation failed');
    });
  });
});
