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
import { useEffect, useMemo, useState } from 'react';
import { I18nextProvider } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { setApiClient } from '@/service/api.js';
import { ErrorBoundary } from '@/components/common/error_boundary/index.jsx';
import './index.css';
import OrchestrationCenter from '@/components/orchestration_center/index.jsx';
import { PLUGIN_I18N_NAMESPACE, registerPluginI18n } from '@/plugin-i18n.js';

// Two portal menus share this bundle: /orchestration → 工作流管理 (browse
// first), /orchestration-builder → 工作流构建 (the three build methods).
const getRouteMode = () => (typeof window !== 'undefined' && window.location.pathname.startsWith('/orchestration-builder') ? 'build' : 'manage');

export default function OrchestrationCenterPlugin() {
    const { theme, api, i18n } = usePortalContext();
    const i18nReady = useMemo(() => registerPluginI18n(i18n), [i18n]);
    const isDark = theme.isDark;
    const [mode, setMode] = useState(getRouteMode);
    useEffect(() => {
        const timer = setInterval(() => setMode(getRouteMode()), 250);
        return () => clearInterval(timer);
    }, []);

    // Route every service-layer request through the Portal's axios instance
    // (per-plugin gateway + auth cookie). Idempotent.
    useEffect(() => {
        setApiClient(api);
    }, [api]);

    if (!i18nReady) return null;

    return (
        <I18nextProvider i18n={i18n} defaultNS={PLUGIN_I18N_NAMESPACE}>
            <div className="h-full w-full relative z-10 visible animate-in">
                <ErrorBoundary>
                    <OrchestrationCenter isDark={isDark} mode={mode} />
                </ErrorBoundary>
            </div>
        </I18nextProvider>
    );
}
