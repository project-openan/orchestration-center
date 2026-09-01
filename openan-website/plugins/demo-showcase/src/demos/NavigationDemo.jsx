// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Navigation, LayoutDashboard, Share2, PlayCircle } from 'lucide-react';

export default function NavigationDemo() {
    const { t } = useTranslation('demo-showcase');
    const { navigate, theme } = usePortalContext();
    const isDark = theme.isDark;

    const targets = [
        { label: t('nav_demo.go_registry'), path: '/registry', icon: LayoutDashboard, color: 'text-blue-500', bg: isDark ? 'hover:bg-blue-950/30' : 'hover:bg-blue-50' },
        { label: t('nav_demo.go_orchestration'), path: '/orchestration', icon: Share2, color: 'text-purple-500', bg: isDark ? 'hover:bg-purple-950/30' : 'hover:bg-purple-50' },
        { label: t('nav_demo.go_execution'), path: '/execution', icon: PlayCircle, color: 'text-emerald-500', bg: isDark ? 'hover:bg-emerald-950/30' : 'hover:bg-emerald-50' },
    ];

    return (
        <div className="space-y-4">
            <div className={`rounded-2xl border p-6 ${isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'}`}>
                <div className="flex items-center gap-2 mb-2">
                    <Navigation size={18} className="text-blue-500" />
                    <h2 className={`text-sm font-black ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                        {t('nav_demo.title')}
                    </h2>
                </div>
                <p className={`text-sm mb-6 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                    {t('nav_demo.desc')}
                </p>

                <div className="space-y-3">
                    {targets.map(target => {
                        const Icon = target.icon;
                        return (
                            <button
                                key={target.path}
                                onClick={() => navigate(target.path)}
                                className={`group w-full flex items-center gap-4 p-4 rounded-xl border transition-all ${isDark ? 'bg-zinc-800/50 border-zinc-700' : 'bg-zinc-50 border-zinc-200'} ${target.bg} hover:border-transparent hover:shadow-md`}
                            >
                                <div className={`p-2.5 rounded-xl ${isDark ? 'bg-zinc-800' : 'bg-white shadow-sm'} ${target.color}`}>
                                    <Icon size={20} />
                                </div>
                                <div className="flex-1 text-left">
                                    <span className={`text-sm font-bold ${isDark ? 'text-zinc-200' : 'text-zinc-800'}`}>
                                        {target.label}
                                    </span>
                                    <div className={`text-xs font-mono ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                                        navigate('{target.path}')
                                    </div>
                                </div>
                                <span className={`text-xs font-bold transition-transform group-hover:translate-x-1 ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>
                                    →
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>
        </div>
    );
}
