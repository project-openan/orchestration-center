// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Globe, Clock } from 'lucide-react';

export default function I18nShowcase() {
    const { t, i18n } = useTranslation('demo-showcase');
    const { theme } = usePortalContext();
    const isDark = theme.isDark;
    const [now, setNow] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setNow(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const currentLang = i18n.language || 'en';
    const cardClass = isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200';
    const subClass = isDark ? 'bg-zinc-800/50' : 'bg-zinc-50';

    const number = 1234567.89;
    const colors = [
        { name: 'Red', hex: '#ef4444', zh: '红色' },
        { name: 'Blue', hex: '#3b82f6', zh: '蓝色' },
        { name: 'Green', hex: '#10b981', zh: '绿色' },
    ];

    return (
        <div className="space-y-4">
            <div className={`rounded-2xl border p-6 ${cardClass}`}>
                <div className="flex items-center gap-3 mb-4">
                    <Globe size={18} className="text-blue-500" />
                    <span className={`text-sm font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        {t('i18n.current_lang')}: <span className="text-blue-500 font-mono">{currentLang}</span>
                    </span>
                </div>

                <div className="flex gap-3 mb-6">
                    <button
                        onClick={() => i18n.changeLanguage('en')}
                        className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all ${currentLang === 'en' ? 'bg-blue-500 text-white shadow-lg' : isDark ? 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700' : 'bg-zinc-100 text-zinc-500 hover:bg-zinc-200'}`}
                    >
                        {t('i18n.switch_en')}
                    </button>
                    <button
                        onClick={() => i18n.changeLanguage('zh')}
                        className={`px-5 py-2.5 rounded-xl text-sm font-bold transition-all ${currentLang === 'zh' ? 'bg-blue-500 text-white shadow-lg' : isDark ? 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700' : 'bg-zinc-100 text-zinc-500 hover:bg-zinc-200'}`}
                    >
                        {t('i18n.switch_zh')}
                    </button>
                </div>

                <div className="space-y-3">
                    <div className={`flex items-center justify-between py-3 px-4 rounded-xl ${subClass}`}>
                        <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{t('i18n.greeting')}</span>
                    </div>

                    <div className={`flex items-center justify-between py-3 px-4 rounded-xl ${subClass}`}>
                        <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{t('i18n.number_label')}</span>
                        <span className={`text-sm font-mono font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                            {new Intl.NumberFormat(currentLang).format(number)}
                        </span>
                    </div>

                    <div className={`flex items-center justify-between py-3 px-4 rounded-xl ${subClass}`}>
                        <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{t('i18n.date_label')}</span>
                        <span className={`text-sm font-mono font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                            {new Intl.DateTimeFormat(currentLang, { dateStyle: 'full', timeStyle: 'short' }).format(now)}
                        </span>
                    </div>

                    <div className={`py-3 px-4 rounded-xl ${subClass}`}>
                        <div className={`text-sm mb-2 ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{t('i18n.color_label')}</div>
                        <div className="flex gap-2">
                            {colors.map(c => (
                                <div key={c.name} className="flex items-center gap-1.5">
                                    <div className="w-4 h-4 rounded-full" style={{ backgroundColor: c.hex }} />
                                    <span className={`text-xs ${isDark ? 'text-zinc-300' : 'text-zinc-700'}`}>
                                        {currentLang === 'zh' ? c.zh : c.name}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    <div className={`flex items-center justify-between py-3 px-4 rounded-xl ${subClass}`}>
                        <div className="flex items-center gap-2">
                            <Clock size={14} className="text-zinc-400" />
                            <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{t('i18n.timestamp_label')}</span>
                        </div>
                        <span className={`text-sm font-mono ${isDark ? 'text-emerald-400' : 'text-emerald-600'}`}>
                            {now.toLocaleTimeString(currentLang)}
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
}
