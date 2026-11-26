// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

import React, {act} from 'react';
import {createRoot} from 'react-dom/client';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import App from './App.jsx';

const {authCheckMock, logoutMock} = vi.hoisted(() => ({authCheckMock: vi.fn(), logoutMock: vi.fn()}));

vi.mock('@/service/api.js', () => ({
    authCheck: (...args) => authCheckMock(...args),
    logout: (...args) => logoutMock(...args),
}));

vi.mock('react-i18next', () => ({
    useTranslation: () => ({t: (key) => key, i18n: {language: 'en', changeLanguage: vi.fn()}}),
}));

vi.mock('@/components/common/header/index.jsx', () => ({
    default: ({onLogout}) => <button data-testid="header" data-has-logout={onLogout ? 'true' : 'false'} onClick={onLogout}/>,
}));
vi.mock('@/components/common/login/index.jsx', () => ({
    default: ({singleAccount}) => <div data-testid="login-page" data-single-account={String(singleAccount)}/>,
}));
vi.mock('@/components/common/password_change/index.jsx', () => ({default: () => null}));
vi.mock('./components/registry_center/index.jsx', () => ({default: () => null}));
vi.mock('@/components/orchestration_center/index.jsx', () => ({default: () => null}));
vi.mock('@/components/execution_center/index.jsx', () => ({default: () => null}));
vi.mock('@/components/skill_center/index.jsx', () => ({default: () => null}));

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const flush = async () => {
    await act(async () => {});
};

describe('App startup auth routing', () => {
    let container;
    let root;

    beforeEach(() => {
        localStorage.clear();
        authCheckMock.mockReset();
        logoutMock.mockReset();
        container = document.createElement('div');
        document.body.appendChild(container);
        root = createRoot(container);
    });

    afterEach(() => {
        act(() => root.unmount());
        container.remove();
    });

    it('shows the app with account actions when the backend reports auth enabled and an active session', async () => {
        authCheckMock.mockResolvedValue({auth_required: true, authenticated: true, username: 'admin', role: 'admin'});
        act(() => root.render(<App/>));
        await flush();

        expect(container.querySelector('[data-testid="header"]').dataset.hasLogout).toBe('true');
        expect(container.querySelector('[data-testid="login-page"]')).toBeNull();
        expect(container.querySelector('[data-testid="backend-unreachable"]')).toBeNull();
    });

    it('hides account actions when the backend reports authentication disabled', async () => {
        authCheckMock.mockResolvedValue({auth_required: false, authenticated: false});
        act(() => root.render(<App/>));
        await flush();

        expect(container.querySelector('[data-testid="header"]').dataset.hasLogout).toBe('false');
    });

    it('shows the login page only when the backend answered and requires login', async () => {
        authCheckMock.mockResolvedValue({auth_required: true, authenticated: false});
        act(() => root.render(<App/>));
        await flush();

        expect(container.querySelector('[data-testid="login-page"]')).not.toBeNull();
        expect(container.querySelector('[data-testid="backend-unreachable"]')).toBeNull();
    });

    it('shows a backend-unreachable panel instead of a login prompt when the backend does not answer', async () => {
        // Simulates a network-level failure: no HTTP response at all
        // (connection refused/reset, TLS mismatch). Rendering the login form
        // here would invite users to guess credentials for a dead backend.
        authCheckMock.mockRejectedValue(new Error('Connection refused'));
        act(() => root.render(<App/>));
        await flush();

        expect(container.querySelector('[data-testid="backend-unreachable"]')).not.toBeNull();
        expect(container.querySelector('[data-testid="login-page"]')).toBeNull();
        expect(container.querySelector('[data-testid="header"]')).toBeNull();
    });

    it.each([true, false])('uses the backend account mode even when registration is disabled: %s', async singleAccount => {
        authCheckMock.mockResolvedValue({auth_required: true, authenticated: false,
            registration_enabled: false, single_account: singleAccount});
        act(() => root.render(<App/>));
        await flush();
        expect(container.querySelector('[data-testid="login-page"]').dataset.singleAccount).toBe(String(singleAccount));
    });

    it('keeps the multi-user account mode after logout', async () => {
        authCheckMock.mockResolvedValue({auth_required: true, authenticated: true,
            username: 'alice', role: 'user', single_account: false});
        act(() => root.render(<App/>));
        await flush();
        await act(async () => container.querySelector('[data-testid="header"]').click());
        expect(logoutMock).toHaveBeenCalledOnce();
        expect(container.querySelector('[data-testid="login-page"]').dataset.singleAccount).toBe('false');
    });

    it('recovers to the authenticated app after a successful retry', async () => {
        authCheckMock
            .mockRejectedValueOnce(new Error('Connection refused'))
            .mockResolvedValueOnce({auth_required: true, authenticated: true, username: 'admin', role: 'admin'});
        act(() => root.render(<App/>));
        await flush();
        expect(container.querySelector('[data-testid="backend-unreachable"]')).not.toBeNull();

        const retry = container.querySelector('[data-testid="retry-backend-connection"]');
        act(() => retry.click());
        await flush();

        expect(authCheckMock).toHaveBeenCalledTimes(2);
        expect(container.querySelector('[data-testid="backend-unreachable"]')).toBeNull();
        expect(container.querySelector('[data-testid="header"]').dataset.hasLogout).toBe('true');
    });
});
