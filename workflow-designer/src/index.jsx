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

export default function OrchestrationCenterPlugin() {
    const { theme, api } = usePortalContext();
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
