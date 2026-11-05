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
        change('password', 'old-password');
        act(() => {
            const select = container.querySelector('select');
            select.value = 'bob';
            select.dispatchEvent(new Event('change', {bubbles: true}));
        });
        expect(container.querySelector('[name="username"]').value).toBe('bob');
        expect(container.querySelector('[name="password"]').value).toBe('');
        clickText('login.clear_recent_usernames');
        expect(localStorage.getItem(historyKey)).toBeNull();
        expect(container.querySelector('select')).toBeNull();
        expect(container.querySelector('[type="checkbox"]').checked).toBe(false);
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
