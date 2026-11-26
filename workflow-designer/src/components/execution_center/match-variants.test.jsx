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

const capture = vi.hoisted(() => ({ sources: [] }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key, i18n: { language: 'en' } }) }));
vi.mock('@/service/api.js', async importOriginal => {
    const actual = await importOriginal();
    return { ...Object.fromEntries(Object.keys(actual).map(key => [key, vi.fn().mockResolvedValue({ status: 'success', data: [] })])),
        getAgentCards: vi.fn().mockResolvedValue({ data: [{ name: 'Host' }] }),
        getStartProcessStreamUrl: vi.fn(psopId => `/sse/${psopId}`),
        matchWorkflowsTopN: vi.fn(),
    };
});
vi.mock('../orchestration_center/workflow/index.jsx', () => ({ default: () => null }));
vi.mock('./execution_statistics/index.jsx', () => ({ default: () => null }));

import ExecutionCenter from './index.jsx';
import { matchWorkflowsTopN } from '@/service/api.js';

let root, container;
const scroll = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'scrollTo');

const variant = (workflowId, binding, score) => ({
    workflow_id: workflowId,
    name: 'SPG.pdf',
    description: 'shared description',
    tags: ['demo'],
    score,
    binding,
});

const render = async () => act(async () => root.render(<ExecutionCenter isDark={false} />));
const flush = async () => act(async () => {});
const matchButton = () => [...container.querySelectorAll('button')]
    .find(button => button.textContent.includes('execution.match'));
const intentInput = () => container.querySelector('input[placeholder="execution.intent_placeholder"]');
const candidateButtons = binding => [...container.querySelectorAll('button')]
    .filter(button => button.textContent.includes('SPG.pdf') && button.textContent.includes(`orchestration.${binding}Mode`));
// Match cards are the only cursor-pointer divs in the match tab.
const matchCards = () => [...container.querySelectorAll('div')]
    .filter(node => typeof node.className === 'string' && node.className.includes('cursor-pointer'));

describe('execution center role/instance workflow variants', () => {
    beforeEach(() => {
        globalThis.IS_REACT_ACT_ENVIRONMENT = true;
        container = document.createElement('div');
        document.body.append(container);
        root = createRoot(container);
        vi.stubGlobal('EventSource', class {
            static CLOSED = 2;
            constructor(url) { capture.sources.push(url); this.readyState = 1; }
            close() { this.readyState = 2; }
        });
        capture.sources.length = 0;
        Object.defineProperty(HTMLElement.prototype, 'scrollTo', { configurable: true, value: vi.fn() });
    });
    afterEach(async () => {
        await act(async () => root.unmount());
        container.remove();
        vi.clearAllMocks();
        vi.unstubAllGlobals();
        if (scroll) Object.defineProperty(HTMLElement.prototype, 'scrollTo', scroll);
        else delete HTMLElement.prototype.scrollTo;
    });

    it('labels candidates by binding and starts only the chosen variant', async () => {
        matchWorkflowsTopN.mockResolvedValue([variant('wf-role', 'role', 0.9), variant('wf-inst', 'instance', 0.8)]);
        await render();
        await act(async () => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(intentInput(), 'save energy');
            intentInput().dispatchEvent(new Event('input', { bubbles: true }));
        });
        await act(async () => matchButton().click());
        await flush();

        // The selection dialog distinguishes the two generations of the package.
        const roleCandidate = candidateButtons('role');
        const instanceCandidate = candidateButtons('instance');
        expect(roleCandidate).toHaveLength(1);
        expect(instanceCandidate).toHaveLength(1);

        await act(async () => roleCandidate[0].click());
        await flush();

        // Both variants stay reachable as separate cards, each with its badge.
        const cards = matchCards();
        expect(cards).toHaveLength(2);
        expect(container.textContent).toContain('orchestration.roleMode');
        expect(container.textContent).toContain('orchestration.instanceMode');

        // Starting the instance card launches exactly that workflow.
        const instanceCard = cards.find(card => card.textContent.includes('orchestration.instanceMode'));
        const play = instanceCard.querySelector('button');
        await act(async () => play.click());
        await flush();
        expect(capture.sources).toEqual(['/sse/wf-inst']);
    });

    it('collapses results that share one workflow id into a single card', async () => {
        matchWorkflowsTopN.mockResolvedValue([variant('wf-dup', 'role', 0.9), variant('wf-dup', 'instance', 0.8)]);
        await render();
        await act(async () => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(intentInput(), 'save energy');
            intentInput().dispatchEvent(new Event('input', { bubbles: true }));
        });
        await act(async () => matchButton().click());
        await flush();

        // One workflow must never render twice with identical behaviour.
        expect(matchCards()).toHaveLength(1);
        expect(candidateButtons('role')).toHaveLength(0);
        expect(candidateButtons('instance')).toHaveLength(0);
    });
});
