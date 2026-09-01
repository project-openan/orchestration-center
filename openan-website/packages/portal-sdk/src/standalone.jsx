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

import { useState, useCallback } from 'react';
import axios from 'axios';
import { PortalContext } from './plugin-context.jsx';

/**
 * MockPortal — a minimal Portal shell for running a single plugin in
 * standalone mode (dev-only).  Provides just enough of PortalContext for
 * the plugin to render without the full Portal infrastructure.
 *
 * Usage (in a plugin's standalone.jsx):
 *   import { MockPortal } from '@openan/portal-sdk/standalone';
 *   import MyPlugin from './index.jsx';
 *
 *   createRoot(document.getElementById('root')).render(
 *     <MockPortal>
 *       <MyPlugin />
 *     </MockPortal>
 *   );
 */
export function MockPortal({ children }) {
    const [isDark, setIsDark] = useState(true);

    const mockApi = axios.create({
        baseURL: '/api/orchestrate',
        timeout: 120000,
        withCredentials: true,
    });
    mockApi.interceptors.response.use(
        (response) => response.data,
        (error) => Promise.reject(error)
    );

    const value = {
        api: mockApi,
        auth: {
            user: 'admin',
            role: 'admin',
            isAuthenticated: true,
            login: async () => {},
            logout: async () => {},
            check: async () => ({ auth_required: false }),
        },
        theme: {
            isDark,
            toggle: () => setIsDark((v) => !v),
            setDark: (v) => setIsDark(v),
        },
        i18n: {
            t: (key) => key,
            language: 'en',
            changeLanguage: () => {},
        },
        navigate: () => {},
        router: { location: { pathname: '/' }, params: {} },
        registerMenu: () => {},
        registerRoute: () => {},
    };

    if (typeof window !== 'undefined') {
        window.__OPENAN_PORTAL_CONTEXT__ = value;
    }
    return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>;
}
