// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import ExecutionTimeline from './index.jsx';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

it('renders canonical latest attempt and failed step without an untruncated event log', async () => {
    const workflow = {
        name: 'Diagnostic flow',
        steps: [{ name: 'Diagnostics', subtasks: [{ description: 'Identify fault', agent: 'Worker' }] }],
    };
    const identity = { task_id: 'runtime-task', step_ref: 's0', task_ref: 's0/t0' };
    const latestAttempt = {
        ...identity, attempt: 2, outcome: 'succeeded',
        input_summary: 'Canonical request',
        result: { summary: 'Canonical conclusion', outputs: { result: 'Canonical output' } },
    };
    const observation = {
        status: 'failed',
        startedAt: '2026-11-24T03:00:00Z',
        completedAt: '2026-11-24T03:01:00Z',
        projectedThrough: '1042',
        stepHistory: [{
            step_ref: 's0', outcome: 'failed', started_at: '2026-11-24T03:00:00Z',
            completed_at: '2026-11-24T03:01:00Z',
        }],
        taskHistory: [{
            ...latestAttempt, attempts: { 1: { ...identity, attempt: 1, outcome: 'failed' }, 2: latestAttempt },
        }],
    };
    const events = [
        { type: 'task_response', seq: '1040', data: { ...identity, attempt: 1, outcome: 'failed', summary: 'Prior failure' } },
        { type: 'task_response', seq: '1042', data: { ...identity, attempt: 2, outcome: 'failed', summary: 'Conflicting result' } },
        { type: 'task_status_changed', seq: '1045', data: { ...identity, attempt: 2, summary: 'Beyond watermark' } },
    ];
    const container = document.createElement('div');
    const root = createRoot(container);
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    try {
        await act(async () => root.render(
            <ExecutionTimeline events={events} workflow={workflow} observation={observation} isRunning={false} />
        ));
        expect(container.textContent).toContain('Diagnostics失败');
        expect(container.textContent).toContain('第 2 次');
        expect(container.textContent).toContain('Canonical conclusion');
        expect(container.textContent).toContain('业务请求Canonical request');
        expect(container.textContent).toContain('业务结果Canonical conclusion');
        expect(container.textContent).toContain('Canonical output');
        expect(container.textContent).not.toMatch(/Prior failure|Conflicting result|Beyond watermark/);
    } finally {
        await act(async () => root.unmount());
        delete globalThis.IS_REACT_ACT_ENVIRONMENT;
    }
});
