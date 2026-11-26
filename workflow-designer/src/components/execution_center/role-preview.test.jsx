// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { beforeEach, expect, it, vi } from 'vitest';

const capture = vi.hoisted(() => ({
    previewArgs: null, executeBody: null, eventSources: [], t: key => key,
    previewResponse: null,
}));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: capture.t, i18n: { language: 'en' } }) }));
vi.mock('@/service/api.js', async importOriginal => {
    const actual = await importOriginal();
    const previewFor = args => {
        const overridden = Object.keys(args.task_overrides || {}).length > 0
            || Object.keys(args.group_overrides || {}).length > 0;
        return {
            psop_id: args.psop_id, psop_name: 'Role flow', template_fingerprint: 'a'.repeat(64),
            catalog_version: 'cat-v1', config_version: 'cfg-v1', policy_version: 'policy-v1',
            execution_scope: 't/city-a/b', caller_id: 'fixture-admin',
            units: [{
                unit_id: 'task:t1', binding_group: null, task_ids: ['t1'],
                required_skills: [{ task_id: 't1', role_id: 'r', role_version: '1', skill_id: 's' }],
                current_selection: {
                    instance_id: 'inst-a', agent_name: 'A', priority: 10,
                    selection_reason: overridden ? 'explicit_override' : 'highest_priority',
                },
                candidates: [{ instance_id: 'inst-a', agent_name: 'A', priority: 10 }],
                exclusions: [{ instance_id: 'inst-b', reasons: ['OUT_OF_SCOPE'] }],
            }],
            issues: [], can_execute: true, resolution_fingerprint: 'b'.repeat(64),
        };
    };
    return {
        ...Object.fromEntries(Object.keys(actual).map(key => [key, vi.fn().mockResolvedValue({ status: 'success', data: [] })])),
        // The stream URL builders are synchronous string helpers; the generic
        // resolved stubs above would hand EventSource a Promise.
        getStartProcessStreamUrl: vi.fn().mockImplementation(
            psopId => `/rest/v1/orchestrate/execute?psop_id=${psopId}`),
        getAgentCards: vi.fn().mockResolvedValue({ data: [{ name: 'Host' }] }),
        matchWorkflowsTopN: vi.fn().mockResolvedValue([
            { workflow_id: 'wf-role', name: 'Role flow', description: 'd', binding: 'role' },
            { workflow_id: 'wf-inst', name: 'Instance flow', description: 'd', binding: 'instance' },
        ]),
        previewRoleExecution: vi.fn().mockImplementation(async args => {
            capture.previewArgs = args;
            return capture.previewResponse || previewFor(args);
        }),
    };
});
vi.mock('@/service/roleStream.js', () => ({
    streamRoleExecution: vi.fn(async (body, handlers) => {
        capture.executeBody = body;
        handlers?.onDone?.();
    }),
}));
vi.mock('../orchestration_center/workflow/index.jsx', () => ({ default: () => null }));
vi.mock('./execution_statistics/index.jsx', () => ({ default: () => null }));

import ExecutionCenter from './index.jsx';

const render = async () => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    const container = document.createElement('div');
    document.body.append(container);
    const root = createRoot(container);
    vi.stubGlobal('EventSource', class {
        static CLOSED = 2;
        constructor(url) { this.readyState = 1; this.url = url; capture.eventSources.push(this); }
        close() { this.readyState = 2; }
    });
    const scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo');
    Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
    await act(async () => root.render(<ExecutionCenter isDark={false} />));
    return { container, root, scroll };
};

const teardown = async (root, container, scroll) => {
    await act(async () => root.unmount());
    container.remove();
    if (scroll) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scroll);
    else delete HTMLElement.prototype.scrollTo;
    vi.unstubAllGlobals();
};

const setInput = async (container, selector, value) => {
    const input = container.querySelector(selector);
    await act(async () => {
        Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
    });
};

