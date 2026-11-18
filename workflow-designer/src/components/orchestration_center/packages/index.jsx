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
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ArrowLeft, Upload, FileText, Link2, Clock, Loader2, RefreshCw, Trash2 } from 'lucide-react';
import { listSolutionPackages, deleteSolutionPackage } from '../../../service/api';

const stem = (filename) => filename.replace(/\.pdf$/i, '');

// Role-catalog and instance generations of the same package are linked in
// separate slots; records created before the split only carry the latest id.
const workflowLinks = (pkg, t) => {
    const bindings = pkg.workflow_bindings || {};
    const links = [
        { id: bindings.role, label: t('orchestration.roleMode') },
        { id: bindings.instance, label: t('orchestration.instanceMode') },
    ].filter(link => link.id);
    if (links.length === 0 && pkg.workflow_id) {
        links.push({ id: pkg.workflow_id, label: null });
    }
    return links;
};

const SolutionPackages = ({ onBack, onImportPdf, onViewWorkflow, loading, loadingStatus, progress, t }) => {
    const fileInput = useRef(null);
    const [dragOver, setDragOver] = useState(false);
    const [packages, setPackages] = useState([]);
    const [listLoading, setListLoading] = useState(true);

    const refresh = useCallback(async () => {
        setListLoading(true);
        try {
            const data = await listSolutionPackages();
            setPackages(Array.isArray(data) ? data : []);
        } catch (e) {
            setPackages([]);
        } finally {
            setListLoading(false);
        }
    }, []);

    useEffect(() => { refresh(); }, [refresh]);

    const handleDelete = async (pkg) => {
        if (!window.confirm(`删除方案包 ${pkg.pdf_filename} ？关联的工作流不受影响。`)) return;
        try {
            await deleteSolutionPackage(pkg.pdf_filename);
            await refresh();
        } catch (e) {
            console.error('Delete failed:', e.message || e);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            onImportPdf(file);
        }
    };

    const handleFileSelect = (e) => {
        const file = e.target.files[0];
        if (file && file.type === 'application/pdf') {
            onImportPdf(file);
        }
        e.target.value = '';
    };

    const formatDate = (dateStr) => {
        const d = new Date(dateStr);
        return isNaN(d.getTime()) ? dateStr : d.toLocaleDateString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit'
        });
    };

    return (
        <div className="flex h-full w-full animate-in flex-col overflow-hidden bg-cm-canvas dark:bg-cm-night">
            <div className="shrink-0 px-6 pb-4 pt-1">
                <button
                    onClick={onBack}
                    className="group mb-4 flex items-center gap-1.5 text-[11px] font-medium text-cm-muted transition-colors hover:text-cm-primary dark:text-zinc-400 dark:hover:text-blue-400"
                >
                    <ArrowLeft size={13} className="transition-transform group-hover:-translate-x-0.5" />
                    {t('orchestration.back_to_options')}
                </button>

                <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInput.current?.click()}
                    className={`
                        relative flex cursor-pointer flex-col items-center justify-center gap-3 rounded-cm border border-dashed bg-white px-6 py-7 transition-all duration-200
                        ${dragOver
                            ? 'border-cm-primary bg-cm-primary-soft dark:border-blue-500 dark:bg-blue-950/30'
                            : 'border-cm-line hover:border-[#ADC8FA] hover:bg-cm-primary-soft/60 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:border-blue-700 dark:hover:bg-zinc-800/70'
                        }
                        ${loading ? 'pointer-events-none opacity-60' : ''}
                    `}
                >
                    <input
                        type="file"
                        ref={fileInput}
                        className="hidden"
                        accept=".pdf"
                        onChange={handleFileSelect}
                    />
                    {loading ? (
                        <>
                            <Loader2 size={22} className="animate-spin text-cm-primary dark:text-blue-400" />
                            <div className="text-center">
                                <p className="text-[13px] font-semibold text-cm-ink dark:text-zinc-200">
                                    {t(loadingStatus)} {Math.floor(progress)}%
                                </p>
                                <div className="mt-2.5 h-1 w-48 overflow-hidden rounded-full bg-cm-line-soft dark:bg-zinc-800">
                                    <div
                                        className="h-full rounded-full bg-cm-primary transition-all duration-300 dark:bg-blue-400"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        </>
                    ) : (
                        <>
                            <span className="cm-entity-icon-square dark:bg-zinc-800 dark:text-blue-400">
                                <Upload size={17} />
                            </span>
                            <div className="text-center">
                                <p className="mb-0.5 text-[13px] font-semibold text-cm-ink dark:text-zinc-200">
                                    {t('orchestration.packages_upload_title')}
                                </p>
                                <p className="text-[11px] text-cm-faint dark:text-zinc-500">
                                    {t('orchestration.packages_upload_hint')}
                                </p>
                            </div>
                        </>
                    )}
                </div>
            </div>

            <div className="custom-scrollbar flex-1 overflow-y-auto px-6 pb-6">
                <div className="mb-3 flex items-center gap-2">
                    <h3 className="cm-eyebrow text-cm-muted dark:text-zinc-500">
                        {t('orchestration.packages_list_title')}
                    </h3>
                    <span className="cm-chip-neutral h-[20px] px-1.5 py-0 text-[10px] font-semibold dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                        {packages.length}
                    </span>
                    <button
                        onClick={refresh}
                        className="cm-icon-btn h-6 w-6 dark:hover:bg-zinc-800 dark:hover:text-blue-400"
                        title="refresh"
                    >
                        <RefreshCw size={12} />
                    </button>
                </div>

                {listLoading ? (
                    <div className="flex items-center justify-center gap-3 py-16 text-cm-faint dark:text-zinc-500">
                        <Loader2 size={18} className="animate-spin" />
                    </div>
                ) : packages.length === 0 ? (
                    <div className="rounded-cm border border-dashed border-cm-line px-6 py-14 text-center text-[12px] text-cm-faint dark:border-zinc-700 dark:text-zinc-500">
                        暂无已导入的解决方案包——拖入上方区域即可导入解析。
                    </div>
                ) : (
                    <div className="cm-card divide-y divide-cm-line-soft overflow-hidden dark:divide-zinc-800 dark:border-zinc-800 dark:bg-zinc-900">
                        {packages.map(pkg => {
                            const links = workflowLinks(pkg, t);
                            return (
                                <div
                                    key={pkg.pdf_filename}
                                    className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-cm-canvas-soft dark:hover:bg-zinc-800/60"
                                >
                                    <span className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                                        <FileText size={16} />
                                    </span>

                                    <div className="min-w-0 flex-1">
                                        <h4 className="truncate text-[13px] font-semibold text-cm-ink dark:text-zinc-100">
                                            {pkg.pdf_filename}
                                        </h4>
                                        <div className="mt-1 flex items-center gap-1.5 text-[11px] text-cm-faint dark:text-zinc-500">
                                            <Clock size={11} className="shrink-0" />
                                            <span>{formatDate(pkg.created_at)}</span>
                                            <span className="h-[3px] w-[3px] shrink-0 rounded-full bg-cm-line-strong dark:bg-zinc-600" />
                                            <span>{pkg.chapter_count ?? Object.keys(pkg.chapters || {}).length} 章节</span>
                                        </div>
                                    </div>

                                    <div className="ml-2 flex shrink-0 items-center gap-2">
                                        {links.length > 0 ? (
                                            links.map(link => (
                                                <button
                                                    key={link.id}
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onViewWorkflow(link.id);
                                                    }}
                                                    className="cm-btn-soft h-[27px] min-h-0 px-2.5 text-[11px] font-semibold dark:border-zinc-700 dark:bg-zinc-800 dark:text-blue-300 dark:hover:bg-zinc-700 dark:hover:text-blue-200"
                                                >
                                                    <Link2 size={12} />
                                                    Workflow
                                                    {link.label && (
                                                        <span className="rounded-[4px] bg-cm-primary/10 px-1 py-px text-[10px] font-medium text-cm-primary dark:bg-blue-400/15 dark:text-blue-300">
                                                            {link.label}
                                                        </span>
                                                    )}
                                                </button>
                                            ))
                                        ) : (
                                            <span className="rounded-cm-sm bg-cm-canvas px-2.5 py-1 text-[11px] text-cm-faint dark:bg-zinc-800 dark:text-zinc-500">
                                                Workflow 未生成
                                            </span>
                                        )}
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                handleDelete(pkg);
                                            }}
                                            className="cm-icon-btn h-[27px] w-[27px] hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-950/30 dark:hover:text-rose-400"
                                            title={t('skills.delete_package')}
                                        >
                                            <Trash2 size={13} />
                                        </button>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
};

export default SolutionPackages;
