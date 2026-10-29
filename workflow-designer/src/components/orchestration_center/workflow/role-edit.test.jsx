// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import PropertyPanel from './property_panel/index.jsx';
import Toolbar from './toolbar/index.jsx';
import { transformWorkflowToReactFlow } from './utils/index.jsx';
import { approvedRoleSkills, findInvalidRoleReferences, isApprovedRoleSkill } from './rolePolicy.js';
import { createWorkflow, getAgentCards } from '@/service/api.js';

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (key, params) => params
        ? `${key} [${Object.entries(params).map(([name, value]) => `${name}=${value}`).join(', ')}]`
        : key }),
}));
vi.mock('@/service/api.js', () => ({ createWorkflow: vi.fn(), getAgentCards: vi.fn() }));
vi.mock('@/components/sandbox/SandboxDialog.jsx', () => ({ default: () => <div data-testid="sandbox" /> }));

let root, container;
beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    createWorkflow.mockResolvedValue({ data: { workflow_id: 'wf' } });
    getAgentCards.mockResolvedValue({ data: [] });
});
afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.clearAllMocks();
});
const click = async button => act(async () => button.click());
const button = text => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === text);
const input = async (element, value) => act(async () => {
    const prototype = element.tagName === 'SELECT' ? HTMLSelectElement.prototype
        : element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});

const CATALOG = {
    catalog_version: 'v1',
    roles: [
        {
            role_id: 'role-a', role_version: '1', name: 'Role A', review_status: 'approved',
            skills: [
                { skill_id: 'analyze', name: 'Analyze', review_status: 'approved' },
                { skill_id: 'draft-skill', name: 'Draft', review_status: 'draft' },
            ],
        },
        { role_id: 'role-b', role_version: '2', name: 'Role B', review_status: 'draft', skills: [] },
    ],
};

// Exact shape of GET /rest/v1/orchestrate/role-catalog: approved-only
// projection, no review_status field on roles or skills.
const PROJECTION = {
    catalog_version: 'v1',
    roles: [{ role_id: 'role-a', role_version: '1', name: 'Role A', description: 'd',
        skills: [{ skill_id: 'analyze', name: 'Analyze', description: 'd' }] }],
};

const graph = () => ({
    nodes: [
        { id: 'start', type: 'startNode', data: {} },
        {
            id: 'step-1', type: 'agentNode', data: {
                label: 'Analyze step', catalogVersion: 'v1', agent: 'role-a', skill: 'analyze',
                subtasks: [
                    { task_id: 't1', binding: 'role', agent: 'role-a', role_version: '1', skill: 'analyze',
                        description: 'Analyze', binding_group: 'session' },
                    { task_id: 't2', binding: 'role', agent: 'role-a', role_version: '1', skill: 'draft-skill',
                        description: 'Sibling', binding_group: 'session' },
                    { task_id: 'legacy', agent: 'legacy-worker', skill: 'merge', description: 'Merge' },
                ],
            },
        },
        { id: 'end', type: 'endNode', data: {} },
    ],
    edges: [{ id: 'e1', source: 'start', target: 'step-1' }, { id: 'e2', source: 'step-1', target: 'end' }],
});

describe('role catalog advisory validation', () => {
    it('authorizes only approved (role, version, skill) triples of the exact release', () => {
        expect(approvedRoleSkills(CATALOG)).toEqual(new Set(['role-a@1#analyze']));
        expect(isApprovedRoleSkill(CATALOG, 'role-a', '1', 'analyze')).toBe(true);
        expect(isApprovedRoleSkill(CATALOG, 'role-a', '1', 'draft-skill')).toBe(false);
        expect(isApprovedRoleSkill(CATALOG, 'role-b', '2', 'analyze')).toBe(false);
        expect(isApprovedRoleSkill(null, 'role-a', '1', 'analyze')).toBe(false);
    });

    it('accepts the served approved-only projection, which carries no review_status', () => {
        expect(approvedRoleSkills(PROJECTION)).toEqual(new Set(['role-a@1#analyze']));
        expect(isApprovedRoleSkill(PROJECTION, 'role-a', '1', 'analyze')).toBe(true);
        expect(findInvalidRoleReferences(graph().nodes, PROJECTION).map(issue => issue.task_id)).toEqual(['t2']);
    });

    it('locates invalid references per node and task without a frontend verdict on missing catalog', () => {
        const nodes = graph().nodes;
        expect(findInvalidRoleReferences(nodes, CATALOG).map(issue => issue.task_id)).toEqual(['t2']);
        expect(findInvalidRoleReferences(nodes, null)).toEqual([]);
    });
});

