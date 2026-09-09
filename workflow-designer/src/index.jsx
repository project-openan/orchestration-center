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

/**
 * Portal plugin entry — exports the Orchestration Center as a pure content
 * component. The Portal shell provides navigation / auth / theme / i18n
 * via PortalContext; this component only renders the orchestration UI itself.
 *
 * Loaded by the OpenAN Portal as a UMD bundle (local or remote mode).
 */
import { useEffect } from 'react';
import { usePortalContext } from '@openan/portal-sdk';
import { setApiClient } from '@/service/api.js';
import { ErrorBoundary } from '@/components/common/error_boundary/index.jsx';
import OrchestrationCenter from '@/components/orchestration_center/index.jsx';
import en from '@/locales/en.json';
import zh from '@/locales/zh.json';

// Merge this plugin's locale resources into the Portal's GLOBAL i18next instance.
// IMPORTANT: react-i18next does NOT export the instance (.i18next is undefined) —
// get it from the Portal's context instead (window.__OPENAN_PORTAL_CONTEXT__.i18n
// is the same singleton useTranslation() resolves against). Runs on first render
// when the context is guaranteed present.
let i18nMerged = false;

function registerPluginI18n(ctxI18n) {
    if (i18nMerged) return;
    try {
        const i18n =
            ctxI18n ||
            (typeof window !== 'undefined' && window.__OPENAN_PORTAL_CONTEXT__ && window.__OPENAN_PORTAL_CONTEXT__.i18n) ||
            null;
        if (!i18n || typeof i18n.addResourceBundle !== 'function') return;
        if (i18n.exists('orchestration.title')) {
            i18nMerged = true;
            return;
        }
        i18n.addResourceBundle('en', 'translation', en, true, true);
        i18n.addResourceBundle('zh', 'translation', zh, true, true);
        i18nMerged = true;
    } catch { /* i18n unavailable — labels fall back to keys */ }
}

export default function OrchestrationCenterPlugin() {
    const { theme, api, i18n } = usePortalContext();

    // Merge locale resources on first render (Portal context guaranteed present).
    useEffect(() => {
        registerPluginI18n(i18n);
    }, [i18n]);
    const isDark = theme.isDark;

    // Route every service-layer request through the Portal's axios instance
    // (per-plugin gateway + auth cookie). Idempotent.
    useEffect(() => {
        setApiClient(api);
    }, [api]);

    return (
        <div className="h-full w-full relative z-10 visible animate-in">
            <ErrorBoundary>
                <OrchestrationCenter isDark={isDark} />
            </ErrorBoundary>
        </div>
    );
}
