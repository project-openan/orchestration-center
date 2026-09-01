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

import { useState, lazy, Suspense } from 'react';
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import {
    Presentation, ShieldQuestion, Wifi, Radio,
    Palette, Globe, Code2, Navigation as NavIcon,
    ArrowLeft, Sparkles, Zap, Eye
} from 'lucide-react';

const demos = {
    interactive: [
        { id: 'auth', icon: ShieldQuestion, component: () => import('./demos/AuthStatus.jsx') },
        { id: 'api_call', icon: Zap, component: () => import('./demos/ApiCall.jsx') },
        { id: 'sse_stream', icon: Radio, component: () => import('./demos/SseStream.jsx') },
    ],
    presentation: [
        { id: 'theme_playground', icon: Palette, component: () => import('./demos/ThemePlayground.jsx') },
        { id: 'i18n_showcase', icon: Globe, component: () => import('./demos/I18nShowcase.jsx') },
        { id: 'context_inspector', icon: Code2, component: () => import('./demos/ContextInspector.jsx') },
        { id: 'navigation_demo', icon: NavIcon, component: () => import('./demos/NavigationDemo.jsx') },
    ],
};

const DemoCard = ({ demo, onClick, isDark }) => {
    const { t } = useTranslation('demo-showcase');
    const Icon = demo.icon;
    return (
        <button
            onClick={onClick}
            className={`group relative p-6 rounded-2xl border text-left transition-all duration-300 hover:shadow-lg hover:-translate-y-1 animate-in fade-in
                ${isDark ? 'bg-zinc-900 border-zinc-800 hover:border-blue-700'
                         : 'bg-white border-zinc-200 hover:border-blue-400'}`}
        >
            <div className="flex items-center gap-3 mb-3">
                <div className={`p-2.5 rounded-xl ${isDark ? 'bg-blue-500/15 text-blue-400' : 'bg-blue-500/10 text-blue-600'}`}>
                    <Icon size={22} />
                </div>
                <h3 className={`text-sm font-bold ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                    {t(`demo.${demo.id}`)}
                </h3>
            </div>
            <p className={`text-xs leading-relaxed ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                {t(`demo.${demo.id}_desc`)}
            </p>
        </button>
    );
};

const CategoryHeader = ({ icon: Icon, title, desc, isDark }) => (
    <div className="flex items-center gap-3 mb-5">
        <div className={`p-2 rounded-lg ${isDark ? 'bg-zinc-800' : 'bg-zinc-100'}`}>
            <Icon size={18} className={isDark ? 'text-blue-400' : 'text-blue-600'} />
        </div>
        <div>
            <h2 className={`text-base font-black ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>{title}</h2>
            <p className={`text-xs ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>{desc}</p>
        </div>
    </div>
);

export default function DemoShowcase() {
    const { t } = useTranslation('demo-showcase');
    const { theme } = usePortalContext();
    const isDark = theme.isDark;
    const [activeDemo, setActiveDemo] = useState(null);

    if (activeDemo) {
        const allDemos = [...demos.interactive, ...demos.presentation];
        const demo = allDemos.find(d => d.id === activeDemo);
        if (!demo) return null;
        const LazyComponent = lazy(demo.component);
        return (
            <div className="h-full overflow-auto bg-zinc-50 dark:bg-[#09090B]">
                <div className="max-w-4xl mx-auto p-8">
                    <button
                        onClick={() => setActiveDemo(null)}
                        className="flex items-center gap-2 text-xs font-bold text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 mb-6 transition-colors"
                    >
                        <ArrowLeft size={14} />
                        {t('back')}
                    </button>
                    <div className="flex items-center gap-3 mb-6">
                        <div className={`p-3 rounded-xl ${isDark ? 'bg-blue-500/15 text-blue-400' : 'bg-blue-500/10 text-blue-600'}`}>
                            <demo.icon size={24} />
                        </div>
                        <h1 className={`text-xl font-black ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                            {t(`demo.${demo.id}`)}
                        </h1>
                    </div>
                    <Suspense fallback={
                        <div className="flex items-center justify-center h-64 text-zinc-400 text-sm animate-pulse">Loading...</div>
                    }>
                        <LazyComponent />
                    </Suspense>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full overflow-auto bg-zinc-50 dark:bg-[#09090B]">
            <div className="max-w-4xl mx-auto p-8">
                <div className="flex items-center gap-3 mb-2">
                    <div className="p-3 rounded-xl bg-blue-500/10 text-blue-500">
                        <Presentation size={28} />
                    </div>
                    <div>
                        <h1 className={`text-2xl font-black ${isDark ? 'text-zinc-100' : 'text-zinc-900'}`}>
                            {t('title')}
                        </h1>
                        <p className={`text-sm ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                            {t('subtitle')}
                        </p>
                    </div>
                </div>

                <div className="mt-10">
                    <CategoryHeader
                        icon={Zap}
                        title={t('category.interactive')}
                        desc={t('category.interactive_desc')}
                        isDark={isDark}
                    />
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {demos.interactive.map(d => (
                            <DemoCard key={d.id} demo={d} isDark={isDark} onClick={() => setActiveDemo(d.id)} />
                        ))}
                    </div>
                </div>

                <div className="mt-10">
                    <CategoryHeader
                        icon={Eye}
                        title={t('category.presentation')}
                        desc={t('category.presentation_desc')}
                        isDark={isDark}
                    />
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                        {demos.presentation.map(d => (
                            <DemoCard key={d.id} demo={d} isDark={isDark} onClick={() => setActiveDemo(d.id)} />
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
}
