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
import { X, Package, Calendar, Tag, User, Shield, ChevronDown, ChevronRight } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';

const SkillDetail = ({ skill, isDark, onClose }) => {
    const { t } = useTranslation();
    const [showVersions, setShowVersions] = useState(true);

    const formatDate = (dateStr) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
    };

    const statusColor = (status) => {
        switch (status) {
            case 'active': return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400';
            case 'deprecated': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400';
            case 'archived': return 'bg-cm-canvas dark:bg-zinc-800 text-cm-muted dark:text-zinc-400';
            default: return 'bg-cm-canvas dark:bg-zinc-800 text-cm-muted';
        }
    };

    const riskColor = (level) => {
        switch (level) {
            case 'low': return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400';
            case 'medium': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400';
            case 'high': return 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400';
            default: return 'bg-cm-canvas dark:bg-zinc-800 text-cm-muted';
        }
    };

    const activeVersions = skill.versions.filter(v => v.status === 'active').length;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-cm-ink-strong/40 dark:bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white dark:bg-zinc-900 w-full max-w-3xl max-h-[85vh] rounded-3xl shadow-modal border border-cm-line dark:border-zinc-800 flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
                <div className="px-5 py-4 border-b border-cm-line dark:border-zinc-800 shrink-0">
                    <div className="flex items-start justify-between gap-3">
                        <div className="flex min-w-0 items-start gap-3">
                            <span className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                                <Package size={18} strokeWidth={1.8} />
                            </span>
                            <div className="min-w-0">
                                <h2 className="text-[15px] font-bold leading-tight text-cm-heading dark:text-zinc-100 truncate">
                                    {skill.name}
                                </h2>
                                <div className="flex flex-wrap items-center gap-2 mt-2">
                                    <span className="cm-chip dark:bg-zinc-800 dark:text-blue-300">{skill.domain}</span>
                                    <span className="text-[11px] text-cm-faint uppercase tracking-[0.06em] dark:text-zinc-500">
                                        {skill.category}
                                    </span>
                                    <span className="w-[3px] h-[3px] rounded-full bg-cm-line-strong dark:bg-zinc-600 shrink-0" />
                                    <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                                        {activeVersions}/{skill.versions.length} {t('skills.versions')}
                                    </span>
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="cm-icon-btn shrink-0 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                        >
                            <X size={18} className="text-cm-faint dark:text-zinc-500" />
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto no-scrollbar px-5 py-4 space-y-5">
                    <div>
                        <h3 className="cm-eyebrow mb-1.5 dark:text-zinc-400">{t('skills.description')}</h3>
                        <p className="text-[13px] leading-[1.7] text-cm-ink dark:text-zinc-300">{skill.description}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-3">
                        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-cm border border-cm-line bg-cm-canvas/60 dark:border-zinc-800 dark:bg-zinc-950/40">
                            <User size={15} className="shrink-0 text-cm-faint dark:text-zinc-500" />
                            <div className="min-w-0">
                                <span className="cm-eyebrow block text-[10px] dark:text-zinc-400">{t('skills.vendor')}</span>
                                <p className="truncate text-[13px] font-semibold text-cm-heading dark:text-zinc-100">{skill.vendor.name}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-cm border border-cm-line bg-cm-canvas/60 dark:border-zinc-800 dark:bg-zinc-950/40">
                            <Shield size={15} className="shrink-0 text-cm-faint dark:text-zinc-500" />
                            <div className="min-w-0">
                                <span className="cm-eyebrow block text-[10px] dark:text-zinc-400">{t('skills.support_level')}</span>
                                <p className="truncate text-[13px] font-semibold text-cm-heading dark:text-zinc-100">{skill.vendor.supportLevel}</p>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 className="cm-eyebrow mb-2 dark:text-zinc-400">{t('skills.tags')}</h3>
                        <div className="flex flex-wrap gap-1.5">
                            {skill.tags.map(tag => (
                                <span key={tag} className="cm-chip dark:bg-zinc-800 dark:text-blue-300">
                                    <Tag size={10} />
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </div>

                    <div>
                        <button
                            onClick={() => setShowVersions(!showVersions)}
                            className="w-full flex items-center justify-between px-3 py-2.5 rounded-cm border border-cm-line bg-cm-canvas/60 hover:border-cm-primary/30 hover:bg-cm-primary-soft transition-colors dark:border-zinc-800 dark:bg-zinc-950/40 dark:hover:bg-zinc-800"
                        >
                            <div className="flex items-center gap-2">
                                <Package size={15} className="text-cm-primary" />
                                <span className="text-[13px] font-semibold text-cm-heading dark:text-zinc-100">
                                    {t('skills.version_history')} ({skill.versions.length})
                                </span>
                            </div>
                            {showVersions
                                ? <ChevronDown size={15} className="text-cm-faint dark:text-zinc-500" />
                                : <ChevronRight size={15} className="text-cm-faint dark:text-zinc-500" />}
                        </button>
                        {showVersions && (
                            <div className="mt-2 space-y-1.5 animate-in slide-in-from-top duration-200">
                                {skill.versions.map((v, idx) => (
                                    <div key={idx} className="flex items-center justify-between gap-3 px-3 py-2.5 rounded-cm-sm border border-cm-line bg-white dark:border-zinc-800 dark:bg-zinc-900">
                                        <div className="flex items-center gap-2.5">
                                            <span className="text-[12px] font-mono font-semibold text-cm-ink dark:text-zinc-100">v{v.version}</span>
                                            <span className={`px-1.5 py-[1px] rounded-[5px] text-[10px] font-semibold ${statusColor(v.status)}`}>
                                                {t(`skills.status_${v.status}`)}
                                            </span>
                                            <span className={`px-1.5 py-[1px] rounded-[5px] text-[10px] font-semibold ${riskColor(v.riskLevel)}`}>
                                                {t(`skills.risk_${v.riskLevel}`)}
                                            </span>
                                        </div>
                                        <div className="flex shrink-0 items-center gap-1 text-[11px] text-cm-faint dark:text-zinc-500">
                                            <Calendar size={12} />
                                            {formatDate(v.createdAt)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="flex items-center justify-between gap-3 pt-4 border-t border-cm-line-soft dark:border-zinc-800">
                        <div className="flex items-center gap-4 text-[11px] text-cm-faint dark:text-zinc-500">
                            <span>{t('skills.created')}: {formatDate(skill.createdAt)}</span>
                            <span>{t('skills.updated')}: {formatDate(skill.updatedAt)}</span>
                        </div>
                        <span className="text-[11px] font-mono text-cm-faint dark:text-zinc-500">{skill.id}</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SkillDetail;
