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
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { createWorkflow } from "@/service/api.js";
import { createPortal } from "react-dom";
import { transformReactFlowToPSOP } from "@/components/orchestration_center/workflow/utils/index.jsx";

const Toolbar = ({ nodes, edges, workflowId, workflowName, workflowDescription, onCancel, onClear, onFitView, isDark, onSaveSuccess }) => {
    const [showConfirm, setShowConfirm] = useState(false);
    const { t } = useTranslation();
    const [showExportModal, setShowExportModal] = useState(false);
    const [exportName, setExportName] = useState(workflowName || "");
    const [exportDesc, setExportDesc] = useState(workflowDescription || "");
    const [toast, setToast] = useState({ show: false, msg: "", type: "error" });

    useEffect(() => {
        if (workflowName) {
            setExportName(workflowName);
        }
    }, [workflowName]);

    useEffect(() => {
        if (workflowDescription) {
            setExportDesc(workflowDescription);
        }
    }, [workflowDescription]);

    useEffect(() => {
        if (toast.show) {
            const timer = setTimeout(() => setToast({ ...toast, show: false }), 3000);
            return () => clearTimeout(timer);
        }
    }, [toast.show]);

    const handleClearClick = () => {
        onClear();
        setShowConfirm(false);
    };

    // --- 0. Pre-validation ---
    const validateWorkflow = () => {
        if (nodes.length === 0) return t('workflow.validate.empty');

        const sourceEdgeIds = new Set(edges.map(e => e.source));

        for (const node of nodes) {
            if (node.type === 'agentNode') {
                if (!node.data.agent) {
                    return t('workflow.validate.invalidAgent', { id: node.id });
                }
                if (!node.data.skill) return t('workflow.validate.noSkill', { id: node.id });
            }
            const isEndNode = (node.type === 'endNode' || node.id === 'endNode');
            if (!isEndNode && !sourceEdgeIds.has(node.id)) {
                return t('workflow.validate.noEdge', { id: node.id });
            }
        }
        if (!nodes.some(n => n.type === 'endNode' || n.id === 'endNode')) {
            return t('workflow.validate.noEnd');
        }
        return null;
    };

    const executeExport = () => {
        const errorMsg = validateWorkflow();
        if (errorMsg) {
            setToast({
                show: true,
                msg: errorMsg,
                type: 'error'
            });
            return;
        }
        const psopData = transformReactFlowToPSOP(nodes, edges, { description: exportDesc, id: workflowId, name: exportName || workflowName });
        try {
            createWorkflow(psopData).then(r => {
                setToast({ show: true, msg: t('workflow.export.success'), type: 'success' });
                setShowExportModal(false);
                setExportName("");
                setExportDesc("");
                if (onSaveSuccess) onSaveSuccess();
            }).catch(err => {
                setToast({ show: true, msg: t('workflow.export.failed'), type: 'error' });
            });
        } catch (e) {
            console.error('Upload failed', e);
        }
    };

    const theme = {
        container: isDark
            ? 'bg-zinc-950/90 border-zinc-800 shadow-[0_10px_40px_rgba(0,0,0,0.7)]'
            : 'bg-white/95 border-slate-200 shadow-[0_10px_30px_rgba(0,0,0,0.1)]',
        secondaryBtn: isDark
            ? 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100'
            : 'text-slate-600 hover:bg-slate-100',
        divider: isDark ? 'bg-zinc-800' : 'bg-slate-200',
        dangerBtn: isDark
            ? 'text-rose-500/80 hover:bg-rose-950/20 hover:text-rose-400'
            : 'text-rose-600 hover:bg-rose-50',
        primaryBtn: isDark
            ? 'bg-zinc-100 text-zinc-950 hover:bg-white shadow-none'
            : 'bg-slate-800 text-white hover:bg-slate-900 shadow-slate-200',
        overlay: isDark
            ? 'bg-zinc-950/60 backdrop-blur-md'
            : 'bg-slate-900/40 backdrop-blur-sm',
        modal: isDark
            ? 'bg-zinc-900 border-zinc-700/50 shadow-[0_20px_50px_rgba(0,0,0,0.5)] ring-1 ring-white/10'
            : 'bg-white border-slate-200 shadow-xl',
        input: isDark
            ? 'bg-zinc-950 border-zinc-700 text-zinc-200 placeholder:text-zinc-600 focus:border-blue-500/50 focus:ring-blue-500/20'
            : 'bg-slate-50 border-slate-200 text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:ring-blue-500/10'
    };

    const ExportModal = (
        <div className={`fixed inset-0 z-[9999] flex items-center justify-center p-4 ${theme.overlay}`}>
            <div className="absolute inset-0" onClick={() => setShowExportModal(false)} />

            <div
                className={`relative w-full max-w-md p-7 rounded-[2rem] border transform transition-all animate-in fade-in zoom-in-95 duration-200 ${theme.modal}`}
                style={{ maxHeight: '90vh', overflowY: 'auto' }}
            >
                {isDark && (
                    <div className="absolute top-0 left-1/2 -translate-x-1/2 w-16 h-1 bg-zinc-700/50 rounded-full mt-2" />
                )}

                <div className="flex items-center gap-4 mb-5">
                    <div className={`p-3 rounded-2xl ${isDark ? 'bg-blue-500/20 text-blue-400' : 'bg-blue-50 text-blue-600'}`}>
                        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                    </div>
                    <div>
                        <h3 className={`text-xl font-extrabold tracking-tight ${isDark ? 'text-zinc-50' : 'text-slate-900'}`}>
                            {t('workflow.export.modalTitle')}
                        </h3>
                        <div className={`h-1 w-8 rounded-full bg-blue-500 mt-1 ${isDark ? 'opacity-80' : ''}`} />
                    </div>
                </div>

                <p className={`text-sm leading-relaxed mb-6 ${isDark ? 'text-zinc-400' : 'text-slate-500'}`}>
                    {t('workflow.export.modalDesc')}
                </p>

                <div className="mb-4">
                    <label className={`block text-xs font-black uppercase tracking-widest mb-2 ml-1 ${isDark ? 'text-zinc-400' : 'text-slate-500'}`}>
                        {t('workflow.export.nameLabel')}
                    </label>
                    <input
                        type="text"
                        autoFocus
                        value={exportName}
                        onChange={(e) => setExportName(e.target.value)}
                        placeholder={t('workflow.export.namePlaceholder')}
                        className={`w-full px-4 py-3 rounded-2xl border outline-none transition-all duration-200 font-medium ${theme.input}`}
                    />
                </div>

                <div className="mb-6">
                    <label className={`block text-xs font-black uppercase tracking-widest mb-2 ml-1 ${isDark ? 'text-zinc-400' : 'text-slate-500'}`}>
                        {t('workflow.export.descLabel')}
                    </label>
                    <textarea
                        value={exportDesc}
                        onChange={(e) => setExportDesc(e.target.value)}
                        placeholder={t('workflow.export.descPlaceholder')}
                        className={`w-full px-4 py-4 rounded-2xl border outline-none transition-all duration-200 resize-none h-28 font-medium ${theme.input}`}
                    />
                </div>

                <div className="flex gap-4">
                    <button
                        onClick={() => { setShowExportModal(false); setExportName(""); setExportDesc(""); }}
                        className={`flex-1 px-4 py-3 text-sm font-bold rounded-2xl transition-all active:scale-95 ${isDark
                                ? 'text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200'
                                : 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
                            }`}
                    >
                        {t('common.cancel')}
                    </button>
                    <button
                        onClick={executeExport}
                        disabled={!exportName.trim()}
                        className={`flex-1 px-4 py-3 text-sm font-black rounded-2xl transition-all active:scale-95 shadow-lg ${isDark
                                ? 'bg-zinc-100 text-zinc-950 hover:bg-white shadow-zinc-950/20'
                                : 'bg-slate-900 text-white hover:bg-slate-800 shadow-slate-200'
                            } disabled:opacity-20 disabled:grayscale disabled:scale-100`}
                    >
                        {t('common.confirm')}
                    </button>
                </div>
            </div>
        </div>
    );


    return (
        <div
            className={`flex items-center gap-3 p-2 backdrop-blur-md rounded-2xl border w-max min-w-[420px] justify-center transition-all duration-300 ${theme.container}`}>

            <button
                onClick={onCancel}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm font-semibold rounded-xl transition-colors ${theme.secondaryBtn}`}
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                {t('workflow.toolbar.back')}
            </button>

            <button
                onClick={onFitView}
                title={t('workflow.toolbar.fitView')}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm font-semibold rounded-xl transition-all active:scale-90 ${theme.secondaryBtn}`}
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                </svg>
                {t('workflow.toolbar.fitView')}
            </button>

            <div className={`w-px h-4 mx-1 ${theme.divider}`} />

            <button
                onClick={handleClearClick}
                className={`flex items-center gap-1 px-3 py-1.5 text-sm font-semibold rounded-xl transition-colors ${theme.dangerBtn}`}
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                {t('workflow.toolbar.clear')}
            </button>

            <button
                onClick={() => {
                    if (workflowId && exportName.trim()) {
                        executeExport();
                    } else {
                        setExportName(workflowName || exportName || "");
                        setExportDesc(workflowDescription || exportDesc || "");
                        setShowExportModal(true);
                    }
                }}
                className={`ml-2 px-4 py-1.5 text-sm font-bold rounded-xl shadow-lg transition-all active:scale-95 flex items-center gap-1 ${theme.primaryBtn}`}
            >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                        d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                {t('workflow.toolbar.export')}
            </button>
            {showExportModal && createPortal(ExportModal, document.body)}
            {toast.show && createPortal(
                <div className="fixed top-10 left-1/2 z-[10000] animate-toast-in">
                    <div className={`flex items-center gap-3 px-6 py-4 rounded-2xl shadow-2xl border transition-all ${toast.type === 'success'
                            ? (isDark ? 'bg-zinc-900 border-emerald-500/30 text-emerald-400 ring-1 ring-emerald-500/20' : 'bg-white border-emerald-100 text-emerald-600 ring-1 ring-emerald-200')
                            : (isDark ? 'bg-zinc-900 border-rose-500/30 text-rose-400 ring-1 ring-rose-500/20' : 'bg-white border-red-100 text-red-600 ring-1 ring-red-200')
                        }`}>
                        <div className={`p-1.5 rounded-full ${toast.type === 'success' ? (isDark ? 'bg-emerald-500/20' : 'bg-emerald-50') : (isDark ? 'bg-rose-500/20' : 'bg-red-50')}`}>
                            {toast.type === 'success' ? (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                                </svg>
                            ) : (
                                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                                </svg>
                            )}
                        </div>

                        <span className="font-bold text-sm tracking-wide">{toast.msg}</span>

                        <button onClick={() => setToast({ ...toast, show: false })} className="ml-4 opacity-50 hover:opacity-100 transition-opacity">
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                        </button>
                    </div>
                </div>,
                document.body
            )}
        </div>
    );
};

export default Toolbar;