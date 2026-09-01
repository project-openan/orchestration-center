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

import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Sun, Moon, User, Globe, Server, Sparkles } from 'lucide-react';

/**
 * Hello Portal — the mock plugin's main view.
 *
 * Demonstrates that PortalContext (auth, theme, i18n, api) is correctly
 * injected by the Portal shell and accessible from within a plugin.
 */
export default function HelloPortal() {
    const { t } = useTranslation();
    // ── Use the plugin's own i18n namespace ──
    const { t: pt } = useTranslation('hello-portal');
    const ctx = usePortalContext();

    const rows = [
        { icon: User, label: pt('content.user_label'), value: ctx.auth?.user || 'N/A' },
        { icon: ctx.theme?.isDark ? Moon : Sun, label: pt('content.theme_label'), value: ctx.theme?.isDark ? 'Dark' : 'Light' },
        { icon: Globe, label: pt('content.i18n_label'), value: ctx.i18n?.language || 'en' },
        { icon: Server, label: pt('content.api_label'), value: ctx.api?.defaults?.baseURL || 'N/A' },
    ];

    return (
        <div className="h-full overflow-auto p-8 bg-zinc-50 dark:bg-[#09090B]">
            <div className="max-w-2xl mx-auto">
                {/* Header card */}
                <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-8 shadow-sm mb-6">
                    <div className="flex items-center gap-3 mb-4">
                        <div className="w-12 h-12 rounded-xl bg-blue-500/10 flex items-center justify-center">
                            <Sparkles size={24} className="text-blue-500" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-zinc-900 dark:text-zinc-100">
                                {pt('content.title')}
                            </h1>
                            <p className="text-sm text-zinc-500 dark:text-zinc-400">
                                {pt('content.description')}
                            </p>
                        </div>
                    </div>
                </div>

                {/* PortalContext verification grid */}
                <div className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-6 shadow-sm">
                    <h2 className="text-sm font-bold text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-4">
                        PortalContext
                    </h2>
                    <div className="space-y-3">
                        {rows.map((row, i) => {
                            const Icon = row.icon;
                            return (
                                <div
                                    key={i}
                                    className="flex items-center justify-between py-3 px-4 rounded-xl bg-zinc-50 dark:bg-zinc-800/50"
                                >
                                    <div className="flex items-center gap-3">
                                        <Icon size={16} className="text-zinc-400" />
                                        <span className="text-sm text-zinc-600 dark:text-zinc-400">
                                            {row.label}
                                        </span>
                                    </div>
                                    <span className="text-sm font-mono font-bold text-zinc-900 dark:text-zinc-100">
                                        {row.value}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Theme toggle demo — proves PortalContext.theme works */}
                <div className="mt-6 text-center">
                    <button
                        onClick={ctx.theme?.toggle}
                        className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all text-sm font-medium"
                    >
                        {ctx.theme?.isDark ? <Sun size={16} /> : <Moon size={16} />}
                        {ctx.theme?.isDark ? 'Switch to Light' : 'Switch to Dark'}
                    </button>
                </div>
            </div>
        </div>
    );
}