describe('role task content editing in the property panel', () => {
    const renderPanel = async (catalog, nodes) => {
        const g = nodes || graph();
        const selected = g.nodes.find(node => node.id === 'step-1');
        const onRoleTaskContentChange = vi.fn();
        await act(async () => root.render(<PropertyPanel selectedElement={selected} nodes={g.nodes}
            edges={g.edges} setNodes={vi.fn()} setEdges={vi.fn()} catalog={catalog}
            onRoleTaskContentChange={onRoleTaskContentChange} />));
        return onRoleTaskContentChange;
    };

    it('edits description, role and skill of role tasks while instance tasks stay read-only', async () => {
        const onRoleTaskContentChange = await renderPanel(CATALOG);

        const cards = [...container.querySelectorAll('[data-testid="role-task-card"]')];
        expect(cards).toHaveLength(3);

        const editable = cards.filter(card => card.querySelector('[data-testid="role-task-description"]'));
        expect(editable).toHaveLength(2);
        expect(cards[2].querySelector('[data-testid="role-task-description"]')).toBeNull();

        await input(cards[0].querySelector('[data-testid="role-task-description"]'), 'New description');
        expect(onRoleTaskContentChange).toHaveBeenCalledWith('step-1', 0, { description: 'New description' });

        // Switching the role identity clears the skill for re-selection.
        await input(cards[0].querySelector('[data-testid="role-task-role"]'), 'role-a@1');
        expect(onRoleTaskContentChange).toHaveBeenLastCalledWith('step-1', 0,
            { agent: 'role-a', role_version: '1', skill: null });

        await input(cards[0].querySelector('[data-testid="role-task-skill"]'), 'analyze');
        expect(onRoleTaskContentChange).toHaveBeenLastCalledWith('step-1', 0, { skill: 'analyze' });

        // Draft skills are not selectable; the invalid sibling is flagged.
        const skillOptions = [...cards[0].querySelectorAll('[data-testid="role-task-skill"] option')]
            .map(option => option.value);
        expect(skillOptions).toContain('analyze');
        expect(skillOptions).not.toContain('draft-skill');
        const alerts = [...document.querySelectorAll('[role="alert"]')].map(alert => alert.textContent);
        expect(alerts.some(text => text.includes('workflow.roleEditInvalidReference'))).toBe(true);
        expect(alerts.filter(text => text.includes('workflow.roleEditInvalidReference'))).toHaveLength(1);
    });

    it('lists the whole binding group so members can be fixed in one session', async () => {
        await renderPanel(CATALOG);
        const members = container.querySelector('[data-testid="role-task-group-members"]');
        expect(members).not.toBeNull();
        expect(members.textContent).toContain('Analyze step');
        expect(members.textContent).toContain('role-a@1');
        expect(members.textContent).toContain('✗');
    });

    it('keeps the raw read-only view when the catalog release is unavailable', async () => {
        const onRoleTaskContentChange = await renderPanel(null);
        expect(container.querySelector('[data-testid="role-task-description"]')).toBeNull();
        expect(container.querySelector('input,select')).toBeNull();
        expect(onRoleTaskContentChange).not.toHaveBeenCalled();
        expect(container.textContent).toContain('workflow.roleEditUnavailable');
    });

    it('offers role and skill selections for the real catalog projection shape', async () => {
        await renderPanel(PROJECTION);
        const card = container.querySelector('[data-testid="role-task-card"]');
        const roleOptions = [...card.querySelectorAll('[data-testid="role-task-role"] option')]
            .map(option => option.value);
        expect(roleOptions).toContain('role-a@1');
        const skillOptions = [...card.querySelectorAll('[data-testid="role-task-skill"] option')]
            .map(option => option.value);
        expect(skillOptions).toContain('analyze');
        // The served projection holds only approved entries: no invalid flag.
        expect([...document.querySelectorAll('[role="alert"]')].map(alert => alert.textContent))
            .not.toContain(expect.stringContaining('workflow.roleEditInvalidReference'));
    });
});

describe('save gate for invalid role references', () => {
    const design = () => ({ id: 'wf', name: 'Role flow', description: 'd', catalog_version: 'v1',
        steps: [{ name: 'analyze', type: 'AllSuccess', context_from: ['*'], next: [],
            subtasks: [
                { task_id: 't1', binding: 'role', agent: 'role-a', role_version: '1', skill: 'analyze',
                    description: 'Analyze', binding_group: 'session' },
                { task_id: 't2', binding: 'role', agent: 'role-a', role_version: '1', skill: 'draft-skill',
                    description: 'Sibling', binding_group: 'session' },
            ] }] });

    const renderToolbar = async (catalog, metadata) => {
        const graph = transformWorkflowToReactFlow(metadata || design());
        await act(async () => root.render(<Toolbar {...graph} workflowId="wf"
            workflowName="Role flow" workflowDescription="d" catalog={catalog}
            workflowMetadata={metadata || design()} />));
    };

    it('blocks saving and names the offending tasks when references are unapproved', async () => {
        await renderToolbar(CATALOG);
        await click(button('workflow.toolbar.export'));
        await click(button('common.confirm'));
        expect(document.body.textContent).toContain('workflow.validate.invalidRoleReference');
        expect(document.body.textContent).toContain('tasks=analyze/t2');
        expect(createWorkflow).not.toHaveBeenCalled();
    });

    it('saves when every role reference is approved', async () => {
        const metadata = design();
        metadata.steps[0].subtasks[1].skill = 'analyze';
        await renderToolbar(CATALOG, metadata);
        await click(button('workflow.toolbar.export'));
        await input(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Role flow');
        await click(button('common.confirm'));
        expect(createWorkflow).toHaveBeenCalledOnce();
    });

    it('serializes role task content edits from the design-steps snapshot, not stale metadata', async () => {
        const metadata = design();
        metadata.steps[0].subtasks[1].skill = 'analyze';
        const graph = transformWorkflowToReactFlow(metadata);
        const editedSteps = JSON.parse(JSON.stringify(metadata.steps));
        editedSteps[0].subtasks[0].description = 'Edited by the user';
        await act(async () => root.render(<Toolbar {...graph} workflowId="wf" workflowName="Role flow"
            workflowDescription="d" catalog={CATALOG} workflowMetadata={metadata}
            designSteps={editedSteps} protectedWorkflow />));
        await click(button('workflow.toolbar.export'));
        await input(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Role flow');
        await click(button('common.confirm'));
        expect(createWorkflow).toHaveBeenCalledOnce();
        const payload = createWorkflow.mock.calls[0][0];
        expect(payload.steps[0].subtasks[0].description).toBe('Edited by the user');
        // The untouched original metadata never leaks into the saved snapshot.
        expect(metadata.steps[0].subtasks[0].description).toBe('Analyze');
    });
});
