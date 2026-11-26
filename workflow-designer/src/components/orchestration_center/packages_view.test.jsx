// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrchestrationCenter from './index.jsx';

const apiMocks = vi.hoisted(() => ({
    getAgentCards: vi.fn(),
    getWorkflow: vi.fn(),
    getWorkflowById: vi.fn(),
    getWorkflowBpmn: vi.fn(),
    handlePlan: vi.fn(),
    parsePdf: vi.fn(),
    generateWorkflowFromIntent: vi.fn(),
    delWorkflowById: vi.fn(),
    getTemplates: vi.fn(),
    importTemplate: vi.fn(),
    listSolutionPackages: vi.fn(),
    deleteSolutionPackage: vi.fn(),
    getSolutionPackage: vi.fn(),
}));

vi.mock('@/service/api.js', () => apiMocks);

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
}));

vi.mock('../orchestration_center/workflow/index.jsx', () => ({ default: () => <div data-testid="unified-workflow" /> }));
vi.mock('@/components/sandbox/SandboxDialog.jsx', () => ({ default: () => <div data-testid="sandbox-dialog" /> }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const flush = async () => { await act(async () => {}); };

describe('builder mode SPG import navigation', () => {
    let container;
    let root;

    beforeEach(() => {
        vi.clearAllMocks();
        apiMocks.getWorkflow.mockResolvedValue({ status: 'success', data: [] });
        apiMocks.getTemplates.mockResolvedValue({ status: 'success', data: [] });
        apiMocks.getAgentCards.mockResolvedValue([]);
        apiMocks.listSolutionPackages.mockResolvedValue([]);
        container = document.createElement('div');
        document.body.appendChild(container);
        root = createRoot(container);
    });

    afterEach(() => {
        act(() => root.unmount());
        container.remove();
    });

    it('lands on the welcome cards in build mode', async () => {
        const errors = [];
        const spy = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args));
        act(() => root.render(<OrchestrationCenter isDark={false} mode="build" />));
        await flush();
        expect(container.textContent).toContain('orchestration.method_import');
        expect(errors.filter(e => String(e[0]).includes('error')).length).toBe(0);
        spy.mockRestore();
    });

    it('clicking the SPG import card renders the solution packages view (no blank page)', async () => {
        const errors = [];
        const spy = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args));
        act(() => root.render(<OrchestrationCenter isDark={false} mode="build" />));
        await flush();

        const card = [...container.querySelectorAll('button')]
            .find(b => b.textContent.includes('orchestration.method_import'));
        expect(card, 'SPG import card should exist in builder welcome').toBeTruthy();
        act(() => card.click());
        await flush();

        // The table-era layout renders no header for the packages view; the
        // component itself must show the upload dropzone and package list UI.
        expect(container.textContent).toContain('orchestration.packages_upload_title');
        expect(container.textContent).toContain('orchestration.packages_list_title');
        expect(container.innerHTML.length).toBeGreaterThan(500);
        const realErrors = errors.filter(args => {
            const s = String(args[0] ?? '');
            return /error|Error|not defined|is not a function|cannot read/i.test(s);
        });
        expect(realErrors).toEqual([]);
        spy.mockRestore();
    });
});
