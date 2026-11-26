// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
//
//    Licensed under the Apache License, Version 2.0 (the "License"); you may
//    not use this file except in compliance with the License. You may obtain
//    a copy of the License at
//
//         http://www.apache.org/licenses/LICENSE-2.0
//
//    Unless required by applicable law or agreed to in writing, software
//    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
//    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
//    License for the specific language governing permissions and limitations
//    under the License.
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SolutionPackages from './index.jsx';
import { listSolutionPackages } from '../../../service/api.js';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('../../../service/api.js', () => ({
    listSolutionPackages: vi.fn(),
    deleteSolutionPackage: vi.fn(),
}));

let root, container, onViewWorkflow;
const t = key => key;
const package_ = overrides => ({
    pdf_filename: 'demo.pdf',
    created_at: '2026-10-01T00:00:00Z',
    chapter_count: 1,
    ...overrides,
});
const render = async () => act(async () => root.render(
    <SolutionPackages
        onBack={() => {}}
        onImportPdf={() => {}}
        onViewWorkflow={onViewWorkflow}
        t={t}
    />
));
const workflowButtons = () =>
    [...container.querySelectorAll('button')].filter(item => item.textContent.includes('Workflow'));
const click = async button => act(async () => button.click());

describe('solution package workflow links', () => {
    beforeEach(() => {
        globalThis.IS_REACT_ACT_ENVIRONMENT = true;
        container = document.createElement('div');
        document.body.append(container);
        root = createRoot(container);
        onViewWorkflow = vi.fn();
    });
    afterEach(async () => {
        await act(async () => root.unmount());
        container.remove();
        vi.clearAllMocks();
    });

    it('offers separate role and instance entries that keep both workflows reachable', async () => {
        listSolutionPackages.mockResolvedValue([package_({
            workflow_bindings: { role: 'wf-role', instance: 'wf-instance' },
        })]);
        await render();

        const buttons = workflowButtons();
        expect(buttons).toHaveLength(2);
        const roleButton = buttons.find(item => item.textContent.includes('orchestration.roleMode'));
        const instanceButton = buttons.find(item => item.textContent.includes('orchestration.instanceMode'));
        expect(roleButton).toBeTruthy();
        expect(instanceButton).toBeTruthy();

        await click(roleButton);
        expect(onViewWorkflow).toHaveBeenCalledWith('wf-role');
        await click(instanceButton);
        expect(onViewWorkflow).toHaveBeenCalledWith('wf-instance');
    });

    it('falls back to the single legacy link for records predating the split', async () => {
        listSolutionPackages.mockResolvedValue([package_({ workflow_id: 'wf-legacy' })]);
        await render();

        const buttons = workflowButtons();
        expect(buttons).toHaveLength(1);
        expect(buttons[0].textContent).not.toContain('orchestration.roleMode');
        expect(buttons[0].textContent).not.toContain('orchestration.instanceMode');
        await click(buttons[0]);
        expect(onViewWorkflow).toHaveBeenCalledWith('wf-legacy');
    });

    it('reports workflows as not generated when no link exists', async () => {
        listSolutionPackages.mockResolvedValue([package_()]);
        await render();

        expect(workflowButtons()).toHaveLength(0);
        expect(container.textContent).toContain('Workflow 未生成');
    });
});
