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
        <div className="h-full w-full flex flex-col overflow-hidden animate-in fade-in duration-300">
            <div className="shrink-0 px-10 pt-8 pb-4">
                <button
                    onClick={onBack}
                    className="group flex items-center gap-2 text-xs font-black text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 transition-all uppercase tracking-[0.2em] mb-6"
                >
                    <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
                    {t('orchestration.back_to_options')}
                </button>

                <div
                    onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                    onClick={() => fileInput.current?.click()}
                    className={`
                        relative flex flex-col items-center justify-center gap-4 p-10 rounded-3xl border-2 border-dashed cursor-pointer transition-all duration-300
                        ${dragOver
                            ? 'border-amber-400 bg-amber-50 dark:bg-amber-900/10 scale-[1.01]'
                            : 'border-zinc-200 dark:border-zinc-700 bg-zinc-50/50 dark:bg-zinc-800/30 hover:border-amber-300 dark:hover:border-amber-600 hover:bg-amber-50/50 dark:hover:bg-amber-900/5'
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
                            <Loader2 size={36} className="animate-spin text-amber-500" />
                            <div className="text-center">
                                <p className="text-sm font-black text-zinc-700 dark:text-zinc-300">
                                    {t(loadingStatus)} {Math.floor(progress)}%
                                </p>
                                <div className="mt-3 w-48 h-1.5 bg-zinc-200 dark:bg-zinc-700 rounded-full overflow-hidden">
                                    <div
                                        className="h-full bg-gradient-to-r from-amber-500 to-orange-500 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                            </div>
                        </>
                    ) : (
                        <>
                            <div className="p-4 rounded-2xl bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400">
                                <Upload size={28} />
                            </div>
                            <div className="text-center">
                                <p className="text-sm font-black text-zinc-700 dark:text-zinc-300 mb-1">
                                    {t('orchestration.packages_upload_title')}
                                </p>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500">
                                    {t('orchestration.packages_upload_hint')}
                                </p>
                            </div>
                        </>
                    )}
                </div>
            </div>

            <div className="flex-1 overflow-y-auto px-10 pb-8 custom-scrollbar">
                <div className="flex items-center gap-3 mb-4 mt-2">
                    <h3 className="text-xs font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-[0.2em]">
                        {t('orchestration.packages_list_title')}
                    </h3>
                    <span className="px-2 py-0.5 rounded-full bg-zinc-100 dark:bg-zinc-800 text-[10px] font-black text-zinc-500 dark:text-zinc-400">
                        {packages.length}
                    </span>
                    <button
                        onClick={refresh}
                        className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                        title="refresh"
                    >
                        <RefreshCw size={13} />
                    </button>
                </div>

                {listLoading ? (
                    <div className="flex items-center justify-center py-16 text-zinc-400 gap-3">
                        <Loader2 size={20} className="animate-spin" />
                    </div>
                ) : packages.length === 0 ? (
                    <div className="py-16 text-center text-sm text-zinc-400">
                        暂无已导入的解决方案包——拖入上方区域即可导入解析。
                    </div>
                ) : (
                    <div className="space-y-3">
                        {packages.map(pkg => {
                            const links = workflowLinks(pkg, t);
                            return (
                                <div
                                    key={pkg.pdf_filename}
                                    className="group p-5 rounded-2xl border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900/50 hover:border-amber-200 dark:hover:border-amber-700 hover:shadow-lg transition-all duration-300"
                                >
                                    <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-4 min-w-0 flex-1">
                                            <div className="p-2.5 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-500 shrink-0">
                                                <FileText size={20} />
                                            </div>
                                            <div className="min-w-0 flex-1">
                                                <h4 className="text-sm font-black text-zinc-800 dark:text-zinc-200 truncate">
                                                    {pkg.pdf_filename}
                                                </h4>
                                                <div className="flex items-center gap-2 mt-1">
                                                    <Clock size={11} className="text-zinc-400" />
                                                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                                                        {formatDate(pkg.created_at)}
                                                    </span>
                                                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                                                        · {pkg.chapter_count ?? Object.keys(pkg.chapters || {}).length} 章节
                                                    </span>
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex items-center gap-3 shrink-0 ml-4">
                                            {links.length > 0 ? (
                                                links.map(link => (
                                                    <button
                                                        key={link.id}
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            onViewWorkflow(link.id);
                                                        }}
                                                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-black uppercase tracking-wider text-white bg-blue-500 hover:bg-blue-600 shadow-sm shadow-blue-500/20 transition-all"
                                                    >
                                                        <Link2 size={13} />
                                                        Workflow
                                                        {link.label && (
                                                            <span className="px-1.5 py-0.5 rounded-md bg-white/25 text-[10px] font-bold tracking-normal normal-case">
                                                                {link.label}
                                                            </span>
                                                        )}
                                                    </button>
                                                ))
                                            ) : (
                                                <span className="px-3 py-1.5 rounded-lg text-[11px] font-bold text-zinc-400 dark:text-zinc-500 bg-zinc-50 dark:bg-zinc-800">
                                                    Workflow 未生成
                                                </span>
                                            )}
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    handleDelete(pkg);
                                                }}
                                                className="p-2 rounded-lg text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors"
                                                title={t('skills.delete_package')}
                                            >
                                                <Trash2 size={15} />
                                            </button>
                                        </div>
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
