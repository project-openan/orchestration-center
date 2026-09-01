// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Code2, Database, Shield, Palette, Globe, Navigation } from 'lucide-react';

function Section({ icon: Icon, title, isDark, children }) {
    return (
        <div className={`rounded-xl border p-4 ${isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'}`}>
            <div className="flex items-center gap-2 mb-3">
                <Icon size={16} className="text-blue-500" />
                <h3 className={`text-xs font-black uppercase tracking-wider ${isDark ? 'text-zinc-300' : 'text-zinc-700'}`}>
                    {title}
                </h3>
            </div>
            {children}
        </div>
    );
}

function Row({ label, value, isDark }) {
    return (
        <div className={`flex items-center justify-between py-2 px-3 rounded-lg ${isDark ? 'bg-zinc-800/30' : 'bg-zinc-50'}`}>
            <span className={`text-xs ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>{label}</span>
            <span className={`text-xs font-mono font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                {String(value)}
            </span>
        </div>
    );
}

export default function ContextInspector() {
    const { t } = useTranslation('demo-showcase');
    const { api, auth, theme, i18n, navigate, router } = usePortalContext();
    const isDark = theme.isDark;

    return (
        <div className="space-y-4">
            <div className={`rounded-2xl border p-4 ${isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'}`}>
                <div className="flex items-center gap-2 mb-4">
                    <Code2 size={18} className="text-blue-500" />
                    <h2 className={`text-sm font-black ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        {t('context.title')}
                    </h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <Section icon={Database} title={t('context.api_section')} isDark={isDark}>
                        <div className="space-y-1.5">
                            <Row label={t('context.base_url')} value={api?.defaults?.baseURL || 'N/A'} isDark={isDark} />
                            <Row label={t('context.timeout')} value={api?.defaults?.timeout || 'N/A'} isDark={isDark} />
                            <Row label={t('context.with_credentials')} value={api?.defaults?.withCredentials || false} isDark={isDark} />
                        </div>
                    </Section>

                    <Section icon={Shield} title={t('context.auth_section')} isDark={isDark}>
                        <div className="space-y-1.5">
                            <Row label="user" value={auth?.user || 'N/A'} isDark={isDark} />
                            <Row label="role" value={auth?.role || 'N/A'} isDark={isDark} />
                            <Row label="isAuthenticated" value={auth?.isAuthenticated || false} isDark={isDark} />
                            <Row label="has login()" value={typeof auth?.login === 'function'} isDark={isDark} />
                            <Row label="has logout()" value={typeof auth?.logout === 'function'} isDark={isDark} />
                        </div>
                    </Section>

                    <Section icon={Palette} title={t('context.theme_section')} isDark={isDark}>
                        <div className="space-y-1.5">
                            <Row label="isDark" value={theme?.isDark} isDark={isDark} />
                            <Row label="has toggle()" value={typeof theme?.toggle === 'function'} isDark={isDark} />
                            <Row label="has setDark()" value={typeof theme?.setDark === 'function'} isDark={isDark} />
                        </div>
                    </Section>

                    <Section icon={Globe} title={t('context.i18n_section')} isDark={isDark}>
                        <div className="space-y-1.5">
                            <Row label="language" value={i18n?.language || 'N/A'} isDark={isDark} />
                            <Row label="has changeLanguage()" value={typeof i18n?.changeLanguage === 'function'} isDark={isDark} />
                            <Row label="has t()" value={typeof i18n?.t === 'function'} isDark={isDark} />
                        </div>
                    </Section>

                    <Section icon={Navigation} title={t('context.router_section')} isDark={isDark}>
                        <div className="space-y-1.5">
                            <Row label="pathname" value={router?.location?.pathname || 'N/A'} isDark={isDark} />
                            <Row label="has navigate()" value={typeof navigate === 'function'} isDark={isDark} />
                        </div>
                    </Section>
                </div>
            </div>
        </div>
    );
}