const clickButton = async (container, text) => {
    const button = [...container.querySelectorAll('button')].find(b => b.textContent.trim() === text);
    await act(async () => button.click());
    return button;
};

beforeEach(() => {
    localStorage.clear();
    capture.previewArgs = null;
    capture.executeBody = null;
    capture.eventSources = [];
    capture.previewResponse = null;
});

it('previews the role arrangement for the selected role workflow and flags stale inputs', async () => {
    const { container, root, scroll } = await render();
    try {
        await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
        await clickButton(container, 'execution.match');

        // Two candidates -> selection dialog; pick the role variant.
        const roleCandidate = [...container.querySelectorAll('button')]
            .find(button => button.textContent.includes('orchestration.roleMode'));
        await act(async () => roleCandidate.click());

        const panel = container.querySelector('[data-testid="role-preview-panel"]');
        expect(panel).not.toBeNull();

        const scopeIncomplete = '请完整填写租户/地点/业务对象，或全部留空使用服务器默认范围';
        await setInput(container, '[data-scope-field="tenant"]', 't');
        await act(async () => container.querySelector('[data-testid="role-preview-button"]').click());
        expect(container.textContent).toContain('execution.scope_incomplete');
        expect(capture.previewArgs).toBeNull();

        await setInput(container, '[data-scope-field="tenant"]', '');
        await act(async () => container.querySelector('[data-testid="role-preview-button"]').click());
        expect(capture.previewArgs).toEqual({ psop_id: 'wf-role' });
        expect(container.textContent).toContain('inst-a');
        expect(container.textContent).toContain('inst-b');
        expect(container.textContent).toContain('OUT_OF_SCOPE');
        expect(container.textContent).toContain('execution.preview_can_execute');
        expect(container.textContent).not.toContain('127.0.0.1');

        // Edited scope input invalidates the previous arrangement.
        await setInput(container, '[data-scope-field="site"]', 'city-a');
        expect(container.textContent).toContain('execution.preview_stale');

        // Selecting the instance workflow removes the role preview panel.
        const instanceCard = [...container.querySelectorAll('div.cursor-pointer')]
            .find(card => card.textContent.includes('Instance flow'));
        await act(async () => instanceCard.click());
        expect(container.querySelector('[data-testid="role-preview-panel"]')).toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('sends the joined scope once all three parts are filled', async () => {
    const { container, root, scroll } = await render();
    try {
        await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
        await clickButton(container, 'execution.match');
        const roleCandidate = [...container.querySelectorAll('button')]
            .find(button => button.textContent.includes('orchestration.roleMode'));
        await act(async () => roleCandidate.click());

        await setInput(container, '[data-scope-field="tenant"]', 't');
        await setInput(container, '[data-scope-field="site"]', 'city-a');
        await setInput(container, '[data-scope-field="business_object"]', 'b');
        await act(async () => container.querySelector('[data-testid="role-preview-button"]').click());
        expect(capture.previewArgs).toEqual({ psop_id: 'wf-role', scope: 't/city-a/b' });
        expect(container.textContent).toContain('t/city-a/b');
    } finally {
        await teardown(root, container, scroll);
    }
});

const selectRoleWorkflow = async (container) => {
    await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
    await clickButton(container, 'execution.match');
    const roleCandidate = [...container.querySelectorAll('button')]
        .find(button => button.textContent.includes('orchestration.roleMode'));
    await act(async () => roleCandidate.click());
    await act(async () => container.querySelector('[data-testid="role-preview-button"]').click());
};

it('re-previews with an override and confirms execution with the digest', async () => {
    const { container, root, scroll } = await render();
    try {
        await selectRoleWorkflow(container);

        const confirmButton = container.querySelector('[data-testid="role-execute-button"]');
        expect(confirmButton).not.toBeNull();
        expect(confirmButton.disabled).toBe(false);

        // Candidate click overrides the task and re-previews with the override.
        const candidate = container.querySelector('[data-testid="role-preview-candidate"]');
        await act(async () => candidate.click());
        expect(capture.previewArgs).toEqual({
            psop_id: 'wf-role', task_overrides: { t1: 'inst-a' }, group_overrides: {},
        });
        expect(container.textContent).toContain('execution.preview_reason_override');

        // The override can be reset back to automatic selection.
        await act(async () => container.querySelector('[data-testid="role-preview-reset"]').click());
        expect(capture.previewArgs).toEqual({ psop_id: 'wf-role' });

        // Re-apply the override and confirm the arrangement.
        await act(async () => candidate.click());
        await act(async () => container.querySelector('[data-testid="role-execute-button"]').click());
        expect(capture.executeBody).toEqual({
            psop_id: 'wf-role',
            task_overrides: { t1: 'inst-a' },
            group_overrides: {},
            confirm_fingerprint: 'b'.repeat(64),
            user_intent: 'Analyze',
            lang: 'en',
        });
    } finally {
        await teardown(root, container, scroll);
    }
});

it('collapses the arrangement after confirming and re-expands from the summary bar', async () => {
    const { container, root, scroll } = await render();
    try {
        await selectRoleWorkflow(container);
        await act(async () => container.querySelector('[data-testid="role-execute-button"]').click());

        const bar = container.querySelector('[data-testid="role-preview-collapsed-bar"]');
        expect(bar).not.toBeNull();
        expect(container.querySelector('[data-testid="role-preview-unit"]')).toBeNull();
        expect(container.textContent).toContain('execution.running');

        await act(async () => bar.click());
        expect(container.querySelector('[data-testid="role-preview-unit"]')).not.toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('collapses and re-expands the arrangement via the title chevron before executing', async () => {
    const { container, root, scroll } = await render();
    try {
        await selectRoleWorkflow(container);
        await act(async () => container.querySelector('[data-testid="role-preview-collapse"]').click());

        expect(container.querySelector('[data-testid="role-preview-collapsed-bar"]')).not.toBeNull();
        expect(container.querySelector('[data-testid="role-preview-panel"]')).toBeNull();

        await act(async () => container.querySelector('[data-testid="role-preview-collapsed-bar"]').click());
        expect(container.querySelector('[data-testid="role-preview-panel"]')).not.toBeNull();
        expect(container.querySelector('[data-testid="role-preview-unit"]')).not.toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('blocks confirmation while the inputs are stale', async () => {
    const { container, root, scroll } = await render();
    try {
        await selectRoleWorkflow(container);
        const confirmButton = container.querySelector('[data-testid="role-execute-button"]');
        expect(confirmButton.disabled).toBe(false);

        await setInput(container, '[data-scope-field="site"]', 'city-a');
        expect(confirmButton.disabled).toBe(true);
        expect(capture.executeBody).toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

const playButtonOf = (container, name) => {
    const card = [...container.querySelectorAll('div.cursor-pointer')]
        .find(item => item.textContent.includes(name));
    return card && [...card.querySelectorAll('button')].find(b => !b.textContent.trim());
};

it('routes the card play button of a role workflow into the preview chain (REQ74 F2)', async () => {
    const { container, root, scroll } = await render();
    try {
        await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
        await clickButton(container, 'execution.match');
        const roleCandidate = [...container.querySelectorAll('button')]
            .find(button => button.textContent.includes('orchestration.roleMode'));
        await act(async () => roleCandidate.click());
        capture.previewArgs = null;

        const play = playButtonOf(container, 'Role flow');
        expect(play).toBeDefined();
        await act(async () => play.click());

        // No legacy GET stream and no execution: the confirm chain must run.
        expect(capture.eventSources).toHaveLength(0);
        expect(capture.executeBody).toBeNull();
        expect(capture.previewArgs).toEqual({ psop_id: 'wf-role' });
        expect(container.querySelector('[data-testid="role-preview-panel"]')).not.toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('keeps the legacy GET stream for instance workflows', async () => {
    const { container, root, scroll } = await render();
    try {
        await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
        await clickButton(container, 'execution.match');
        const roleCandidate = [...container.querySelectorAll('button')]
            .find(button => button.textContent.includes('orchestration.roleMode'));
        await act(async () => roleCandidate.click());
        const instanceCard = [...container.querySelectorAll('div.cursor-pointer')]
            .find(card => card.textContent.includes('Instance flow'));
        await act(async () => instanceCard.click());

        const play = playButtonOf(container, 'Instance flow');
        expect(play).toBeDefined();
        await act(async () => play.click());
        expect(capture.eventSources).toHaveLength(1);
        expect(String(capture.eventSources[0].url)).toContain('execute');        expect(capture.previewArgs).toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('reaches the preview chain from exact search results for role workflows (REQ74 F2)', async () => {
    const { getWorkflow } = await import('@/service/api.js');
    getWorkflow.mockResolvedValue({ status: 'success', data: [
        { workflow_id: 'wf-role', name: 'Role flow', description: 'd', binding: 'role' },
    ] });
    const { container, root, scroll } = await render();
    try {
        await act(async () => [...container.querySelectorAll('button')]
            .find(b => b.textContent.trim() === 'execution.search_exact').click());
        await setInput(container, 'input[placeholder="execution.search_by_name"]', 'Role');
        await act(async () => { await new Promise(resolve => setTimeout(resolve, 400)); });

        const play = playButtonOf(container, 'Role flow');
        expect(play).toBeDefined();
        await act(async () => play.click());
        expect(capture.eventSources).toHaveLength(0);
        expect(capture.previewArgs).toEqual({ psop_id: 'wf-role' });
        expect(container.querySelector('[data-testid="role-preview-panel"]')).not.toBeNull();
    } finally {
        await teardown(root, container, scroll);
    }
});

it('keeps candidate re-selection available while the arrangement is blocked (REQ74 F4)', async () => {
    capture.previewResponse = {
        psop_id: 'wf-role', psop_name: 'Role flow', template_fingerprint: 'a'.repeat(64),
        catalog_version: 'cat-v1', config_version: 'cfg-v1', policy_version: 'policy-v1',
        execution_scope: 't/city-a/b', caller_id: 'fixture-admin',
        units: [{
            unit_id: 'task:t1', binding_group: null, task_ids: ['t1'],
            required_skills: [{ task_id: 't1', role_id: 'r', role_version: '1', skill_id: 's' }],
            current_selection: null,
            candidates: [
                { instance_id: 'inst-a', agent_name: 'A', priority: 10 },
                { instance_id: 'inst-b', agent_name: 'B', priority: 10 },
            ],
            exclusions: [],
        }],
        issues: [{ code: 'AMBIGUOUS_BINDING', message: 'Equal-priority candidates', task_ids: ['t1'] }],
        can_execute: false, resolution_fingerprint: null,
    };
    const { container, root, scroll } = await render();
    try {
        await setInput(container, 'input[placeholder="execution.intent_placeholder"]', 'Analyze');
        await clickButton(container, 'execution.match');
        const roleCandidate = [...container.querySelectorAll('button')]
            .find(button => button.textContent.includes('orchestration.roleMode'));
        await act(async () => roleCandidate.click());
        await act(async () => container.querySelector('[data-testid="role-preview-button"]').click());
        capture.previewArgs = null;

        const confirmButton = container.querySelector('[data-testid="role-execute-button"]');
        expect(confirmButton).toBeNull();

        // Ambiguity must be resolvable through explicit re-selection.
        const candidates = [...container.querySelectorAll('[data-testid="role-preview-candidate"]')];
        expect(candidates).toHaveLength(2);
        expect(candidates.every(button => !button.disabled)).toBe(true);
        await act(async () => candidates[1].click());
        expect(capture.previewArgs).toEqual({
            psop_id: 'wf-role', task_overrides: { t1: 'inst-b' }, group_overrides: {},
        });
    } finally {
        await teardown(root, container, scroll);
    }
});
