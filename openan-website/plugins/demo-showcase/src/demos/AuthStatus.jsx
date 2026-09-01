// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { ShieldCheck, ShieldX, User, KeyRound, LogIn, LogOut } from 'lucide-react';

export default function AuthStatus() {
    const { t } = useTranslation('demo-showcase');
    const { auth, theme } = usePortalContext();
    const isDark = theme.isDark;
    const cardClass = isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200';

    const rows = [
        { icon: auth.isAuthenticated ? ShieldCheck : ShieldX, label: t('auth.authenticated'), value: auth.isAuthenticated ? t('auth.authenticated') : t('auth.not_authenticated'), highlight: auth.isAuthenticated },
        { icon: User, label: t('auth.user'), value: auth.user || 'N/A' },
        { icon: KeyRound, label: t('auth.role'), value: auth.role || 'N/A' },
    ];

    return (
        <div className="space-y-4">
            <div className={`rounded-2xl border p-6 ${cardClass}`}>
                <div className="space-y-3">
                    {rows.map((r, i) => {
                        const Icon = r.icon;
                        return (
                            <div key={i} className={`flex items-center justify-between py-3 px-4 rounded-xl ${isDark ? 'bg-zinc-800/50' : 'bg-zinc-50'}`}>
                                <div className="flex items-center gap-3">
                                    <Icon size={16} className={r.highlight ? 'text-emerald-500' : isDark ? 'text-zinc-400' : 'text-zinc-500'} />
                                    <span className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-600'}`}>{r.label}</span>
                                </div>
                                <span className={`text-sm font-mono font-bold ${r.highlight ? 'text-emerald-500' : isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                                    {String(r.value)}
                                </span>
                            </div>
                        );
                    })}
                </div>
            </div>
            <div className="flex gap-3">
                <button
                    onClick={() => auth.login && auth.login('demo-user', 'demo-pass').catch(() => {})}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-500 hover:bg-blue-600 text-white text-sm font-bold transition-all"
                >
                    <LogIn size={16} />
                    {t('auth.login_btn')}
                </button>
                <button
                    onClick={() => auth.logout && auth.logout().catch(() => {})}
                    className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-bold transition-all ${isDark ? 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300' : 'bg-zinc-100 hover:bg-zinc-200 text-zinc-600'}`}
                >
                    <LogOut size={16} />
                    {t('auth.logout_btn')}
                </button>
            </div>
        </div>
    );
}
