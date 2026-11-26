// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrchestrationCenterPlugin from './index.jsx';

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
    setApiClient: vi.fn(),
}));

vi.mock('@/service/api.js', () => apiMocks);

vi.mock('react-i18next', () => ({
    useTranslation: () => ({ t: (key) => key, i18n: { language: 'en', changeLanguage: vi.fn() } }),
    I18nextProvider: ({ children }) => <>{children}</>,
}));

// Production passes the SDK from the Portal shell; emulate the same surface.
const portalApi = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() };
vi.mock('@openan/portal-sdk', () => ({
    usePortalContext: () => ({ theme: { isDark: false }, api: portalApi, i18n: { language: 'en', addResourceBundle: vi.fn() } }),
}));

vi.mock('../orchestration_center/workflow/index.jsx', () => ({ default: () => <div data-testid="unified-workflow" /> }));
vi.mock('@/components/sandbox/SandboxDialog.jsx', () => ({ default: () => <div data-testid="sandbox-dialog" /> }));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const flush = async () => { await act(async () => {}); };

describe('plugin entry: builder SPG import navigation (production path)', () => {
    let container;
    let root;
    let consoleSpy;
    let errors;

    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('location', { ...window.location, pathname: '/orchestration-builder' });
        apiMocks.getWorkflow.mockResolvedValue({ status: 'success', data: [] });
        apiMocks.getTemplates.mockResolvedValue({ status: 'success', data: [] });
        apiMocks.getAgentCards.mockResolvedValue([]);
        apiMocks.listSolutionPackages.mockResolvedValue([]);
        errors = [];
        consoleSpy = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args));
        container = document.createElement('div');
        document.body.appendChild(container);
        root = createRoot(container);
    });

    afterEach(() => {
        act(() => root.unmount());
        container.remove();
        consoleSpy.mockRestore();
        vi.unstubAllGlobals();
    });

    it('renders the builder welcome and navigates to the SPG packages view without a blank page', async () => {
        act(() => root.render(<OrchestrationCenterPlugin />));
        await flush();

        expect(container.textContent).toContain('orchestration.method_import');

        const card = [...container.querySelectorAll('button')]
            .find(b => b.textContent.includes('orchestration.method_import'));
        act(() => card.click());
        await flush();

        expect(container.textContent).toContain('orchestration.packages_upload_title');
        expect(container.textContent).toContain('orchestration.packages_list_title');
        expect(container.innerHTML.length).toBeGreaterThan(500);
        const realErrors = errors.filter(args => {
            const s = String(args[0] ?? '');
            return /error|Error|not defined|is not a function|cannot read/i.test(s);
        });
        expect(realErrors).toEqual([]);
    });
});
