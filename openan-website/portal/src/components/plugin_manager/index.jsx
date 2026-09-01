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

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../../theme/ThemeContext.jsx';
import { X, Puzzle, CheckCircle2, CircleSlash, Route, ChevronDown, ChevronUp, FileJson } from 'lucide-react';

/**
 * Plugin Manager — modal that lists all loaded plugins with runtime
 * enable/disable toggles. Disabled plugins are hidden from the navigation
 * bar and their routes become inaccessible.
 *
 * The disabled state is persisted to localStorage so it survives refreshes.
 */
export default function PluginManager({ plugins, disabledIds, onToggle, onClose }) {
    const { t } = useTranslation();
    const { isDark } = useTheme();
    const [expandedId, setExpandedId] = useState(null);

    const activeCount = plugins.filter((p) => !disabledIds.has(p.id)).length;
    const disabledCount = plugins.length - activeCount;

    const Toggle = ({ enabled }) => (
        <div
            className={`relative w-11 h-6 rounded-full transition-colors duration-300 ${
                enabled ? 'bg-blue-500' : isDark ? 'bg-zinc-700' : 'bg-zinc-300'
            }`}
        >
            <div
                className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-transform duration-300 ${
                    enabled ? 'translate-x-5' : 'translate-x-0.5'
                }`}
            />
        </div>
    );

    return (
        <div
            className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm"
            onClick={onClose}
        >
            <div
                className="bg-white dark:bg-zinc-900 w-full max-w-2xl max-h-[80vh] rounded-2xl shadow-2xl border border-zinc-200 dark:border-zinc-800 flex flex-col overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between p-5 border-b border-zinc-100 dark:border-zinc-800 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-500">
                            <Puzzle size={22} />
                        </div>
                        <div>
                            <h2 className="text-base font-black text-zinc-900 dark:text-zinc-100">
                                {t('plugin_manager.title')}
                            </h2>
                            <p className="text-xs text-zinc-400 dark:text-zinc-500">
                                {t('plugin_manager.subtitle')}
                            </p>
                        </div>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                    >
                        <X size={20} className="text-zinc-400" />
                    </button>
                </div>

                {/* Stats bar */}
                <div className="flex items-center gap-6 px-5 py-3 bg-zinc-50 dark:bg-zinc-950/50 border-b border-zinc-100 dark:border-zinc-800 shrink-0">
                    <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-zinc-400 uppercase tracking-wider">
                            {t('plugin_manager.total')}
                        </span>
                        <span className="text-lg font-black text-zinc-900 dark:text-zinc-100">
                            {plugins.length}
                        </span>
                    </div>
                    <div className="flex items-center gap-2">
                        <CheckCircle2 size={14} className="text-emerald-500" />
                        <span className="text-sm font-bold text-emerald-500">{activeCount}</span>
                        <span className="text-xs text-zinc-400">{t('plugin_manager.active')}</span>
                    </div>
                    {disabledCount > 0 && (
                        <div className="flex items-center gap-2">
                            <CircleSlash size={14} className="text-zinc-400" />
                            <span className="text-sm font-bold text-zinc-400">{disabledCount}</span>
                            <span className="text-xs text-zinc-400">{t('plugin_manager.disabled')}</span>
                        </div>
                    )}
                </div>

                {/* Plugin list */}
                <div className="flex-1 overflow-y-auto p-4 space-y-3">
                    {plugins.map((plugin) => {
                        const isEnabled = !disabledIds.has(plugin.id);
                        const Icon = plugin.menu?.[0]?.icon;
                        const isExpanded = expandedId === plugin.id;
                        const configJson = JSON.stringify(plugin, (key, val) =>
                            key === 'icon' ? (val?.displayName || '[Component]') : val
                        , 2);
                        return (
                            <div
                                key={plugin.id}
                                className={`rounded-xl border transition-all ${
                                    isEnabled
                                        ? isDark ? 'bg-zinc-800/50 border-zinc-700' : 'bg-zinc-50 border-zinc-200'
                                        : 'opacity-50 ' + (isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-zinc-50 border-zinc-200')
                                }`}
                            >
                                <div className="flex items-center gap-4 p-4">
                                    {/* Icon */}
                                    <div
                                        className={`p-2.5 rounded-xl shrink-0 ${
                                            isEnabled
                                                ? 'bg-blue-500/10 text-blue-500'
                                                : isDark ? 'bg-zinc-800 text-zinc-600' : 'bg-zinc-200 text-zinc-400'
                                        }`}
                                    >
                                        {Icon ? <Icon size={20} /> : <Puzzle size={20} />}
                                    </div>

                                    {/* Info */}
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2">
                                            <h3 className="text-sm font-bold text-zinc-900 dark:text-zinc-100 truncate">
                                                {plugin.name}
                                            </h3>
                                            <span className="text-[10px] font-mono text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-1.5 py-0.5 rounded">
                                                v{plugin.version}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2 mt-1">
                                            <code className="text-[10px] font-mono text-zinc-400 dark:text-zinc-500">
                                                {plugin.id}
                                            </code>
                                            {plugin.routes?.length > 0 && (
                                                <span className="flex items-center gap-1 text-[10px] text-zinc-400">
                                                    <Route size={10} />
                                                    {plugin.routes.map((r) => r.path).join(', ')}
                                                </span>
                                            )}
                                        </div>
                                    </div>

                                    {/* Config viewer button */}
                                    <button
                                        onClick={() => setExpandedId(isExpanded ? null : plugin.id)}
                                        className={`shrink-0 p-2 rounded-lg transition-all ${
                                            isExpanded
                                                ? 'bg-blue-500/15 text-blue-500'
                                                : isDark ? 'text-zinc-500 hover:bg-zinc-700' : 'text-zinc-400 hover:bg-zinc-200'
                                        }`}
                                        title={t('plugin_manager.view_config')}
                                    >
                                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                                    </button>

                                    {/* Toggle */}
                                    <button
                                        onClick={() => onToggle(plugin.id)}
                                        className="shrink-0 cursor-pointer"
                                        aria-label={isEnabled ? t('plugin_manager.disable') : t('plugin_manager.enable')}
                                    >
                                        <Toggle enabled={isEnabled} />
                                    </button>
                                </div>

                                {/* Expanded config viewer */}
                                {isExpanded && (
                                    <div className="px-4 pb-4">
                                        <div className="flex items-center gap-2 mb-2">
                                            <FileJson size={12} className="text-zinc-400" />
                                            <span className="text-[10px] font-black uppercase tracking-wider text-zinc-400">
                                                plugin.manifest.js
                                            </span>
                                        </div>
                                        <pre className={`text-xs font-mono whitespace-pre-wrap rounded-lg p-3 max-h-64 overflow-auto ${
                                            isDark ? 'bg-zinc-950 text-zinc-300 border border-zinc-800' : 'bg-white text-zinc-700 border border-zinc-200'
                                        }`}>
                                            {configJson}
                                        </pre>
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Footer */}
                <div className="flex justify-end p-4 border-t border-zinc-100 dark:border-zinc-800 shrink-0">
                    <button
                        onClick={onClose}
                        className="px-6 py-2.5 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 font-bold text-sm transition-all"
                    >
                        {t('plugin_manager.close')}
                    </button>
                </div>
            </div>
        </div>
    );
}
