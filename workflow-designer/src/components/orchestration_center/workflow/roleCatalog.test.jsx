// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import { decorateRoleNodes, useRoleCatalog } from './roleCatalog.js';
import { getRoleCatalog } from '@/service/api.js';
import { transformWorkflowToReactFlow, transformReactFlowToPSOP } from './utils/index.jsx';

vi.mock('@/service/api.js', () => ({ getRoleCatalog: vi.fn() }));

it('uses joint role/version/skill names only for display and never serializes them', () => {
    const design = { name: 'Design', catalog_version: 'v1', steps: [{ name: 'work', subtasks: [{
        task_id: 't1', binding: 'role', agent: 'role-a', role_version: '1', skill: 'same', description: 'Analyze',
    }], next: [] }] };
    const graph = transformWorkflowToReactFlow(design);
    const catalog = { catalog_version: 'v1', roles: ['role-a', 'role-b'].map(id => ({
        role_id: id, role_version: '1', name: `Display ${id}`, skills: [{ skill_id: 'same', name: `Skill ${id}` }],
    })) };
    const decorated = decorateRoleNodes(graph.nodes, catalog);
    expect(decorated.find(node => node.id === 'work').data.subtasks[0]).toMatchObject({
        agent: 'role-a', skill: 'same', roleName: 'Display role-a', skillName: 'Skill role-a',
    });
    expect(transformReactFlowToPSOP(decorated, graph.edges, design)).toEqual({ ...design, description: '', tags: [] });
    const unavailable = decorateRoleNodes(decorated, null);
    expect(unavailable.find(node => node.id === 'work').data.subtasks[0]).not.toHaveProperty('roleName');
});

it('rejects another release and ignores stale lookup results without latest fallback', async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    const root = createRoot(container);
    let state, firstResolve;
    const Probe = ({ version, enabled = true }) => { state = useRoleCatalog(version, enabled); return null; };
    getRoleCatalog.mockImplementationOnce(() => new Promise(resolve => { firstResolve = resolve; }))
        .mockResolvedValueOnce({ catalog_version: 'different', roles: [] });
    try {
        await act(async () => root.render(<Probe version="v1" />));
        await act(async () => root.render(<Probe version="v2" />));
        expect(state.unavailable).toBe(true);
        await act(async () => firstResolve({ catalog_version: 'v1', roles: [] }));
        expect(state.catalog).toBeNull();
        expect(getRoleCatalog.mock.calls).toEqual([['v1'], ['v2']]);
        await act(async () => root.render(<Probe version="v3" enabled={false} />));
        expect(getRoleCatalog).toHaveBeenCalledTimes(2);
    } finally {
        await act(async () => root.unmount());
        vi.clearAllMocks();
    }
});
