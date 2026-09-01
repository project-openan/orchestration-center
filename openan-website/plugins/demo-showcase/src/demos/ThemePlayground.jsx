// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Moon, Sun, Palette } from 'lucide-react';

export default function ThemePlayground() {
    const { t } = useTranslation('demo-showcase');
    const { theme } = usePortalContext();
    const isDark = theme.isDark;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between p-6 rounded-2xl bg-gradient-to-r from-blue-500 to-purple-500 text-white shadow-lg">
                <div>
                    <div className="text-xs uppercase tracking-widest opacity-80">{t('theme.current')}</div>
                    <div className="text-2xl font-black mt-1">{isDark ? t('theme.dark') : t('theme.light')}</div>
                </div>
                <button
                    onClick={theme.toggle}
                    className="p-4 rounded-2xl bg-white/20 hover:bg-white/30 transition-all backdrop-blur-sm"
                >
                    {isDark ? <Sun size={28} /> : <Moon size={28} />}
                </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {[
                    { label: 'bg-zinc-50 dark:bg-[#09090B]', className: 'bg-zinc-50 dark:bg-[#09090B] border border-zinc-200 dark:border-zinc-800' },
                    { label: 'bg-white dark:bg-zinc-900', className: 'bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800' },
                    { label: 'bg-blue-500', className: 'bg-blue-500' },
                    { label: 'bg-emerald-500', className: 'bg-emerald-500' },
                ].map((swatch, i) => (
                    <div key={i} className={`rounded-xl p-4 h-24 flex items-end ${swatch.className}`}>
                        <span className={`text-[10px] font-mono ${i < 2 ? (isDark ? 'text-zinc-400' : 'text-zinc-500') : 'text-white/80'}`}>
                            {swatch.label}
                        </span>
                    </div>
                ))}
            </div>

            <div className={`rounded-2xl border p-6 ${isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'}`}>
                <div className="flex items-center gap-2 mb-4">
                    <Palette size={16} className="text-blue-500" />
                    <h3 className={`text-sm font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        {t('theme.card_title')}
                    </h3>
                </div>
                <p className={`text-sm mb-4 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                    {t('theme.card_body')}
                </p>
                <div className="flex items-center gap-3">
                    <input
                        type="text"
                        defaultValue={t('theme.sample_text')}
                        className={`flex-1 px-4 py-2.5 rounded-xl border text-sm ${isDark ? 'bg-zinc-800 border-zinc-700 text-zinc-100' : 'bg-zinc-50 border-zinc-200 text-zinc-900'}`}
                    />
                    <button
                        onClick={theme.toggle}
                        className={`px-4 py-2.5 rounded-xl text-sm font-bold transition-all ${isDark ? 'bg-zinc-800 hover:bg-zinc-700 text-zinc-200' : 'bg-zinc-100 hover:bg-zinc-200 text-zinc-700'}`}
                    >
                        {t('theme.toggle')}
                    </button>
                </div>
            </div>
        </div>
    );
}
