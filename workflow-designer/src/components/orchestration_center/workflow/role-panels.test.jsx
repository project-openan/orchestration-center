// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Toolbar from './toolbar/index.jsx';
import PropertyPanel from './property_panel/index.jsx';
import { transformWorkflowToReactFlow } from './utils/index.jsx';
import { createWorkflow, getAgentCards } from '@/service/api.js';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
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
    const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, value);
    element.dispatchEvent(new Event('input', { bubbles: true }));
});
const design = () => ({ id: 'wf', name: 'Role flow', description: 'Description', tags: ['kept'], catalog_version: 'v1',
    user_intent: 'Original intent', related_preflow: 'preflow', source: 'template', created_at: '2026-10-23T00:00:00Z',
    steps: [{ name: 'analyze', type: 'AllSuccess', layer: 2, context_from: ['*'], next: [],
        subtasks: [{ task_id: 'task-1', binding: 'role', role_version: '1', binding_group: 'session',
            agent: 'role-a', skill: 'analyze', description: 'Task', status: 'pending' }] }],
});

describe('role toolbar and properties', () => {
    it('shows a save gate rejection instead of hiding its catalog reason', async () => {
        const metadata = design();
        createWorkflow.mockRejectedValueOnce({ response: { data: { message: 'CATALOG_VERSION_UNAVAILABLE' } } });
        await act(async () => root.render(<Toolbar {...transformWorkflowToReactFlow(metadata)} workflowMetadata={metadata}
            workflowId={metadata.id} workflowName={metadata.name} workflowDescription={metadata.description} />));
        await click(button('workflow.toolbar.export'));
        await click(button('common.confirm'));
        expect(document.body.textContent).toContain('CATALOG_VERSION_UNAVAILABLE');
    });

    it('downloads the original design without saving or querying an unavailable catalog', async () => {
        const metadata = design();
        const graph = transformWorkflowToReactFlow(metadata);
        graph.nodes.find(node => node.type === 'agentNode').data.subtasks[0].status = 'success';
        let downloaded;
        vi.stubGlobal('URL', { createObjectURL: vi.fn(blob => { downloaded = blob; return 'blob:design'; }), revokeObjectURL: vi.fn() });
        const anchor = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
        try {
            await act(async () => root.render(<Toolbar {...graph} workflowMetadata={metadata}
                workflowId={metadata.id} workflowName={metadata.name} workflowDescription={metadata.description} />));
            await click(button('workflow.toolbar.export'));
            await click(button('workflow.downloadDesign'));
            const text = await new Promise(resolve => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result);
                reader.readAsText(downloaded);
            });
            expect(JSON.parse(text)).toEqual(metadata);
            expect(createWorkflow).not.toHaveBeenCalled();
            expect(getAgentCards).not.toHaveBeenCalled();
            expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:design');
        } finally {
            anchor.mockRestore();
            vi.unstubAllGlobals();
        }
    });

    it('resets save drafts when switching to a template with empty metadata', async () => {
        const first = design();
        const second = { ...design(), id: 'second', name: 'Second', description: null, tags: null };
        const render = async metadata => act(async () => root.render(<Toolbar {...transformWorkflowToReactFlow(metadata)}
            workflowId={metadata.id} workflowName={metadata.name} workflowDescription={metadata.description} workflowMetadata={metadata} />));
        await render(first);
        await click(button('workflow.toolbar.export'));
        await input(document.querySelector('textarea'), 'Unrelated draft');
        await click(button('common.cancel'));
        await render(second);
        await click(button('workflow.toolbar.export'));
        expect(document.querySelector('textarea').value).toBe('');
        await click(button('common.confirm'));
        expect(createWorkflow).toHaveBeenCalledWith(second);
    });

    it('saves editable metadata while preserving original design and disabling sandbox/clear', async () => {
        const metadata = design();
        const graph = transformWorkflowToReactFlow(metadata);
        graph.nodes.find(node => node.type === 'agentNode').data.subtasks[0].agent = 'runtime-worker';
        const onClear = vi.fn(), onSaveSuccess = vi.fn();
        await act(async () => root.render(<Toolbar {...graph} workflowId={metadata.id} workflowName={metadata.name}
            workflowDescription={metadata.description} workflowMetadata={metadata} onClear={onClear} onSaveSuccess={onSaveSuccess} />));
        expect(button('workflow.toolbar.sandbox').disabled).toBe(true);
        expect(button('workflow.toolbar.sandbox').title).toBe('workflow.roleSandboxUnsupported');
        expect(button('workflow.toolbar.clear').disabled).toBe(true);
        await click(button('workflow.toolbar.clear'));
        expect(onClear).not.toHaveBeenCalled();
        expect(document.querySelector('[data-testid="sandbox"]')).toBeNull();

        await click(button('workflow.toolbar.export'));
        await input(document.querySelector('input[placeholder="workflow.export.namePlaceholder"]'), 'Renamed');
        await input(document.querySelector('textarea'), 'Edited description');
        await input(document.querySelector('input[aria-label="workflow.tagsLabel 1"]'), 'edited');
        await click(button('common.confirm'));
        expect(createWorkflow).toHaveBeenCalledWith({ ...metadata, name: 'Renamed', description: 'Edited description', tags: ['edited'] });
        expect(onSaveSuccess).toHaveBeenCalledWith('wf');
        expect(metadata.steps[0].subtasks[0].agent).toBe('role-a');
        expect(metadata.tags).toEqual(['kept']);
    });

    it('shows role identity and mixed instance properties without loading or exposing agent editing', async () => {
        const metadata = design();
        metadata.steps[0].subtasks.push({ task_id: 'legacy', agent: 'legacy-worker', skill: 'merge', description: 'Merge' });
        const graph = transformWorkflowToReactFlow(metadata);
        const selected = graph.nodes.find(node => node.type === 'agentNode');
        const setNodes = vi.fn(), setEdges = vi.fn();
        await act(async () => root.render(<PropertyPanel nodes={graph.nodes} edges={graph.edges}
            selectedElement={selected} setNodes={setNodes} setEdges={setEdges} />));
        expect(getAgentCards).not.toHaveBeenCalled();
        expect(container.textContent).toContain('role-a');
        expect(container.textContent).not.toContain('session');
        expect(container.textContent).toContain('legacy-worker');
        expect(container.querySelector('input,textarea,select')).toBeNull();
        expect(setNodes).not.toHaveBeenCalled();
        expect(setEdges).not.toHaveBeenCalled();
    });

    it('keeps sandbox and clear available on ordinary instance designs', async () => {
        const onClear = vi.fn();
        await act(async () => root.render(<Toolbar nodes={[]} edges={[]} workflowId="legacy" onClear={onClear} />));
        expect(button('workflow.toolbar.sandbox').disabled).toBe(false);
        await click(button('workflow.toolbar.clear'));
        expect(onClear).toHaveBeenCalledOnce();
        await click(button('workflow.toolbar.sandbox'));
        expect(document.querySelector('[data-testid="sandbox"]')).not.toBeNull();
    });
});
