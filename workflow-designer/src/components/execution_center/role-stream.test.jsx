// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';

const capture = vi.hoisted(() => ({ workflow: null, source: null, t: key => key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: capture.t, i18n: { language: 'en' } }) }));
vi.mock('@/service/api.js', async importOriginal => {
    const actual = await importOriginal();
    return { ...Object.fromEntries(Object.keys(actual).map(key => [key, vi.fn().mockResolvedValue({ status: 'success', data: [] })])),
        getAgentCards: vi.fn().mockResolvedValue({ data: [{ name: 'Host' }] }),
        getDispatchStreamUrl: vi.fn().mockReturnValue('/fake-sse'),
    };
});
vi.mock('../orchestration_center/workflow/index.jsx', () => ({ default: props => { capture.workflow = props; return null; } }));
vi.mock('./execution_statistics/index.jsx', () => ({ default: () => null }));

import ExecutionCenter from './index.jsx';

it('handles resolution and error SSE without replacing the role design graph with instance topology', async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    document.body.append(container);
    const root = createRoot(container);
    vi.stubGlobal('EventSource', class {
        static CLOSED = 2;
        constructor() { capture.source = this; this.readyState = 1; }
        close() { this.readyState = 2; }
    });
    const scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo');
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
    try {
        localStorage.clear();
        await act(async () => root.render(<ExecutionCenter isDark={false} />));
        const intentInput = container.querySelector('input[placeholder="execution.intent_placeholder"]');
        await act(async () => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(intentInput, 'Analyze');
            intentInput.dispatchEvent(new Event('input', { bubbles: true }));
        });
        const dispatch = [...container.querySelectorAll('button')].find(button => button.textContent.trim() === 'execution.dispatch');
        expect(dispatch.disabled).toBe(false);
        await act(async () => dispatch.click());
        const emit = async (type, data) => act(async () => capture.source.onmessage({ data: JSON.stringify({ type, data, timestamp: 1 }) }));
        const template = { id: 'wf', name: 'Design', catalog_version: 'v1', steps: ['first', 'parallel'].map((name, index) => ({
            name, next: null, subtasks: [{ task_id: `original-${index}`, binding: 'role', role_version: '1',
                agent: 'role-a', skill: 'explore', status: 'pending' }],
        })) };
        await emit('start', { workflow: 'Design', workflow_id: 'wf' });
        await emit('psop_update', { psop: template });
        await emit('resolution', { execution_id: 'exec-1', resolution_snapshot: { template },
            bindings: [{ task_id: 'original-0', role_id: 'role-a', instance_id: 'worker' }] });
        await emit('psop_update', { psop: { ...template, steps: template.steps.map(step => ({ ...step,
            subtasks: step.subtasks.map(task => ({ ...task, binding: 'instance', agent: 'worker', skill: 'analyze', status: 'success' })),
        })) } });
        const task = capture.workflow.nodes.find(node => node.id === 'first').data.subtasks[0];
        expect(task).toMatchObject({ agent: 'role-a', skill: 'explore', binding: 'role', runtimeInstance: 'worker', status: 'success' });
        expect(capture.workflow.edges.some(edge => edge.source === 'first' && edge.target === 'parallel')).toBe(false);
        await emit('error', { code: 'CARD_DRIFT', reason: 'CHANGED', task_ids: ['original-0'], error: 'Card changed' });
        expect(capture.workflow.nodes.find(node => node.id === 'first').data.executionError).toContain('CARD_DRIFT');
        expect(capture.workflow.nodes.find(node => node.id === 'parallel').data.executionError).toBeNull();
        expect(container.textContent).toContain('CHANGED');
        expect(container.textContent).toContain('exec-1');
        expect(template.steps[0].subtasks[0].status).toBe('pending');
        await act(async () => dispatch.click());
        expect(container.textContent).toContain('execution.standby');
        await emit('error', { code: 'PSOP_NOT_FOUND', error: 'No workflow' });
        expect(container.textContent).toContain('execution.standby');
        expect(container.textContent).toContain('PSOP_NOT_FOUND');
        expect(container.textContent).not.toContain('exec-1');
    } finally {
        await act(async () => root.unmount());
        container.remove();
        if (scroll) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scroll);
        else delete HTMLElement.prototype.scrollTo;
        vi.unstubAllGlobals();
    }
});
