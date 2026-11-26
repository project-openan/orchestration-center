// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { expect, it } from 'vitest';
import { projectRoleExecution, roleTemplateFromEvents } from './workflowProjection.js';
import { transformReactFlowToPSOP, transformWorkflowToReactFlow } from '../orchestration_center/workflow/utils/index.jsx';

it('isolates status and instance evidence without adding serial edges or rewriting role identity', () => {
    const template = { id: 'wf', name: 'Design', catalog_version: 'v1', steps: ['first', 'parallel'].map((name, index) => ({
        name, next: null, subtasks: [{ task_id: `original-${index}`, binding: 'role', role_version: '1',
            agent: 'role-a', skill: 'explore', status: 'pending' }],
    })) };
    const runtime = { ...template, steps: template.steps.map(step => ({ ...step,
        subtasks: step.subtasks.map(task => ({ ...task, binding: 'instance', agent: 'worker', skill: 'analyze', status: 'success' })),
    })) };
    const projected = projectRoleExecution(template, runtime);
    expect(projected.steps[0].subtasks[0]).toMatchObject({ binding: 'role', agent: 'role-a', skill: 'explore',
        runtimeInstance: 'worker', runtimeSkill: 'analyze', status: 'success' });
    expect(template.steps[0].subtasks[0].status).toBe('pending');
    expect(template.steps[0].subtasks[0]).not.toHaveProperty('runtimeInstance');
    const graph = transformWorkflowToReactFlow(projected);
    expect(graph.edges.some(edge => edge.source === 'first' && edge.target === 'parallel')).toBe(false);
    expect(transformReactFlowToPSOP(graph.nodes, graph.edges, template)).toEqual({ ...template, description: '', tags: [] });
    const unmapped = { steps: [{ subtasks: [{ ...runtime.steps[0].subtasks[0], task_id: 'sdk-task' }] }] };
    expect(projectRoleExecution(template, unmapped).steps[0].subtasks[0].status).toBe('pending');
    expect(roleTemplateFromEvents([{ type: 'resolution', data: { resolution_snapshot: { template } } }])).toBe(template);
    expect(roleTemplateFromEvents([{ type: 'psop_update', data: { psop: JSON.stringify(template) } }])).toEqual(template);
    expect(roleTemplateFromEvents([{ type: 'psop_update', data: { psop: '{bad' } }])).toBeNull();
    expect(roleTemplateFromEvents(null)).toBeNull();
});
