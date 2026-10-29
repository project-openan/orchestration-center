// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const capture = vi.hoisted(() => ({ flow: null, toolbar: null, panel: null,
    flowApi: { screenToFlowPosition: vi.fn(point => point), fitView: vi.fn(), setCenter: vi.fn(), getNode: vi.fn() },
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/service/api.js', () => ({ getRoleCatalog: vi.fn().mockResolvedValue({ catalog_version: 'v1', roles: [] }) }));
vi.mock('@xyflow/react', async importOriginal => ({
    ...await importOriginal(),
    ReactFlowProvider: ({ children }) => children,
    ReactFlow: props => { capture.flow = props; return <div>{props.children}</div>; },
    Controls: () => null, Background: () => null,
    useReactFlow: () => capture.flowApi,
}));
vi.mock('./toolbar/index.jsx', () => ({ default: props => { capture.toolbar = props; return null; } }));
vi.mock('./property_panel/index.jsx', () => ({ default: props => {
    capture.panel = props;
    return <div data-testid="property-panel" />;
} }));
vi.mock('./sidebar/index.jsx', () => ({ default: () => <div data-testid="sidebar" /> }));

import UnifiedWorkflow from './index.jsx';
import { transformWorkflowToReactFlow } from './utils/index.jsx';

let container, root;
beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    capture.panel = null;
});
afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.clearAllMocks();
});

const template = binding => ({ id: 'wf', name: 'Design', catalog_version: 'v1', tags: ['original'], steps: [
    { name: 'role-step', type: 'AllSuccess', subtasks: [{ task_id: 'role-task', binding,
        agent: 'role-a', role_version: binding === 'role' ? '1' : undefined, skill: 'analyze', description: 'Analyze' }],
        next: [{ step: 'instance-step', condition: 'ready' }] },
    { name: 'instance-step', type: 'AllSuccess', subtasks: [{ task_id: 'instance-task', agent: 'worker', skill: 'merge' }] },
] });

