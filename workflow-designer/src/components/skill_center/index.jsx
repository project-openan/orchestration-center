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
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Package, Layers, Server, Wrench } from 'lucide-react';
import { mockSkills } from './mock_data';
import SkillDetail from './skill_detail';

const TABS = ['all', 'service', 'common'];

const SkillCenter = ({ isDark }) => {
    const { t } = useTranslation();
    const [keyword, setKeyword] = useState('');
    const [activeTab, setActiveTab] = useState('all');
    const [selectedSkill, setSelectedSkill] = useState(null);

    const filteredSkills = useMemo(() => {
        let result = mockSkills;
        if (keyword) {
            const term = keyword.toLowerCase();
            result = result.filter(s =>
                s.name.toLowerCase().includes(term) ||
                s.description.toLowerCase().includes(term) ||
                s.tags.some(tag => tag.toLowerCase().includes(term))
            );
        }
        if (activeTab === 'service') {
            result = result.filter(s => s.category === 'ServiceLayer');
        } else if (activeTab === 'common') {
            result = result.filter(s => s.category === 'Common');
        }
        return result;
    }, [keyword, activeTab]);

    const tabCounts = useMemo(() => ({
        all: mockSkills.length,
        service: mockSkills.filter(s => s.category === 'ServiceLayer').length,
        common: mockSkills.filter(s => s.category === 'Common').length,
    }), []);

    const renderCard = (skill) => {
        const activeVersions = skill.versions.filter(v => v.status === 'active').length;
        return (
            <div
                key={skill.id}
                onClick={() => setSelectedSkill(skill)}
                className="cm-card cm-card-hover group relative flex flex-col cursor-pointer p-[17px_16px_14px]
                    dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-blue-700"
            >
                <div className="flex items-start gap-3">
                    <span className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                        <Package size={18} strokeWidth={1.8} />
                    </span>
                    <div className="min-w-0 flex-1">
                        <h3 className="cm-entity-title dark:text-zinc-100" title={skill.name}>
                            {skill.name}
                        </h3>
                        <p className="cm-entity-meta dark:text-zinc-500">
                            {skill.domain} · {skill.vendor.name}
                        </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                        <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                            {activeVersions}/{skill.versions.length} {t('skills.ver')}
                        </span>
                    </div>
                </div>

                <p className="mt-3 min-h-[38px] line-clamp-2 text-[12px] leading-[1.6] text-cm-secondary dark:text-zinc-400">
                    {skill.description}
                </p>

                <div className="mt-3 flex flex-wrap gap-1.5">
                    {skill.tags.slice(0, 3).map(tag => (
                        <span key={tag} className="cm-chip dark:bg-zinc-800 dark:text-blue-300">{tag}</span>
                    ))}
                    {skill.tags.length > 3 && (
                        <span className="cm-chip cm-chip-neutral dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-400">+{skill.tags.length - 3}</span>
                    )}
                </div>

                <div className="mt-auto pt-3 flex items-center justify-between gap-2 border-t border-cm-line-soft dark:border-zinc-800">
                    <span className="truncate text-[11px] font-mono text-cm-faint dark:text-zinc-500">
                        v{skill.versions[0].version}
                    </span>
                    <span className="shrink-0 text-[11px] text-cm-muted dark:text-zinc-400">
                        {skill.vendor.supportLevel}
                    </span>
                </div>
            </div>
        );
    };

    return (
        <div className="h-full p-6 flex flex-col w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans bg-cm-canvas dark:bg-cm-night">
            <div className="shrink-0 flex items-start justify-between gap-4 mb-5">
                <div className="flex min-w-0 items-center gap-3">
                    <span className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                        <Layers size={18} strokeWidth={1.8} />
                    </span>
                    <div className="min-w-0">
                        <h1 className="cm-section-title truncate dark:text-zinc-100">
                            {t('skills.title')}
                        </h1>
                        <p className="mt-[3px] truncate text-[12px] text-cm-muted dark:text-zinc-400">
                            {mockSkills.length} {t('skills.total_skills')}
                        </p>
                    </div>
                </div>
                <div className="cm-search shrink-0 w-[300px] max-w-[55%] dark:border-zinc-700 dark:bg-zinc-900">
                    <Search size={15} className="shrink-0 text-cm-faint dark:text-zinc-500" />
                    <input
                        type="text"
                        placeholder={t('skills.search_placeholder')}
                        className="dark:text-zinc-100 dark:placeholder:text-zinc-500"
                        onChange={(e) => setKeyword(e.target.value)}
                        value={keyword}
                    />
                </div>
            </div>

            <div className="shrink-0 flex items-center gap-1.5 mb-5">
                {TABS.map(tab => {
                    const isActive = activeTab === tab;
                    return (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`inline-flex items-center gap-1.5 h-8 px-3 rounded-cm-sm text-[12px] transition-colors duration-150
                                ${isActive
                                    ? 'bg-cm-primary-faint font-semibold text-cm-primary dark:bg-zinc-800 dark:text-blue-300'
                                    : 'font-medium text-cm-secondary hover:bg-cm-primary-soft hover:text-cm-primary dark:text-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-200'}`}
                        >
                            {tab === 'all' && <Layers size={14} />}
                            {tab === 'service' && <Server size={14} />}
                            {tab === 'common' && <Wrench size={14} />}
                            {t(`skills.tab_${tab}`)}
                            <span className={`rounded-[5px] px-1.5 py-[1px] text-[10px] font-semibold leading-[14px]
                                ${isActive
                                    ? 'bg-white text-cm-primary dark:bg-white/10 dark:text-blue-300'
                                    : 'bg-cm-canvas text-cm-muted dark:bg-zinc-800 dark:text-zinc-400'}`}>
                                {tabCounts[tab]}
                            </span>
                        </button>
                    );
                })}
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar pb-4">
                {filteredSkills.length === 0 ? (
                    <div className="flex h-full flex-col items-center justify-center gap-2.5 text-cm-faint dark:text-zinc-500">
                        <Package size={40} strokeWidth={1.4} />
                        <p className="text-[12px] font-medium">{t('skills.no_skills')}</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 gap-[17px] md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                        {filteredSkills.map(renderCard)}
                    </div>
                )}
            </div>

            {selectedSkill && (
                <SkillDetail
                    skill={selectedSkill}
                    isDark={isDark}
                    onClose={() => setSelectedSkill(null)}
                />
            )}
        </div>
    );
};

export default SkillCenter;
