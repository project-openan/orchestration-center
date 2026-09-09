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

import { createContext, useContext } from 'react';

/**
 * PortalContext — the shared capability surface injected into every plugin
 * by the Portal shell.
 *
 * @typedef {Object} PortalContextValue
 * @property {object} api                — Shared axios instance (gateway mode, httpOnly cookie)
 * @property {object} auth               — { user, role, isAuthenticated, login, logout, check }
 * @property {object} theme              — { isDark, toggle, setDark }
 * @property {object} i18n               — i18n instance (react-i18next), plugins use own namespace
 * @property {function} navigate         — React Router navigate function
 * @property {object} router              — { location, params, navigate }
 * @property {function} registerMenu      — Dynamically register a menu item (for lazy plugins)
 * @property {function} registerRoute     — Dynamically register a route (for lazy plugins)
 */

/** @type {import('react').Context<PortalContextValue|null>} */
export const PortalContext = createContext(null);

const GLOBAL_KEY = '__OPENAN_PORTAL_CONTEXT__';

/**
 * Hook for plugins to access Portal-provided services.
 *
 * In normal mode (same Vite build), React Context works directly.
 *
 * In Module Federation dev mode, the plugin's copy of portal-sdk
 * has a different React Context instance than the Portal's.
 * To bridge this gap, PortalProvider also writes the context value
 * to window.__OPENAN_PORTAL_CONTEXT__. This hook checks the React
 * Context first, then falls back to the global variable.
 *
 * @returns {PortalContextValue}
 */
export function usePortalContext() {
    const ctx = useContext(PortalContext);
    if (ctx) return ctx;

    if (typeof window !== 'undefined' && window[GLOBAL_KEY]) {
        return window[GLOBAL_KEY];
    }

    throw new Error(
        'usePortalContext() must be used within a <PortalProvider>. ' +
        'In standalone mode, wrap your component with <MockPortal> from ' +
        "'@openan/portal-sdk/standalone'."
    );
}

/**
 * PortalProvider — convenience wrapper for PortalContext.Provider.
 * The Portal shell wraps its content with this, injecting all shared services.
 * Also writes the context to a global variable for Module Federation bridging.
 */
export function PortalProvider({ value, children }) {
    if (typeof window !== 'undefined') {
        window[GLOBAL_KEY] = value;
    }
    return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>;
}
