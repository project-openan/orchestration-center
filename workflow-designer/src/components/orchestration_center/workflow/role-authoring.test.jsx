// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import UnifiedWorkflow from './index.jsx';
import OrchestrationCenter from '../index.jsx';
import { transformWorkflowToReactFlow, transformReactFlowToPSOP } from './utils/index.jsx';
import { getRoleCatalog, createWorkflow, getAgentCards } from '@/service/api.js';
import { workflowBinding, findRoleContractIssues } from './rolePolicy.js';

const capture = vi.hoisted(() => ({ flow: null, api: {
    screenToFlowPosition: point => point, fitView: vi.fn(), setCenter: vi.fn(), getNode: vi.fn(),
} }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/service/api.js', async importOriginal => {
    const actual = await importOriginal();
    return { ...Object.fromEntries(Object.keys(actual).map(key => [key, vi.fn().mockResolvedValue({ status: 'success', data: [] })])),
        getRoleCatalog: vi.fn(), createWorkflow: vi.fn(), getAgentCards: vi.fn() };
});
vi.mock('@/components/sandbox/SandboxDialog.jsx', () => ({ default: () => null }));
vi.mock('@xyflow/react', async importOriginal => ({
    ...await importOriginal(), ReactFlowProvider: ({ children }) => children,
    ReactFlow: props => { capture.flow = props; return <div>{props.children}</div>; },
    Controls: () => null, Background: () => null, useReactFlow: () => capture.api,
}));

const catalog = { catalog_version: 'current-v1', roles: [
    { role_id: 'analyst', role_version: '2', name: 'Analyst', skills: [
        { skill_id: 'inspect', name: 'Inspect', description: 'Inspect network' },
        { skill_id: 'repair', name: 'Repair', description: 'Repair network' },
        { skill_id: 'draft', name: 'Draft', review_status: 'draft' },
    ] },
    { role_id: 'draft-role', role_version: '1', review_status: 'draft', skills: [{ skill_id: 'x', name: 'Hidden' }] },
] };
let root, container;
beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div'); document.body.append(container); root = createRoot(container);
    getRoleCatalog.mockResolvedValue(catalog);
    getAgentCards.mockResolvedValue({ data: [] });
    createWorkflow.mockResolvedValue({ status: 'success', data: { workflow_id: 'saved-role' } });
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); vi.clearAllMocks(); });
const button = text => [...document.querySelectorAll('button')].find(item => item.textContent.trim() === text);
const click = async element => act(async () => element.click());
const change = async (element, value) => act(async () => {
    const proto = element.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(element, value);
    element.dispatchEvent(new Event(element.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }));
});
async function newRoleCanvas() {
    await act(async () => root.render(<UnifiedWorkflow mode="edit" newWorkflowBinding="role" />));
    await act(async () => capture.flow.onInit({ getNodes: () => capture.flow.nodes }));
}
async function drop(skill, x = 400) {
    let payload;
    const selector = [...container.querySelectorAll('select')].find(element => [...element.options].some(option => option.text === skill));
    const option = [...selector.options].find(option => option.text === skill);
    await change(selector, option.value);
    const card = container.querySelector(`[draggable="true"][data-skill-id="${option.value}"]`);
    await act(async () => card.dispatchEvent(Object.assign(new Event('dragstart', { bubbles: true }), {
        dataTransfer: { setData: (_type, data) => { payload = data; } },
    })));
    await act(async () => capture.flow.onDrop({ preventDefault() {}, clientX: x, clientY: 100,
        dataTransfer: { getData: () => payload } }));
}

it('opens the role palette directly from Orchestration Center role binding and Graph Builder', async () => {
    await act(async () => root.render(<OrchestrationCenter />));
    await change(container.querySelector('select[aria-label="orchestration.generationMode"]'), 'role');
    await click(button('orchestration.method_graph'));
    expect(container.querySelector('select[aria-label="workflow.roleCanvas.binding"]')).toBeNull();
    expect(getRoleCatalog.mock.calls).toEqual([[undefined]]);
    expect(getAgentCards).not.toHaveBeenCalled();
    expect(container.textContent).toContain('Analyst');
    expect(container.textContent).toContain('Inspect');
    await act(async () => capture.flow.onInit({ getNodes: () => capture.flow.nodes }));
    await drop('Inspect');
    expect(capture.flow.nodes.find(node => node.type === 'agentNode').data.subtasks[0]).toMatchObject({
        binding: 'role', agent: 'analyst', role_version: '2', skill: 'inspect',
    });
});

