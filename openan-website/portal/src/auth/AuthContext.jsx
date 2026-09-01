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

import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import api, { authCheck, login as apiLogin, logout as apiLogout } from '../service/api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    const [authState, setAuthState] = useState('checking');
    const [authRequired, setAuthRequired] = useState(false);
    const [currentUser, setCurrentUser] = useState(null);

    const checkAuth = useCallback(async () => {
        try {
            const data = await authCheck();
            if (data.auth_required === false || data.authenticated === true) {
                setAuthRequired(data.auth_required !== false);
                setCurrentUser(data.username || null);
                setAuthState('authenticated');
            } else {
                setAuthRequired(true);
                setAuthState('unauthenticated');
            }
        } catch {
            setAuthState('unauthenticated');
        }
    }, []);

    useEffect(() => {
        checkAuth();
    }, [checkAuth]);

    // Listen for auth-expired events dispatched by the axios interceptor
    useEffect(() => {
        const handleExpired = () => setAuthState('unauthenticated');
        window.addEventListener('auth-expired', handleExpired);
        return () => window.removeEventListener('auth-expired', handleExpired);
    }, []);

    const login = useCallback(async (username, password) => {
        const data = await apiLogin(username, password);
        setAuthRequired(true);
        setCurrentUser(data.username || username);
        setAuthState('authenticated');
        return data;
    }, []);

    const logout = useCallback(async () => {
        try {
            await apiLogout();
        } finally {
            setAuthState('unauthenticated');
            setCurrentUser(null);
        }
    }, []);

    const value = {
        authState,
        authRequired,
        currentUser,
        isAuthenticated: authState === 'authenticated',
        isChecking: authState === 'checking',
        login,
        logout,
        checkAuth,
        api,
    };

    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) {
        throw new Error('useAuth() must be used within an <AuthProvider>');
    }
    return ctx;
}
