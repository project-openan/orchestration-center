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

import { useEffect, useState } from 'react';

/**
 * Agent registry status (publish + health) shared store.
 * Sync period: 3 minutes. Data source: registry-center manage cards + heartbeat health.
 * Fetch failures degrade gracefully to an empty map (badges simply hide).
 */
const REFRESH_MS = 3 * 60 * 1000;
const REGISTRY_CARDS_URL = '/api/registry/rest/v1/registry/agent-cards/manage';
const REGISTRY_HEALTH_URL = '/api/registry/rest/v1/registry/agents/health';

let registryMap = {};
let lastFetchAt = 0;
let inflight = null;
let timer = null;
const listeners = new Set();

async function refreshRegistry() {
    inflight = (async () => {
        try {
            const [cards, health] = await Promise.all([
                fetch(REGISTRY_CARDS_URL).then(r => (r.ok ? r.json() : null)).catch(() => null),
                fetch(REGISTRY_HEALTH_URL).then(r => (r.ok ? r.json() : null)).catch(() => null),
            ]);
            const map = {};
            ((cards && cards.agentCards) || []).forEach(a => {
                if (!a || !a.name) return;
                map[a.name] = { ...(map[a.name] || {}), publishStatus: a.publishStatus || 'published' };
            });
            ((health && health.agents) || []).forEach(a => {
                if (!a || !a.name) return;
                map[a.name] = { ...(map[a.name] || {}), healthStatus: a.health_status || 'unknown' };
            });
            registryMap = map;
            lastFetchAt = Date.now();
            listeners.forEach(fn => fn(registryMap));
        } finally {
            inflight = null;
        }
    })();
    return inflight;
}

function ensureSyncLoop() {
    if (timer) return;
    if (Date.now() - lastFetchAt > REFRESH_MS) refreshRegistry();
    timer = setInterval(() => {
        if (listeners.size > 0) refreshRegistry();
    }, REFRESH_MS);
}


const normAgentName = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

/**
 * Resolve an agent's registry info by name. Exact match first; then a
 * normalized containment match (workflow display names like
 * "Complaint Handling Agent" map to registry technical names like
 * "mockagent_an-l4-complaint-handling-agent"). Longest registry name wins.
 */
export function matchAgentInfo(map, agentName) {
    if (!agentName) return null;
    const exact = map[agentName];
    if (exact) return exact;
    const wfNorm = normAgentName(agentName);
    if (!wfNorm) return null;
    let best = null;
    for (const [regName, info] of Object.entries(map)) {
        const regNorm = normAgentName(regName);
        if (!regNorm) continue;
        if (regNorm.includes(wfNorm) || wfNorm.includes(regNorm)) {
            if (!best || regNorm.length > best.len) best = { info, len: regNorm.length };
        }
    }
    return best ? best.info : null;
}

export function useAgentRegistryStatus() {
    const [map, setMap] = useState(registryMap);
    useEffect(() => {
        listeners.add(setMap);
        ensureSyncLoop();
        return () => listeners.delete(setMap);
    }, []);
    return map;
}

const PUB_META = {
    published: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-500',
    registered: 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400',
    rejected: 'border-rose-500/40 bg-rose-500/10 text-rose-500',
    deprecated: 'border-zinc-400/40 bg-zinc-500/10 text-zinc-500 dark:text-zinc-400',
};

const HEALTH_META = {
    healthy: { dot: 'bg-emerald-500', cls: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-500' },
    suspect: { dot: 'bg-amber-500 animate-pulse', cls: 'border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400' },
    offline: { dot: 'bg-rose-500', cls: 'border-rose-500/40 bg-rose-500/10 text-rose-500' },
    unknown: { dot: 'bg-zinc-400', cls: 'border-zinc-400/40 bg-zinc-500/10 text-zinc-500 dark:text-zinc-400' },
};

export function AgentRegistryBadges({ info, isDark, t }) {
    if (!info || (!info.publishStatus && !info.healthStatus)) return null;
    const pubKey = info.publishStatus || 'published';
    const healthKey = info.healthStatus || 'unknown';
    const pub = PUB_META[pubKey] || PUB_META.published;
    const health = HEALTH_META[healthKey] || HEALTH_META.unknown;
    return (
        <span className="inline-flex items-center gap-1.5 flex-wrap">
            <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[9px] font-bold ${pub.cls}`}>
                {t(`workflow.panel.pub_${pubKey}`)}
            </span>
            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] font-bold ${health.cls}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${health.dot}`} />
                {t(`workflow.panel.health_${healthKey}`)}
            </span>
        </span>
    );
}
