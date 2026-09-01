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

import axios from 'axios';

// ──── Base URL resolution ────

const STORAGE_KEY = 'server_config';
const defaultGateway = '/api/orchestrate';
const defaultIp = '127.0.0.1';
const defaultPort = '5001';
const defaultProtocol =
    window.location.protocol === 'https:' ? 'https://' : 'http://';

const trimTrailingSlash = (url) => url.replace(/\/$/, '');

export const shouldDefaultToGateway = () => true;

export function getBaseUrl() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const config = JSON.parse(saved);
            if (config.mode === 'ip') {
                const ip = config.ip || defaultIp;
                const port = config.port || defaultPort;
                return `${defaultProtocol}${ip}:${port}`;
            }
            return trimTrailingSlash(
                config.nginxUrl || config.gatewayUrl || defaultGateway
            );
        }
        if (shouldDefaultToGateway()) {
            return trimTrailingSlash(defaultGateway);
        }
        return `${defaultProtocol}${defaultIp}:${defaultPort}`;
    } catch {
        return `${defaultProtocol}${defaultIp}:${defaultPort}`;
    }
}

const ORCHESTRATE_BASE = () => `${getBaseUrl()}/rest/v1/orchestrate`;

// ──── Shared axios instance (default: orchestrate gateway) ────

const api = axios.create({ timeout: 120000, withCredentials: true });

api.interceptors.response.use(
    (response) => response.data,
    (error) => {
        if (error.response && error.response.status === 401) {
            window.dispatchEvent(new Event('auth-expired'));
        }
        return Promise.reject(error);
    }
);

export default api;

// ──── Factory: create a per-plugin axios instance ────
// Plugins with their own backend (e.g. registry-center) declare a gateway
// path in their manifest. The Portal calls this to create a dedicated API
// client that routes to that backend via the corresponding Vite/nginx proxy.

export function createApi(gateway) {
    const instance = axios.create({
        baseURL: trimTrailingSlash(gateway || defaultGateway),
        timeout: 120000,
        withCredentials: true,
    });
    instance.interceptors.response.use(
        (response) => response.data,
        (error) => {
            if (error.response && error.response.status === 401) {
                window.dispatchEvent(new Event('auth-expired'));
            }
            return Promise.reject(error);
        }
    );
    return instance;
}

// ──── Auth endpoints ────
// The axios interceptor already unwraps response.data, so these functions
// receive the backend envelope { code, message, data } and return .data.

export async function authCheck() {
    const resp = await api.get(`${ORCHESTRATE_BASE()}/auth/check`);
    return resp.data;
}

export async function login(username, password) {
    const resp = await api.post(`${ORCHESTRATE_BASE()}/auth/login`, { username, password });
    return resp.data;
}

export async function logout() {
    await api.post(`${ORCHESTRATE_BASE()}/auth/logout`);
}

// ──── Business API (used by shared-workflow components via @/service/api.js) ────

export async function getAgentCards() {
    return api.get(`${ORCHESTRATE_BASE()}/agent-cards`);
}

export async function getWorkflow() {
    return api.get(`${ORCHESTRATE_BASE()}/workflows`);
}

export async function getWorkflowById(id) {
    return api.get(`${ORCHESTRATE_BASE()}/workflows/${id}`);
}

export async function delWorkflowById(id) {
    return api.delete(`${ORCHESTRATE_BASE()}/workflows/${id}`);
}

export async function createWorkflow(data) {
    return api.post(`${ORCHESTRATE_BASE()}/workflows`, { psop: data });
}

export async function getTemplates() {
    return api.get(`${ORCHESTRATE_BASE()}/templates`);
}

export async function importTemplate(templateId) {
    return api.post(`${ORCHESTRATE_BASE()}/templates/${templateId}/import`);
}

function unwrapEnvelope(body) {
    if (body.status === 'error') {
        throw new Error(body.message || 'Request failed');
    }
    return body.data;
}

export async function parsePdf(file) {
    const formData = new FormData();
    formData.append('file', file);
    const body = await api.post(`${ORCHESTRATE_BASE()}/parse-pdf`, formData);
    return unwrapEnvelope(body);
}

export async function handlePlan(preflow, agentCards) {
    const body = await api.post(`${ORCHESTRATE_BASE()}/generate-from-preflow`, {
        preflow: preflow,
        agent_cards: agentCards
    });
    return unwrapEnvelope(body);
}

export async function generateWorkflowFromIntent(intent, name = "Generated Workflow") {
    const body = await api.post(`${ORCHESTRATE_BASE()}/generate-from-intent`, {
        user_intent: intent,
        workflow_name: name
    });
    return unwrapEnvelope(body) || body;
}

export async function matchWorkflowsTopN(intent, topN = 3) {
    const body = await api.post(`${ORCHESTRATE_BASE()}/retrieve-topn-by-intent`, {
        user_intent: intent,
        top_n: topN
    });
    const data = body.data;
    if (!data) return [];
    return (Array.isArray(data) ? data : [data]).map(item => ({
        workflow_id: item.workflow_id,
        name: item.name,
        description: item.description,
        tags: item.tags || [],
        score: item.score
    }));
}

export function getStartProcessStreamUrl(psopId, userIntent = '', lang = '', targetAgent = '') {
    const base = `${ORCHESTRATE_BASE()}/execute?psop_id=${psopId}`;
    const params = [];
    if (userIntent) params.push(`user_intent=${encodeURIComponent(userIntent)}`);
    if (lang) params.push(`lang=${encodeURIComponent(lang)}`);
    if (targetAgent) params.push(`target_agent=${encodeURIComponent(targetAgent)}`);
    return params.length ? `${base}&${params.join('&')}` : base;
}

export function getDispatchStreamUrl(intent, agentName, lang = '') {
    const params = [`intent=${encodeURIComponent(intent)}`, `agent_name=${encodeURIComponent(agentName)}`];
    if (lang) params.push(`lang=${encodeURIComponent(lang)}`);
    return `${ORCHESTRATE_BASE()}/dispatch?${params.join('&')}`;
}

export async function getExecutionRecords() {
    return api.get(`${ORCHESTRATE_BASE()}/execution-records`);
}

export async function getExecutionRecord(executionId) {
    return api.get(`${ORCHESTRATE_BASE()}/execution-records/${executionId}`);
}

export async function deleteExecutionRecord(executionId) {
    return api.delete(`${ORCHESTRATE_BASE()}/execution-records/${executionId}`);
}
