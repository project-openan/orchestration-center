// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { annotateWorkflowErrors, errorStepNames, formatRoleResolution, formatWorkflowError } from './workflowErrors.js';
import ExecutionTimeline from './timeline/index.jsx';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

const workflow = { steps: [
    { name: 'first', subtasks: [{ task_id: 'original-1', agent: 'same-agent', skill: 'same-skill' }] },
    { name: 'second', subtasks: [{ task_id: 'original-2', agent: 'same-agent', skill: 'same-skill' }] },
] };
const failure = { code: 'CARD_DRIFT', reason: 'FINGERPRINT_CHANGED', error: 'Card changed',
    task_ids: ['original-1'], role_ids: ['role-a'], instance_id: 'worker-1', binding_group: 'group-1' };

describe('execution role evidence', () => {
    it('formats structured evidence and keeps legacy string errors', () => {
        expect(formatWorkflowError('legacy error')).toBe('legacy error');
        const text = formatWorkflowError({ ...failure, snapshot: { secret: 'hidden' } });
        for (const value of ['CARD_DRIFT', 'FINGERPRINT_CHANGED', 'original-1', 'role-a', 'worker-1', 'group-1']) {
            expect(text).toContain(value);
        }
        expect(text).not.toContain('hidden');
        expect(formatWorkflowError({ message: 'Failure' })).toBe('Failure');
    });

    it('locates original task IDs without guessing from agent/skill names or SDK task IDs', () => {
        const nodes = workflow.steps.map(step => ({ id: step.name, data: { subtasks: step.subtasks } }));
        expect(errorStepNames(workflow, failure)).toEqual(['first']);
        const marked = annotateWorkflowErrors(nodes, failure);
        expect(marked[0].data.executionError).toContain('CARD_DRIFT');
        expect(marked[1].data.executionError).toBeNull();
        expect(nodes[0].data).not.toHaveProperty('executionError');
        const sdkFailure = { ...failure, task_ids: ['sdk-task'], agent: 'same-agent', skill: 'same-skill' };
        expect(errorStepNames(workflow, sdkFailure)).toEqual([]);
        expect(annotateWorkflowErrors(nodes, sdkFailure).every(node => !node.data.executionError)).toBe(true);
        expect(annotateWorkflowErrors(marked, null).every(node => !node.data.executionError)).toBe(true);
    });

    it('shows resolution identity and flow-level errors even before any step starts', () => {
        const resolution = { execution_id: 'exec-1', catalog_version: 'v1', bindings: [{
            task_id: 'original-1', role_id: 'role-a', role_version: '1', role_skill_id: 'explore',
            instance_id: 'worker-1', execution_skill: 'analyze', selection_reason: 'priority',
        }], resolution_snapshot: { secret: 'private-snapshot-value' } };
        expect(formatRoleResolution(resolution)).not.toContain('private-snapshot-value');
        const html = renderToString(<ExecutionTimeline workflow={workflow} events={[
            { type: 'resolution', data: resolution, timestamp: 1 },
            { type: 'error', data: failure, timestamp: 2 },
        ]} />);
        expect(html).toContain('execution.roleResolution');
        expect(html).toContain('original-1');
        expect(html).toContain('worker-1');
        expect(html).toContain('role="alert"');
        expect(html).toContain('CARD_DRIFT');
        expect(html).not.toContain('private-snapshot-value');
    });

    it('does not attach unmapped errors to the most recent active step', () => {
        const events = [
            { type: 'start', data: { workflow: 'wf', steps: 2 }, timestamp: 1 },
            { type: 'step_start', data: { step: 'first' }, timestamp: 2 },
            { type: 'step_start', data: { step: 'second' }, timestamp: 3 },
            { type: 'error', data: { ...failure, task_ids: ['sdk-task'] }, timestamp: 4 },
        ];
        const html = renderToString(<ExecutionTimeline workflow={workflow} events={events} />);
        expect(html).toContain('CARD_DRIFT');
        expect(html.replaceAll('<!-- -->', '')).not.toContain('(1 失败)');
        const mapped = renderToString(<ExecutionTimeline workflow={workflow}
            events={[...events.slice(0, -1), { ...events.at(-1), data: failure }]} />);
        expect(mapped.replaceAll('<!-- -->', '')).toContain('(1 失败)');
    });
});
