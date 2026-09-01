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

import { useMemo } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Sun, Moon, LogOut, Puzzle } from 'lucide-react';
import { useAuth } from '../../auth/AuthContext.jsx';
import { useTheme } from '../../theme/ThemeContext.jsx';

/**
 * Dynamic Header — renders navigation buttons from plugin manifests.
 *
 * Unlike the original workflow-designer header that hardcoded 4 tab buttons,
 * this header iterates over the plugin registry's menu items and generates
 * buttons dynamically.  New plugins register their menu items via their
 * plugin.manifest.js, and they appear here automatically — zero changes
 * to the Portal shell needed.
 */
export default function Header({ plugins, disabledIds, onManagePlugins }) {
    const { t, i18n } = useTranslation();
    const { currentUser, authRequired, logout } = useAuth();
    const { isDark, toggle } = useTheme();
    const location = useLocation();
    const navigate = useNavigate();

    const activeCount = plugins.filter((p) => !disabledIds.has(p.id)).length;
    const hasDisabled = disabledIds.size > 0;

    // Flatten all active plugin menu items, sorted by their declared `order`
    const menuItems = useMemo(() => {
        return plugins
            .filter((p) => !disabledIds.has(p.id))
            .flatMap((p) => (p.menu || []).map((m) => ({ ...m, pluginId: p.id })))
            .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));
    }, [plugins, disabledIds]);

    const handleLangChange = (lng) => {
        i18n.changeLanguage(lng);
        localStorage.setItem('lang', lng);
    };

    return (
        <nav className="h-16 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800 px-8 flex justify-between items-center shrink-0 z-20 transition-all">
            {/* Brand */}
            <div className="flex items-center gap-3">
                <div className="flex flex-col">
                    <span className="text-xl font-medium tracking-tight text-zinc-900 dark:text-zinc-100 leading-tight">
                        Open<span className="text-blue-500">AN</span>
                    </span>
                    <span className="text-xs tracking-widest uppercase text-zinc-400 dark:text-zinc-500 leading-tight">
                        {t('nav.subtitle')}
                    </span>
                </div>
            </div>

            {/* Dynamic navigation — generated from plugin manifests */}
            <div className="flex items-center bg-zinc-100 dark:bg-zinc-800 p-1.5 rounded-2xl border border-zinc-200 dark:border-zinc-700 shadow-inner">
                {menuItems.map((item) => {
                    const isActive = location.pathname.startsWith(item.route);
                    const Icon = item.icon;
                    return (
                        <button
                            key={item.id}
                            onClick={() => navigate(item.route)}
                            className={`flex items-center gap-3 px-6 py-2 rounded-xl text-sm font-black transition-all duration-300 ${
                                isActive
                                    ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-md scale-[1.02]'
                                    : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'
                            }`}
                        >
                            {Icon && <Icon size={16} />}
                            {t(item.labelKey)}
                        </button>
                    );
                })}
            </div>

            {/* Right controls */}
            <div className="flex items-center gap-4">
                {authRequired && (
                    <>
                        <span className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
                            {currentUser || 'admin'}
                        </span>
                        <button
                            onClick={logout}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all"
                        >
                            <LogOut size={14} />
                            {t('login.logout')}
                        </button>
                    </>
                )}
                <button
                    onClick={toggle}
                    className="p-2.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all"
                >
                    {isDark ? (
                        <Sun size={20} className="text-amber-400" />
                    ) : (
                        <Moon size={20} className="text-zinc-500" />
                    )}
                </button>
                <button
                    onClick={onManagePlugins}
                    className={`relative p-2.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all ${hasDisabled ? 'text-amber-500' : 'text-zinc-400'}`}
                    title={t('plugin_manager.title')}
                >
                    <Puzzle size={20} />
                    <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-blue-500 text-white text-[9px] font-black flex items-center justify-center">
                        {activeCount}
                    </span>
                </button>
                <div className="flex bg-zinc-100 dark:bg-zinc-800 p-1 rounded-full border border-zinc-200 dark:border-zinc-700 shadow-inner">
                    <button
                        onClick={() => handleLangChange('zh')}
                        className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${
                            i18n.language === 'zh'
                                ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm'
                                : 'text-zinc-400'
                        }`}
                    >
                        中
                    </button>
                    <button
                        onClick={() => handleLangChange('en')}
                        className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${
                            i18n.language === 'en'
                                ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm'
                                : 'text-zinc-400'
                        }`}
                    >
                        EN
                    </button>
                </div>
            </div>
        </nav>
    );
}
