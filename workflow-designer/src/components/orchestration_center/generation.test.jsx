// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import OrchestrationCenter from './index.jsx';
import { generateWorkflowFromIntent, getAgentCards, handlePlan, parsePdf, getRoleCatalog } from '@/service/api.js';

const state = vi.hoisted(() => ({ packages: null, t: key => key }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: state.t }) }));
vi.mock('@/service/api.js', async importOriginal => {
    const actual = await importOriginal();
    return { ...Object.fromEntries(Object.keys(actual).map(key => [key, vi.fn().mockResolvedValue({ data: [] })])),
        getAgentCards: vi.fn().mockRejectedValue(new Error('Registry offline')),
    };
});
vi.mock('./workflow/index.jsx', () => ({ default: () => <div data-testid="workflow" /> }));
vi.mock('./packages/index.jsx', () => ({ default: props => { state.packages = props; return null; } }));

let root, container;
beforeEach(async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    await act(async () => root.render(<OrchestrationCenter />));
});
afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.clearAllMocks();
});
const button = text => [...container.querySelectorAll('button')].find(item => item.textContent.trim() === text);
const click = async text => act(async () => button(text).click());
const writeIntent = async () => {
    await click('orchestration.method_ai');
    await act(async () => {
        const input = container.querySelector('textarea');
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(input, 'Analyze');
        input.dispatchEvent(new Event('input', { bubbles: true }));
    });
};

it('defaults new intent generation to role without consulting an offline registry', async () => {
    generateWorkflowFromIntent.mockResolvedValueOnce({ id: 'wf', name: 'Role', catalog_version: 'v1', steps: [] });
    expect(container.querySelector('select').value).toBe('role');
    await writeIntent();
    await click('orchestration.generate');
    expect(generateWorkflowFromIntent).toHaveBeenCalledWith('Analyze', undefined, { binding: 'role' });
    expect(getAgentCards).not.toHaveBeenCalled();
    expect(container.querySelector('[data-testid="workflow"]')).not.toBeNull();
});

it('shows structured errors without silently falling back and permits explicit instance mode', async () => {
    generateWorkflowFromIntent.mockRejectedValueOnce({ response: { data: { message: { code: 'NO_APPROVED_ROLE_SKILL', message: 'No approved skills' } } } });
    await writeIntent();
    await click('orchestration.generate');
    expect(container.querySelector('[role="alert"]').textContent).toContain('NO_APPROVED_ROLE_SKILL');
    expect(container.querySelector('select').value).toBe('role');
    await act(async () => {
        const select = container.querySelector('select');
        select.value = 'instance';
        select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    generateWorkflowFromIntent.mockResolvedValueOnce({ id: 'wf', name: 'Instance', steps: [] });
    await click('orchestration.generate');
    expect(generateWorkflowFromIntent).toHaveBeenLastCalledWith('Analyze', undefined, { binding: 'instance' });
});

it('generates from PDF/PreFlow without loading AgentCards in role mode', async () => {
    getRoleCatalog.mockResolvedValueOnce({ catalog_version: 'v1', roles: [] });
    parsePdf.mockResolvedValueOnce({ name: 'PreFlow', steps_md: 'Analyze' });
    handlePlan.mockResolvedValueOnce({ id: 'wf', name: 'Role', catalog_version: 'v1', steps: [] });
    await click('orchestration.method_import');
    await act(async () => state.packages.onImportPdf(new File(['pdf'], 'demo.pdf', { type: 'application/pdf' })));
    expect(getAgentCards).not.toHaveBeenCalled();
    expect(handlePlan).toHaveBeenCalledWith({ name: 'PreFlow', steps_md: 'Analyze' }, undefined, { binding: 'role', catalog_version: 'v1' });
});

it('rejects unavailable catalogs before starting PDF parsing', async () => {
    getRoleCatalog.mockRejectedValueOnce({ response: { data: { detail: { code: 'CATALOG_VERSION_UNAVAILABLE', message: 'Unavailable' } } } });
    await click('orchestration.method_import');
    await act(async () => state.packages.onImportPdf(new File(['pdf'], 'demo.pdf', { type: 'application/pdf' })));
    expect(parsePdf).not.toHaveBeenCalled();
    expect(handlePlan).not.toHaveBeenCalled();
    expect(container.querySelector('[role="alert"]').textContent).toContain('CATALOG_VERSION_UNAVAILABLE');
});
