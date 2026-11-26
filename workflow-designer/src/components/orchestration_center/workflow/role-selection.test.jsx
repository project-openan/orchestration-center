// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import UnifiedWorkflow from './index.jsx';
import { transformWorkflowToReactFlow } from './utils/index.jsx';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/service/api.js', () => ({
    getRoleCatalog: vi.fn().mockResolvedValue({ catalog_version: 'v1', roles: [
        { role_id: 'analyst', role_version: '1', skills: [{ skill_id: 'inspect' }] },
    ] }),
    getAgentCards: vi.fn().mockResolvedValue({ data: [] }), createWorkflow: vi.fn(),
}));
vi.mock('@/components/sandbox/SandboxDialog.jsx', () => ({ default: () => null }));

let root, container;
beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    // jsdom has no layout observer. Keep React Flow's real event handlers and store.
    vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
    container = document.createElement('div'); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.unstubAllGlobals(); });

it('keeps ordinary multi-selection without showing grouping controls or legacy group badges', async () => {
    const design = { name: 'Selection', catalog_version: 'v1', steps: ['first', 'second'].map((name, index) => ({
        name, type: 'AllSuccess', subtasks: [{ task_id: `task-${index}`, binding: 'role',
            agent: 'analyst', role_version: '1', skill: 'inspect', description: name, binding_group: 'legacy-session' }],
    })) };
    const graph = transformWorkflowToReactFlow(design);
    await act(async () => root.render(<UnifiedWorkflow mode="edit" workflowMetadata={design}
        importedNodes={graph.nodes} importedEdges={graph.edges} />));
    const node = id => container.querySelector(`.react-flow__node[data-id="${id}"]`);
    expect(container.querySelector('[data-testid="binding-group-actions"]')).toBeNull();
    await act(async () => node('first').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(node('first').classList.contains('selected')).toBe(true);
    await act(async () => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Shift', code: 'ShiftLeft', shiftKey: true, bubbles: true })));
    await act(async () => node('second').dispatchEvent(new MouseEvent('click', { bubbles: true, shiftKey: true })));
    await act(async () => window.dispatchEvent(new KeyboardEvent('keyup', { key: 'Shift', code: 'ShiftLeft', bubbles: true })));
    expect(node('first').classList.contains('selected')).toBe(true);
    expect(node('second').classList.contains('selected')).toBe(true);
    expect(container.querySelector('[data-testid="binding-group-actions"]')).toBeNull();
    expect(container.querySelector('[aria-label="workflow.roleCanvas.group"]')).toBeNull();
    expect(container.querySelector('[aria-label="workflow.roleCanvas.selectTask"]')).toBeNull();
    expect(container.textContent).not.toContain('legacy-session');
});