it('retains explicit instance binding when entering Graph Builder from Orchestration Center', async () => {
    await act(async () => root.render(<OrchestrationCenter />));
    await change(container.querySelector('select[aria-label="orchestration.generationMode"]'), 'instance');
    await click(button('orchestration.method_graph'));
    expect(container.querySelector('select[aria-label="workflow.roleCanvas.binding"]')).toBeNull();
    expect(container.querySelector('[aria-label="workflow.sidebar.title"]')).not.toBeNull();
    expect(getRoleCatalog).not.toHaveBeenCalled();
    expect(getAgentCards).toHaveBeenCalledOnce();
    await click(button('workflow.toolbar.back'));
    expect(container.querySelector('select[aria-label="orchestration.generationMode"]').value).toBe('instance');
    await change(container.querySelector('select[aria-label="orchestration.generationMode"]'), 'role');
    await click(button('orchestration.method_graph'));
    expect(container.textContent).toContain('Inspect');
    await click(button('workflow.toolbar.back'));
    expect(container.querySelector('select[aria-label="orchestration.generationMode"]').value).toBe('role');
});

it('creates, saves and reopens independent role tasks using the same PSOP contract as generated designs', async () => {
    await newRoleCanvas();
    expect(capture.flow.nodesConnectable).toBe(true);
    expect(container.textContent).not.toContain('Hidden');
    expect(container.textContent).not.toContain('Draft');
    await drop('Inspect'); await drop('Repair', 800);
    const steps = capture.flow.nodes.filter(node => node.type === 'agentNode');
    expect(steps).toHaveLength(2);
    const tasks = steps.flatMap(node => node.data.subtasks);
    expect(new Set(tasks.map(task => task.task_id)).size).toBe(2);
    expect(tasks[0]).toMatchObject({ binding: 'role', agent: 'analyst', role_version: '2', skill: 'inspect', status: 'pending' });
    expect(tasks[0]).not.toHaveProperty('skillsList');
    await act(async () => {
        capture.flow.onConnect({ source: 'startNode', target: steps[0].id });
        capture.flow.onConnect({ source: steps[0].id, target: steps[1].id });
        capture.flow.onConnect({ source: steps[1].id, target: 'endNode' });
        capture.flow.onNodesChange(steps.map(node => ({ type: 'select', id: node.id, selected: true })));
    });
    const savedEvent = vi.fn(); window.addEventListener('orchestrate:workflow-saved', savedEvent);
    try {
        await click(button('workflow.toolbar.export'));
        await change(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Canvas role flow');
        await click(button('common.confirm'));
        expect(createWorkflow).toHaveBeenCalledOnce();
        const saved = createWorkflow.mock.calls[0][0];
        expect(saved).toMatchObject({ catalog_version: 'current-v1', source: 'graph_editor' });
        expect(saved.steps[0].next).toEqual([{ step: steps[1].id, condition: '' }]);
        expect(saved.steps[1].next).toEqual([{ step: 'end', condition: '' }]);
        expect(saved.steps.flatMap(step => step.subtasks).every(task => !task.binding_group)).toBe(true);
        expect(savedEvent).toHaveBeenCalledOnce();
        const reopened = transformWorkflowToReactFlow(saved);
        expect(transformReactFlowToPSOP(reopened.nodes, reopened.edges, saved, { fromCanvas: true })).toEqual(saved);
        await act(async () => root.render(<UnifiedWorkflow key="reopened" mode="edit" workflowId="saved-role"
            workflowMetadata={saved} importedNodes={reopened.nodes} importedEdges={reopened.edges} />));
        expect(getRoleCatalog.mock.calls).toEqual([[undefined], ['current-v1']]);
        expect(capture.flow.nodesConnectable).toBe(true);
        expect(getAgentCards).not.toHaveBeenCalled();
    } finally { window.removeEventListener('orchestrate:workflow-saved', savedEvent); }
});

it('edits the current role topology and task content instead of exporting stale metadata', async () => {
    const onSaveSuccess = vi.fn();
    const design = { name: 'Generated', catalog_version: 'current-v1', steps: [
        { name: 'generated', type: 'AllSuccess', subtasks: [{ task_id: 't1', binding: 'role', agent: 'analyst', role_version: '2', skill: 'inspect', description: 'Old' }] },
    ] };
    const graph = transformWorkflowToReactFlow(design);
    await act(async () => root.render(<UnifiedWorkflow mode="edit" workflowMetadata={design} importedNodes={graph.nodes} importedEdges={graph.edges} onSaveSuccess={onSaveSuccess} />));
    expect(capture.flow.nodesConnectable).toBe(true);
    await act(async () => capture.flow.onSelectionChange({ nodes: [capture.flow.nodes.find(node => node.id === 'generated')], edges: [] }));
    await change(container.querySelector('[data-testid="role-task-description"]'), 'Updated');
    const stepName = [...container.querySelectorAll('input')].find(element => element.value === 'generated');
    await change(stepName, 'renamed');
    await act(async () => capture.flow.onInit({ getNodes: () => capture.flow.nodes }));
    await drop('Repair', 5000);
    const added = capture.flow.nodes.find(node => node.type === 'agentNode' && node.id !== 'generated');
    const previousEnd = capture.flow.edges.find(edge => edge.source === 'generated');
    await act(async () => {
        capture.flow.onReconnect(previousEnd, { source: 'generated', target: added.id });
        capture.flow.onConnect({ source: added.id, target: 'END_OF_WORKFLOW' });
    });
    await click(button('workflow.toolbar.export')); await click(button('common.confirm'));
    const saved = createWorkflow.mock.calls[0][0];
    expect(saved.steps[0].name).toBe('renamed');
    expect(saved.steps[0].subtasks[0].description).toBe('Updated');
    expect(saved.steps).toHaveLength(2);
    expect(saved.steps[0].next).toEqual([{ step: added.id, condition: '' }]);
    const [savedId, savedDesign, savedGraph] = onSaveSuccess.mock.calls[0];
    expect(savedId).toBe('saved-role');
    expect(savedDesign).toEqual(saved);
    expect(savedGraph.nodes.find(node => node.id === 'renamed').data._templateStep.subtasks[0].description).toBe('Updated');
    expect(savedGraph.nodes.find(node => node.id === added.id).position).toEqual(added.position);
    await act(async () => root.render(<UnifiedWorkflow mode="view" workflowId={savedId} workflowMetadata={savedDesign}
        nodes={savedGraph.nodes} edges={savedGraph.edges} importedNodes={savedGraph.nodes} importedEdges={savedGraph.edges} />));
    await act(async () => root.render(<UnifiedWorkflow mode="edit" workflowId={savedId} workflowMetadata={savedDesign}
        nodes={savedGraph.nodes} edges={savedGraph.edges} importedNodes={savedGraph.nodes} importedEdges={savedGraph.edges} />));
    expect(capture.flow.nodes.find(node => node.id === 'renamed').data.subtasks[0].description).toBe('Updated');
    expect(capture.flow.edges.some(edge => edge.source === 'renamed' && edge.target === added.id)).toBe(true);
    expect(design.steps[0].subtasks[0].description).toBe('Old');
    expect(getAgentCards).not.toHaveBeenCalled();
});

it('preserves existing binding metadata through content edits and saving without exposing group authoring', async () => {
    const design = { id: 'legacy', name: 'Legacy design', catalog_version: 'current-v1', steps: [{
        name: 'work', type: 'AllSuccess', subtasks: [{ task_id: 't1', binding: 'role',
            agent: 'analyst', role_version: '2', skill: 'inspect', description: 'Original', binding_group: 'legacy-session' }],
    }] };
    const graph = transformWorkflowToReactFlow(design);
    await act(async () => root.render(<UnifiedWorkflow mode="edit" workflowId="legacy" workflowMetadata={design}
        importedNodes={graph.nodes} importedEdges={graph.edges} />));
    await act(async () => capture.flow.onSelectionChange({ nodes: [capture.flow.nodes.find(node => node.id === 'work')], edges: [] }));
    expect(container.textContent).not.toContain('legacy-session');
    expect(container.querySelector('[data-testid="binding-group-actions"]')).toBeNull();
    expect(container.querySelector('[aria-label="workflow.roleCanvas.group"]')).toBeNull();
    expect(container.querySelector('[aria-label="workflow.roleCanvas.selectTask"]')).toBeNull();
    await change(container.querySelector('[data-testid="role-task-description"]'), 'Updated');
    await click(button('workflow.toolbar.export')); await click(button('common.confirm'));
    const saved = createWorkflow.mock.calls[0][0];
    expect(saved.steps[0].subtasks[0]).toMatchObject({ description: 'Updated', binding_group: 'legacy-session' });
    const reopened = transformWorkflowToReactFlow(saved);
    expect(reopened.nodes.find(node => node.id === 'work').data.subtasks[0].binding_group).toBe('legacy-session');
});

it('keeps saved role designs read-only when their exact catalog is unavailable without requesting latest', async () => {
    getRoleCatalog.mockRejectedValueOnce(new Error('Unavailable'));
    const design = { id: 'old', catalog_version: 'retired', steps: [{ name: 'work', subtasks: [
        { task_id: 't1', binding: 'role', agent: 'analyst', role_version: '2', skill: 'inspect', description: 'd' },
    ] }] };
    const graph = transformWorkflowToReactFlow(design);
    await act(async () => root.render(<UnifiedWorkflow mode="edit" workflowMetadata={design} importedNodes={graph.nodes} importedEdges={graph.edges} />));
    expect(capture.flow.nodesConnectable).toBe(false);
    expect(getRoleCatalog.mock.calls).toEqual([['retired']]);
    const work = capture.flow.nodes.find(node => node.id === 'work');
    await act(async () => capture.flow.onNodesChange([{ type: 'remove', id: work.id }]));
    expect(capture.flow.nodes.some(node => node.id === work.id)).toBe(true);
    expect(container.textContent).toContain('workflow.roleEditUnavailable');
});

it('shows task-level catalog rejection on save and does not broadcast success', async () => {
    createWorkflow.mockRejectedValueOnce({ response: { data: { message: { code: 'INVALID_ROLE_SKILL', message: 'Task t1 approval withdrawn' } } } });
    await newRoleCanvas(); await drop('Inspect');
    const node = capture.flow.nodes.find(node => node.type === 'agentNode');
    await act(async () => {
        capture.flow.onConnect({ source: 'startNode', target: node.id });
        capture.flow.onConnect({ source: node.id, target: 'endNode' });
    });
    const savedEvent = vi.fn(); window.addEventListener('orchestrate:workflow-saved', savedEvent);
    try {
        await click(button('workflow.toolbar.export'));
        await change(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Rejected');
        await click(button('common.confirm'));
        expect(document.body.textContent).toContain('INVALID_ROLE_SKILL: Task t1 approval withdrawn');
        expect(savedEvent).not.toHaveBeenCalled();
    } finally { window.removeEventListener('orchestrate:workflow-saved', savedEvent); }
});

it('keeps an empty or unavailable role catalog protected and prevents saving an empty role graph', async () => {
    getRoleCatalog.mockResolvedValueOnce({ catalog_version: 'empty', roles: [] });
    await newRoleCanvas();
    expect(capture.flow.nodesConnectable).toBe(false);
    expect(container.textContent).toContain('workflow.roleCanvas.emptyCatalog');
    await click(button('workflow.toolbar.export'));
    await change(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Empty');
    await click(button('common.confirm'));
    expect(createWorkflow).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('workflow.roleCanvas.emptyWorkflow');
});

it('blocks instance drops, draft references and SelfLoop while allowing role task deletion', async () => {
    await newRoleCanvas();
    const inject = async payload => act(async () => capture.flow.onDrop({ preventDefault() {}, clientX: 400, clientY: 100,
        dataTransfer: { getData: () => JSON.stringify(payload) } }));
    await inject({ agent: 'worker', skill: 'inspect' });
    expect(capture.flow.nodes.filter(node => node.type === 'agentNode')).toHaveLength(0);
    await inject({ binding: 'role', agent: 'analyst', role_version: '2', skill: 'draft' });
    expect(capture.flow.nodes.filter(node => node.type === 'agentNode')).toHaveLength(0);
    await drop('Inspect');
    const node = capture.flow.nodes.find(node => node.type === 'agentNode');
    await act(async () => capture.flow.onSelectionChange({ nodes: [node], edges: [] }));
    expect([...container.querySelectorAll('option')].some(option => option.value === 'SelfLoop')).toBe(false);
    await click(button('workflow.panel.removeSubtask'));
    expect(capture.flow.nodes.find(item => item.id === node.id).data.subtasks).toEqual([]);
    expect(capture.flow.nodesConnectable).toBe(true);
});

it('retains protocol validation for existing role contracts', () => {
    const nodes = [{ id: 'work', data: { type: 'SelfLoop', subtasks: [
        { task_id: 'a', binding: 'role', agent: 'analyst', role_version: '2', skill: 'inspect' },
    ] } }];
    expect(workflowBinding(nodes)).toBe('role');
    expect(findRoleContractIssues(nodes).map(issue => issue.code)).toEqual(['ROLE_SELF_LOOP']);
});