describe('role and mixed canvas protection', () => {
    it('blocks every structural callback, keeps layout/select, and forwards original metadata', async () => {
        const design = template('role');
        const graph = transformWorkflowToReactFlow(design);
        const render = async (isDark = false, importedNodes = graph.nodes) => act(async () => root.render(
            <UnifiedWorkflow mode="edit" visible isDark={isDark} importedNodes={importedNodes}
                importedEdges={graph.edges} workflowMetadata={design} workflowId="wf" />
        ));
        await render();
        const initial = capture.flow.nodes;
        const initialEdges = capture.flow.edges;
        const target = initial.find(node => node.id === 'instance-step');
        const source = initial.find(node => node.id === 'role-step');
        expect(initial.every(node => !node.deletable && !node.data.editable)).toBe(true);
        expect(capture.flow.nodesConnectable).toBe(false);
        expect(capture.flow.edgesReconnectable).toBe(false);
        expect(capture.toolbar.workflowMetadata).toBe(design);
        expect(container.querySelector('[data-testid="sidebar"]')).toBeNull();
        await act(async () => capture.flow.onInit({ getNodes: () => [source, { ...target, position: source.position }] }));

        await act(async () => {
            capture.flow.onNodesChange([{ type: 'remove', id: source.id }, { type: 'replace', id: target.id, item: source }]);
            capture.flow.onEdgesChange([{ type: 'remove', id: initialEdges[0].id }]);
            capture.flow.onConnect({ source: source.id, target: target.id });
            capture.flow.onDrop({ preventDefault() {}, dataTransfer: { getData() { throw new Error('Drop must be blocked'); } } });
            capture.flow.onNodeDragStop({}, source);
            capture.toolbar.onClear();
        });
        expect(capture.flow.nodes).toEqual(initial);
        expect(capture.flow.edges).toEqual(initialEdges);
        expect(await capture.flow.onBeforeDelete({ nodes: initial, edges: initialEdges })).toEqual({ nodes: [], edges: [] });

        await act(async () => capture.flow.onSelectionChange({ nodes: [target], edges: [] }));
        expect(capture.panel.readOnly).toBe(true);
        await act(async () => {
            capture.panel.setNodes([]);
            capture.panel.setEdges([]);
            capture.panel.onDelete();
            capture.flow.onNodesChange([{ type: 'position', id: source.id, position: { x: 99, y: 55 } },
                { type: 'select', id: source.id, selected: true }]);
        });
        expect(capture.flow.nodes).toHaveLength(initial.length);
        expect(capture.flow.nodes.find(node => node.id === source.id).position).toEqual({ x: 99, y: 55 });
        expect(capture.flow.edges).toEqual(initialEdges);

        // Even an instance-bound runtime graph cannot unlock the original role design.
        const runtimeGraph = graph.nodes.map(node => ({ ...node, data: { ...node.data,
            subtasks: node.data.subtasks?.map(task => ({ ...task, binding: 'instance', agent: 'resolved' })) } }));
        await render(true, runtimeGraph);
        expect(capture.flow.nodes.every(node => !node.deletable && !node.data.editable)).toBe(true);
        expect(capture.toolbar.protectedWorkflow).toBe(true);
    });

    it('retains ordinary instance editing and protects START/END', async () => {
        const design = template('instance');
        const graph = transformWorkflowToReactFlow(design);
        await act(async () => root.render(<UnifiedWorkflow mode="edit" visible importedNodes={graph.nodes}
            importedEdges={graph.edges} workflowMetadata={design} />));
        expect(capture.flow.nodesConnectable).toBe(true);
        expect(container.querySelector('[data-testid="sidebar"]')).not.toBeNull();
        await act(async () => capture.flow.onNodesChange(graph.nodes.map(node => ({ type: 'remove', id: node.id }))));
        expect(capture.flow.nodes.map(node => node.type)).toEqual(['startNode', 'endNode']);
    });

    it('routes role task content edits into the design-steps snapshot used for saving', async () => {
        const design = template('role');
        const graph = transformWorkflowToReactFlow(design);
        await act(async () => root.render(<UnifiedWorkflow mode="edit" visible importedNodes={graph.nodes}
            importedEdges={graph.edges} workflowMetadata={design} workflowId="wf" />));
        await act(async () => capture.flow.onSelectionChange({ nodes: [graph.nodes.find(node => node.id === 'role-step')], edges: [] }));
        await act(async () => capture.panel.onRoleTaskContentChange('role-step', 0, { description: 'Edited by the user' }));
        const steps = capture.toolbar.designSteps;
        expect(steps[0].subtasks[0].description).toBe('Edited by the user');
        expect(steps[0].subtasks[0].task_id).toBe('role-task');
        // The original metadata stays untouched; only the snapshot moves.
        expect(capture.toolbar.workflowMetadata).toBe(design);
        expect(design.steps[0].subtasks[0].description).toBe('Analyze');
    });

    it('keeps the edit panel closed after its close button and clears RF selection', async () => {
        const design = template('role');
        const graph = transformWorkflowToReactFlow(design);
        await act(async () => root.render(<UnifiedWorkflow mode="edit" visible importedNodes={graph.nodes}
            importedEdges={graph.edges} workflowMetadata={design} workflowId="wf" />));
        // Mirror the RF-controlled select flow: the store applies the change and
        // the parent receives it through onNodesChange.
        await act(async () => capture.flow.onNodesChange([{ type: 'select', id: 'role-step', selected: true }]));
        const handler = capture.flow.onSelectionChange;
        await act(async () => capture.flow.onSelectionChange({ nodes: [graph.nodes.find(node => node.id === 'role-step')], edges: [] }));
        // Opening the panel re-renders the parent. RF v12 re-invokes
        // onSelectionChange whenever its identity changes, so an unstable
        // handler would immediately re-open the panel after close.
        expect(capture.flow.onSelectionChange).toBe(handler);
        expect(container.querySelector('[data-testid="property-panel"]')).not.toBeNull();
        await act(async () => capture.panel.onClose());
        expect(container.querySelector('[data-testid="property-panel"]')).toBeNull();
        expect(capture.flow.nodes.every(node => !node.selected)).toBe(true);
        expect(capture.flow.edges.every(edge => !edge.selected)).toBe(true);
    });
});
