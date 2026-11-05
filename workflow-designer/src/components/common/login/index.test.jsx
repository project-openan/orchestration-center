// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0

import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import Login from './index.jsx';

const {login, register, getBaseUrl, i18n} = vi.hoisted(() => ({
    login: vi.fn(), register: vi.fn(), getBaseUrl: vi.fn(),
    i18n: {language: 'en', changeLanguage: vi.fn()},
}));
vi.mock('@/service/api.js', () => ({login, register, getBaseUrl}));
vi.mock('react-i18next', () => ({useTranslation: () => ({t: key => key, i18n})}));
vi.mock('../setting/index.jsx', () => ({default: () => null}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const historyKey = 'openan.orchestration.recent-usernames:/api/orchestrate';

describe('login username preferences', () => {
    let container;
    let root;
    let onLoginWithUser;

    beforeEach(() => {
        vi.resetAllMocks();
        localStorage.clear();
        getBaseUrl.mockReturnValue('/api/orchestrate');
        login.mockResolvedValue({auth_required: true, username: 'alice', must_change_password: false});
        onLoginWithUser = vi.fn();
        container = document.createElement('div');
        document.body.appendChild(container);
        root = createRoot(container);
    });

    afterEach(() => {
        act(() => root.unmount());
        container.remove();
        vi.restoreAllMocks();
    });

    function render(props = {}) {
        act(() => root.render(<Login onLoginWithUser={onLoginWithUser} {...props}/>));
    }

    function change(name, value) {
        const input = container.querySelector(`[name="${name}"]`);
        act(() => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(input, value);
            input.dispatchEvent(new Event('input', {bubbles: true}));
        });
    }

    function clickText(text) {
        act(() => [...container.querySelectorAll('button')].find(button => button.textContent === text).click());
    }

    function openHistory() {
        act(() => {
            const input = container.querySelector('[name="username"]');
            input.focus();
            input.click();
        });
    }

    function pressKey(key) {
        act(() => container.querySelector('[name="username"]').dispatchEvent(
            new KeyboardEvent('keydown', {key, bubbles: true, cancelable: true})));
    }

    async function submit() {
        await act(async () => {
            container.querySelector('form').dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
        });
    }

    function credentials() {
        change('username', 'alice');
        change('password', 'Secret123!');
    }

    it('starts multi-user login blank with browser autocomplete and remembering disabled', () => {
        render();
        expect(container.querySelector('[name="username"]').value).toBe('');
        expect(container.querySelector('[name="username"]').autocomplete).toBe('username');
        expect(container.querySelector('[name="password"]').autocomplete).toBe('current-password');
        expect(container.querySelector('[type="checkbox"]').checked).toBe(false);
        expect(container.querySelector('select')).toBeNull();
    });

    it('keeps the single-account admin default without application username history', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice']));
        render({singleAccount: true});
        expect(container.querySelector('[name="username"]').value).toBe('admin');
        expect(container.querySelector('[type="checkbox"]')).toBeNull();
        expect(container.querySelector('select')).toBeNull();
    });

    it('does not persist usernames unless the user opts in', async () => {
        render();
        credentials();
        await submit();
        expect(onLoginWithUser).toHaveBeenCalledWith('alice', false);
        expect(localStorage.getItem(historyKey)).toBeNull();
    });

    it('remembers only the successful server username and deduplicates the five most recent accounts', async () => {
        localStorage.setItem(historyKey, JSON.stringify(['bob', 'alice', 'carol', 'dave', 'eve']));
        render();
        credentials();
        await submit();
        expect(JSON.parse(localStorage.getItem(historyKey))).toEqual(['alice', 'bob', 'carol', 'dave', 'eve']);
        login.mockResolvedValueOnce({auth_required: true, username: 'frank'});
        await submit();
        expect(JSON.parse(localStorage.getItem(historyKey))).toEqual(['frank', 'alice', 'bob', 'carol', 'dave']);
        expect(localStorage.getItem(historyKey)).not.toContain('Secret123!');
    });

    it('leaves no history for failed login attempts even after opting in', async () => {
        login.mockRejectedValueOnce(new Error('Invalid credentials'));
        render();
        act(() => container.querySelector('[type="checkbox"]').click());
        credentials();
        await submit();
        expect(localStorage.getItem(historyKey)).toBeNull();
        expect(onLoginWithUser).not.toHaveBeenCalled();
        expect(container.textContent).toContain('Invalid credentials');
    });

    it('stores the confirmed username after opting in rather than the submitted spelling', async () => {
        login.mockResolvedValueOnce({auth_required: true, username: 'canonical-alice'});
        render();
        credentials();
        act(() => container.querySelector('[type="checkbox"]').click());
        await submit();
        expect(JSON.parse(localStorage.getItem(historyKey))).toEqual(['canonical-alice']);
    });

    it('supports registration autocomplete and remembers the account only after automatic login succeeds', async () => {
        render({registrationEnabled: true});
        clickText('login.register_button');
        expect(container.querySelector('[name="password"]').autocomplete).toBe('new-password');
        expect(container.querySelector('[name="confirmPassword"]').autocomplete).toBe('new-password');
        credentials();
        change('confirmPassword', 'Secret123!');
        act(() => container.querySelector('[type="checkbox"]').click());
        await submit();
        expect(register).toHaveBeenCalledWith('alice', 'Secret123!');
        expect(login).toHaveBeenCalledWith('alice', 'Secret123!');
        expect(JSON.parse(localStorage.getItem(historyKey))).toEqual(['alice']);
    });

    it('does not remember a registered account when its automatic login fails', async () => {
        login.mockRejectedValueOnce(new Error('Login unavailable'));
        render({registrationEnabled: true});
        clickText('login.register_button');
        credentials();
        change('confirmPassword', 'Secret123!');
        act(() => container.querySelector('[type="checkbox"]').click());
        await submit();
        expect(register).toHaveBeenCalledOnce();
        expect(localStorage.getItem(historyKey)).toBeNull();
        expect(onLoginWithUser).not.toHaveBeenCalled();
    });

    it('offers remembered usernames on the next login and clears the password when choosing one', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice', 'bob']));
        render();
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        change('password', 'old-password');
        openHistory();
        expect(container.querySelector('[role="listbox"]').textContent).toBe('alicebob');
        clickText('bob');
        expect(container.querySelector('[name="username"]').value).toBe('bob');
        expect(container.querySelector('[name="password"]').value).toBe('');
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        openHistory();
        clickText('login.clear_recent_usernames');
        expect(localStorage.getItem(historyKey)).toBeNull();
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        expect(container.querySelector('[type="checkbox"]').checked).toBe(false);
    });

    it('shows suggestions on hover and hides them when the pointer leaves without input focus', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice']));
        render();
        const input = container.querySelector('[name="username"]');
        act(() => input.dispatchEvent(new MouseEvent('mouseover', {bubbles: true, relatedTarget: document.body})));
        expect(container.querySelector('[role="option"]').textContent).toBe('alice');
        act(() => input.dispatchEvent(new MouseEvent('mouseout', {bubbles: true, relatedTarget: document.body})));
        expect(container.querySelector('[role="listbox"]')).toBeNull();
    });

    it('filters suggestions while typing and supports keyboard selection without submitting login', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice', 'alex', 'bob']));
        render();
        openHistory();
        change('username', 'AL');
        expect([...container.querySelectorAll('[role="option"]')].map(option => option.textContent)).toEqual(['alice', 'alex']);
        pressKey('ArrowDown');
        pressKey('ArrowDown');
        const input = container.querySelector('[name="username"]');
        expect(document.getElementById(input.getAttribute('aria-activedescendant')).textContent).toBe('alex');
        pressKey('Enter');
        expect(input.value).toBe('alex');
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        expect(login).not.toHaveBeenCalled();
    });

    it('closes suggestions with Escape or when focus moves to the password', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice', 'bob']));
        render();
        openHistory();
        pressKey('ArrowUp');
        expect(container.querySelector('[aria-selected="true"]').textContent).toBe('bob');
        pressKey('Escape');
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        expect(container.querySelector('[name="username"]').getAttribute('aria-activedescendant')).toBeNull();
        openHistory();
        act(() => container.querySelector('[name="password"]').focus());
        expect(container.querySelector('[role="listbox"]')).toBeNull();
    });

    it('does not suggest an existing username during registration', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice']));
        render({registrationEnabled: true});
        clickText('login.register_button');
        openHistory();
        pressKey('ArrowDown');
        expect(container.querySelector('[role="listbox"]')).toBeNull();
        expect(container.querySelector('[role="combobox"]')).toBeNull();
    });

    it('removes saved history when remembering is unchecked', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice']));
        render();
        act(() => container.querySelector('[type="checkbox"]').click());
        expect(localStorage.getItem(historyKey)).toBeNull();
        expect(container.querySelector('select')).toBeNull();
    });

    it.each(['{broken', '{}', '[null,42,""]'])('ignores invalid local history: %s', value => {
        localStorage.setItem(historyKey, value);
        render();
        expect(container.querySelector('select')).toBeNull();
        expect(container.querySelector('[type="checkbox"]').checked).toBe(false);
    });

    it('isolates account history by backend service', () => {
        localStorage.setItem(historyKey, JSON.stringify(['alice']));
        getBaseUrl.mockReturnValue('https://other.example');
        render();
        expect(container.querySelector('select')).toBeNull();
        expect(container.querySelector('[type="checkbox"]').checked).toBe(false);
    });

    it('still logs in when browser storage is blocked', async () => {
        for (const method of ['getItem', 'setItem', 'removeItem']) {
            vi.spyOn(Storage.prototype, method).mockImplementation(() => {throw new Error('Storage blocked');});
        }
        render();
        credentials();
        act(() => container.querySelector('[type="checkbox"]').click());
        await submit();
        expect(onLoginWithUser).toHaveBeenCalledWith('alice', false);
    });
});
