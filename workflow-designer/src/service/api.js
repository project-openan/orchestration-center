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
import axios from "axios";

const STORAGE_KEY = 'server_config';
export const defaultIp = '127.0.0.1';
export const defaultPort = '5001';
export const defaultGateway = '/api/orchestrate';

 // Protocol follows the current page: HTTPS page -> https://, otherwise http://
export const defaultProtocol = window.location.protocol === 'https:' ? 'https://' : 'http://';

const trimTrailingSlash = (url) => url.replace(/\/$/, '');

// The session cookie (see login()/logout() below) is httpOnly and scoped to
// the internal API path, so the browser only attaches it on a same-origin
// request. Both shipped serving paths -- nginx in docker-compose, and the
// Vite dev server's own /api/orchestrate proxy for `npm run dev` -- put the
// frontend and this API on the same origin, so the gateway path is always
// the correct default; direct-IP mode remains available as an explicit,
// manually-configured choice (see the settings UI) for deployments that
// don't run behind either proxy.
export const shouldDefaultToGateway = () => true;

export const getBaseUrl = () => {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const config = JSON.parse(saved);
          if (config.mode === 'ip') {
              const ip = config.ip || defaultIp;
              const port = config.port || defaultPort;
                return `${defaultProtocol}${ip}:${port}`;
           }
            return trimTrailingSlash(config.nginxUrl || config.gatewayUrl || defaultGateway);
        }
       if (shouldDefaultToGateway()) {
           return trimTrailingSlash(defaultGateway);
       }
        return `${defaultProtocol}${defaultIp}:${defaultPort}`;
   } catch (e) {
        return `${defaultProtocol}${defaultIp}:${defaultPort}`;
   }
}

const ORCHESTRATE_BASE = () => `${getBaseUrl()}/rest/v1/orchestrate`;

// withCredentials: true so the httpOnly session cookie is sent on every
// request (and stored from every Set-Cookie response) -- same-origin via
// the gateway path this makes no difference, but it's what a cross-origin
// direct-IP deployment needs for the cookie to attach at all.
const localApi = axios.create({ timeout: 120000, withCredentials: true });

localApi.interceptors.response.use(
    (response) => response.data,
    (error) => {
        if (error.response && error.response.status === 401) {
            window.dispatchEvent(new Event('auth-expired'));
        }
        return Promise.reject(error);
    }
);

// Injectable client — the OpenAN Portal plugin entry calls setApiClient() with
// PortalContext.api at mount so every request flows through the Portal's
// axios instance (per-plugin gateway, auth cookie). Standalone mode never
// calls it and keeps the local instance above.
let api = localApi;

export function setApiClient(instance) {
    if (instance && typeof instance.get === 'function') {
        api = instance;
    }
}

// ──── Agent Cards ────

export async function getAgentCards() {
    return api.get(`${ORCHESTRATE_BASE()}/agent-cards`);
}

// ──── Workflow CRUD ────

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

// ──── Workflow Templates ────

export async function getTemplates() {
    return api.get(`${ORCHESTRATE_BASE()}/templates`);
}

export async function importTemplate(templateId) {
    return api.post(`${ORCHESTRATE_BASE()}/templates/${templateId}/import`);
}

// Backend envelope is {code, message, status, data} (see response_utils.py). A
// non-2xx response already rejects via axios; this catches the "200 OK but
// status: error" case so callers relying on try/catch (e.g. the PDF import
// flow) actually see a rejection instead of silently getting `undefined`.
function unwrapEnvelope(body) {
    if (body.status === 'error') {
        throw new Error(body.message || 'Request failed');
    }
    return body.data;
}

// ──── PDF Parsing ────

export async function parsePdf(file) {
    const formData = new FormData();
    formData.append('file', file);
    const body = await api.post(`${ORCHESTRATE_BASE()}/parse-pdf`, formData);
    return unwrapEnvelope(body);
}

// ──── Workflow Generation ────

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

export async function matchWorkflows(intent) {
    const body = await api.post(`${ORCHESTRATE_BASE()}/retrieve-by-intent`, {
        user_intent: intent,
    });
    const data = body.data;
    if (!data) return [];
    const list = Array.isArray(data) ? data : [data];
    return list.map(item => ({
        workflow_id: item.id || item.workflow_id,
        name: item.name || item.workflow_name,
        description: item.description,
        tags: item.tags || []
    }));
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

// ──── Workflow Execution ────

export function getStartProcessStreamUrl(psopId, userIntent = '', lang = '', targetAgent = '') {
    const base = `${ORCHESTRATE_BASE()}/execute?psop_id=${psopId}`;
    const params = [];
    if (userIntent) {
        params.push(`user_intent=${encodeURIComponent(userIntent)}`);
    }
    if (lang) {
        params.push(`lang=${encodeURIComponent(lang)}`);
    }
    if (targetAgent) {
        params.push(`target_agent=${encodeURIComponent(targetAgent)}`);
    }
    if (params.length > 0) {
        return `${base}&${params.join('&')}`;
    }
    return base;
}

export function getDispatchStreamUrl(intent, agentName, lang = '') {
    const base = `${ORCHESTRATE_BASE()}/dispatch`;
    const params = [];
    params.push(`intent=${encodeURIComponent(intent)}`);
    params.push(`agent_name=${encodeURIComponent(agentName)}`);
    if (lang) {
        params.push(`lang=${encodeURIComponent(lang)}`);
    }
    return `${base}?${params.join('&')}`;
}

// ──── Execution Records ────

export async function getExecutionRecords() {
    return api.get(`${ORCHESTRATE_BASE()}/execution-records`);
}

export async function getExecutionRecord(executionId) {
    return api.get(`${ORCHESTRATE_BASE()}/execution-records/${executionId}`);
}

export async function deleteExecutionRecord(executionId) {
    return api.delete(`${ORCHESTRATE_BASE()}/execution-records/${executionId}`);
}
 
 // ---- Access authentication ----
 
export async function authCheck() {
    const resp = await api.get(`${ORCHESTRATE_BASE()}/auth/check`);
    return resp.data;
}
 
export async function login(username, password) {
    // The session token arrives as an httpOnly Set-Cookie header, not in
    // this body -- the browser stores it and attaches it automatically,
    // this code never sees or handles the token value at all.
    const body = await api.post(`${ORCHESTRATE_BASE()}/auth/login`, { username, password });
    return body.data;
}

export async function logout() {
    // The server clears the cookie via Set-Cookie on this response; there's
    // no client-side token state left to clean up on our end.
    await api.post(`${ORCHESTRATE_BASE()}/auth/logout`);
}
 
export async function register(username, password) {
    const body = await api.post(`${ORCHESTRATE_BASE()}/auth/register`, { username, password });
    return body.data;
}
 
export async function listUsers() {
    const resp = await api.get(`${ORCHESTRATE_BASE()}/auth/users`);
    return resp.data;
}
 
export async function deleteUser(username) {
    return api.delete(`${ORCHESTRATE_BASE()}/auth/users/${username}`);
}

export async function changePassword(oldPassword, newPassword) {
    return api.post(`${ORCHESTRATE_BASE()}/auth/change-password`, {
        old_password: oldPassword,
        new_password: newPassword,
    });
}
