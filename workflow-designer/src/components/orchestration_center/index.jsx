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
import React, { useState, useMemo, useEffect, useRef } from 'react';
import { dump } from 'js-yaml';
import {
    Search, Loader2, Layout, Hash,
    Plus, Upload, MessageSquare,
    ChevronRight, Sparkles, ChevronLeft, Code2, Trash2, Download, Eye, ArrowLeft, TriangleAlert
} from 'lucide-react';
import { getRoleCatalog, getAgentCards, getWorkflow, getWorkflowById, handlePlan, parsePdf, generateWorkflowFromIntent, delWorkflowById, getTemplates, importTemplate } from "@/service/api.js";
import { transformWorkflowToReactFlow } from "./workflow/utils/index.jsx";
import UnifiedWorkflow from "../orchestration_center/workflow/index.jsx";
import SolutionPackages from "./packages/index.jsx";
import GenerationMode from './generationMode.jsx';
import { generationErrorMessage } from './generationErrors.js';
import { useTranslation } from 'react-i18next';


const MethodCard = ({ icon: Icon, title, onClick, color, loading, progress, status, t }) => (
    <button
        onClick={onClick}
        disabled={loading}
        className={`
            group relative flex w-full flex-col items-start gap-3 overflow-hidden p-[17px] text-left
            cm-card cm-card-hover dark:border-zinc-800 dark:bg-zinc-900
            ${!loading ? 'cursor-pointer' : 'cursor-wait'}
        `}
    >
        {loading && (
            <div
                className="absolute inset-y-0 left-0 origin-left bg-cm-primary/[0.05] transition-all duration-300 ease-out dark:bg-blue-400/[0.06]"
                style={{ width: `${progress}%` }}
            />
        )}

        <span className={`cm-entity-icon-square dark:bg-zinc-800 dark:text-blue-400 ${color} relative z-10`}>
            <Icon size={17} strokeWidth={2} />
        </span>

        <div className="relative z-10 flex w-full flex-col gap-1">
            <span className="cm-entity-title dark:text-zinc-100">
                {title}
            </span>
            {loading && (<span className="cm-entity-meta dark:text-zinc-400">
                {t ? t(status) : status} {Math.floor(progress)}%
            </span>)}
            <div className="mt-2 h-[3px] w-6 rounded-full bg-cm-primary-faint transition-all duration-300 group-hover:w-10 dark:bg-zinc-700" />
        </div>

        {loading && (
            <div className="absolute bottom-0 left-0 h-[3px] w-full bg-cm-line-soft dark:bg-zinc-800">
                <div
                    className="h-full bg-cm-primary transition-all duration-300 dark:bg-blue-400"
                    style={{ width: `${progress}%` }}
                />
            </div>
        )}
    </button>
);
const LOADING_STAGES = {
    IDLE: '',
    PARSING: 'orchestration.stage_parsing',
    PLANNING: 'orchestration.stage_planning',
    GENERATING: 'orchestration.stage_generating',
    FINALIZING: 'orchestration.stage_finalizing',
    DELETING: 'orchestration.stage_deleting',
};
const OrchestrationCenter = ({ isDark }) => {
    const { t, i18n } = useTranslation();
    const [workflows, setWorkflows] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [openedFromPackage, setOpenedFromPackage] = useState(false);
    const [currentWf, setCurrentWf] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [activeView, setActiveView] = useState('welcome'); // 'welcome' | 'detail' | 'ai' | 'editor'
    const [aiPrompt, setAiPrompt] = useState("");
    const [generationBinding, setGenerationBinding] = useState('role');
    const [generationError, setGenerationError] = useState(null);
    const [showConfig, setShowConfig] = useState(false);
    const [browseMode, setBrowseMode] = useState('view');
    const [progress, setProgress] = useState(0);
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [importingTpl, setImportingTpl] = useState(null);
    const fileInput = useRef(null);

    const [loading, setLoading] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [loadingStatus, setLoadingStatus] = useState(LOADING_STAGES.IDLE);

    // Delete confirmation related status
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [wfToDelete, setWfToDelete] = useState(null);
    // Workflow id returned by the first save of a brand-new design, so that
    // subsequent saves update the same workflow instead of creating duplicates
    const [savedWorkflowId, setSavedWorkflowId] = useState(null);
    // Unsaved-changes flag lifted from the editor, used by the global header
    // back button to guard against losing edits
    const [editorDirty, setEditorDirty] = useState(false);
    const [showLeaveEditorConfirm, setShowLeaveEditorConfirm] = useState(false);

    useEffect(() => {
        if (activeView !== 'editor') setEditorDirty(false);
    }, [activeView]);
    useEffect(() => {
        let timer;
        if (loading) {
            setProgress(0);
            timer = setInterval(() => {
                setProgress(prev => {
                    if (prev >= 95) return 95;
                    const increment = prev < 40 ? 0.5 : 0.1;
                    return prev + increment;
                });
            }, 100);
        } else {
            setProgress(100);
            setTimeout(() => setProgress(0), 500);
        }
        return () => clearInterval(timer);
    }, [loading]);

    const handleFileChange = async (event) => {
        const file = event.target.files[0];

        if (!file) return;
        if (file.type !== "application/pdf") {
            event.target.value = ''; // Clear selection
            return;
        }

        const formData = new FormData();
        // Attention: Corresponding to backend request. files ['file ']
        formData.append('file', file);

        setLoading(true);
        setLoadingStatus(LOADING_STAGES.PARSING); // Phase 1
        try {
            setGenerationError(null);
            const catalog = generationBinding === 'role' ? await getRoleCatalog() : null;
            const contentData = await parsePdf(file);
            const agentCards = generationBinding === 'instance' ? await getAgentCards() : null;
            setLoadingStatus(LOADING_STAGES.PLANNING);
            const agentCardsList = agentCards?.data || agentCards || [];
            const finalPlan = await handlePlan(contentData, generationBinding === 'instance' ? agentCardsList : undefined, {
                binding: generationBinding, ...(catalog ? { catalog_version: catalog.catalog_version } : {}),
            });

            setLoadingStatus(LOADING_STAGES.FINALIZING);
            const design = finalPlan?.data || finalPlan;
            setCurrentWf({ id: design.id, name: design.name, rawText: design });
            setSelectedId(design.id);
            setSavedWorkflowId(null);
            const { nodes: n, edges: e } = transformWorkflowToReactFlow(design);
            setNodes(n);
            setEdges(e);
            setActiveView('detail');
        } catch (error) {
            setGenerationError(generationErrorMessage(error));
        } finally {
            setLoading(false);
            setLoadingStatus(LOADING_STAGES.IDLE);
            event.target.value = '';
        }
    };

    const handleImportPdfFromPackage = async (file) => {
        if (!file || file.type !== "application/pdf") return;

        const formData = new FormData();
        formData.append('file', file);

        setLoading(true);
        setLoadingStatus(LOADING_STAGES.PARSING);
        try {
            setGenerationError(null);
            const catalog = generationBinding === 'role' ? await getRoleCatalog() : null;
            const contentData = await parsePdf(file);
            const agentCards = generationBinding === 'instance' ? await getAgentCards() : null;
            setLoadingStatus(LOADING_STAGES.PLANNING);
            const agentCardsList = agentCards?.data || agentCards || [];
            const finalPlan = await handlePlan(contentData, generationBinding === 'instance' ? agentCardsList : undefined, {
                binding: generationBinding, ...(catalog ? { catalog_version: catalog.catalog_version } : {}),
            });

            setLoadingStatus(LOADING_STAGES.FINALIZING);
            const design = finalPlan?.data || finalPlan;
            setCurrentWf({ id: design.id, name: design.name, rawText: design });
            setSelectedId(design.id);
            setSavedWorkflowId(null);
            const { nodes: n, edges: e } = transformWorkflowToReactFlow(design);
            setNodes(n);
            setEdges(e);
            setActiveView('detail');
        } catch (error) {
            setGenerationError(generationErrorMessage(error));
        } finally {
            setLoading(false);
            setLoadingStatus(LOADING_STAGES.IDLE);
        }
    };

    const fetchWorkflows = async () => {
        try {
            setLoading(true);
            const res = await getWorkflow();
            if (res.status === 'success') {
                const data = (res.data || []).map(item => ({
                    id: item.workflow_id,
                    name: item.name || 'Untitled',
                    tags: item.tags || [],
                    description: item.description
                }));
                setWorkflows(data);
            }
        } catch (e) {
            console.error("Failed to obtain PSOP list:", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWorkflows();
        fetchTemplates();
    }, []);

    const fetchTemplates = async () => {
        try {
            const res = await getTemplates();
            if (res.status === 'success') {
                setTemplates(res.data || []);
            }
        } catch (e) {
            console.error("Failed to fetch templates:", e);
        }
    };

    // Refresh only currentWf (name/description) after a save, without touching
    // canvas nodes so the editor layout is preserved
    const refreshWorkflowMeta = async (id) => {
        try {
            const res = await getWorkflowById(id);
            if (res?.status === 'success') {
                setCurrentWf({ id: res.data.id, name: res.data.name, rawText: res.data });
            }
        } catch (e) {
            console.error("Failed to refresh workflow meta:", e);
        }
    };

    const acceptCanvasSave = (savedId, design, graph) => {
        if (design && graph) {
            setCurrentWf({ id: savedId, name: design.name, rawText: { ...design, id: savedId } });
            setNodes(graph.nodes);
            setEdges(graph.edges);
        } else if (savedId) {
            refreshWorkflowMeta(savedId);
        }
    };

    const handleImportTemplate = async (tplId) => {
        try {
            setImportingTpl(tplId);
            const res = await importTemplate(tplId);
            if (res.status === 'success') {
                const psop = res.data;
                const { nodes: n, edges: e } = transformWorkflowToReactFlow(psop);
                setNodes(n);
                setEdges(e);
                setCurrentWf({
                    id: psop.id,
                    name: psop.name,
                    rawText: psop
                });
                setSavedWorkflowId(null);
                setActiveView('editor');
            }
        } catch (e) {
            console.error("Failed to import template:", e);
        } finally {
            setImportingTpl(null);
        }
    };

    useEffect(() => {
        if (!selectedId) {
            setCurrentWf(null);
            return;
        }

        (async () => {
            try {
                setDetailLoading(true);
                const res = await getWorkflowById(selectedId);
                if (res?.status === 'success') {
                    const detailData = res.data;

                    setCurrentWf({
                        id: detailData.id,
                        name: detailData.name,
                        rawText: detailData
                    });

                    // Convert canvas nodes
                    const { nodes: n, edges: e } = transformWorkflowToReactFlow(detailData);
                    setNodes(n);
                    setEdges(e);

                    if (activeView !== 'editor' && activeView !== 'browse') setActiveView('detail');
                }
            } catch (e) {
                console.error("Failed to obtain PSOP details:", e);
            } finally {
                setDetailLoading(false);
            }
        })();
    }, [selectedId]);

    const handleDeleteWorkflow = async () => {
        if (!wfToDelete) return;

        try {
            setLoading(true);
            setLoadingStatus(LOADING_STAGES.DELETING);
            const res = await delWorkflowById(wfToDelete.id);
            if (res.status === 'success') {
                // If the deleted one is currently selected, just clear the
                // selection and stay in browse view
                if (selectedId === wfToDelete.id) {
                    setSelectedId(null);
                }
                await fetchWorkflows();
            }
        } catch (e) {
            console.error("Failed to delete PSOP:", e);
        } finally {
            setLoading(false);
            setShowDeleteConfirm(false);
            setWfToDelete(null);
        }
    };

    const renderContent = () => {
        switch (activeView) {
            case 'welcome':
                return (
                    <div className="custom-scrollbar h-full w-full overflow-y-auto bg-cm-canvas dark:bg-cm-night">
                        <div className="relative w-full px-6 pb-6 pt-1">
                            <div className="pointer-events-none absolute inset-x-0 top-0 h-48 bg-gradient-to-b from-cm-sky/70 to-transparent dark:from-zinc-900/40" />

                            <div className="relative mb-5 animate-in">
                                <h2 className="cm-section-title dark:text-zinc-100">
                                    {t('orchestration.build_workflow')}
                                </h2>
                                <div className="mt-2 h-[3px] w-9 rounded-full bg-cm-primary dark:bg-blue-400" />
                            </div>

                            <div className="relative grid grid-cols-1 gap-[17px] sm:grid-cols-2 xl:grid-cols-4">
                                <MethodCard
                                    icon={Upload} title={t('orchestration.method_import')} color="text-brand-600"
                                    onClick={() => setActiveView('packages')}
                                />
                                <MethodCard
                                    icon={Layout} title={t('orchestration.method_graph')} color="text-brand-500"
                                    onClick={() => {
                                        setSelectedId(null);
                                        setCurrentWf(null);
                                        setSavedWorkflowId(null);
                                        setActiveView('editor');
                                        setNodes([]);
                                        setEdges([]);
                                    }}
                                />
                                <MethodCard
                                    icon={MessageSquare} title={t('orchestration.method_ai')} color="text-cm-accent"
                                    onClick={() => setActiveView('ai')}
                                    loading={loading && loadingStatus === LOADING_STAGES.GENERATING}
                                    progress={progress}
                                    status={loadingStatus}
                                    t={t}
                                />
                                <MethodCard
                                    icon={Eye} title={t('orchestration.manage_workflow')} color="text-brand-700"
                                    onClick={() => {
                                        setSelectedId(null);
                                        setActiveView('browse');
                                    }}
                                />
                            </div>

                            {templates.length > 0 && (
                                <div className="relative mt-7 animate-in">
                                    <div className="mb-3 flex flex-wrap items-baseline gap-x-2 gap-y-1">
                                        <h3 className="cm-eyebrow text-cm-muted dark:text-zinc-500">
                                            {t('orchestration.templates')}
                                        </h3>
                                        <p className="text-[11px] text-cm-faint dark:text-zinc-500">
                                            {t('orchestration.templates_hint')}
                                        </p>
                                    </div>
                                    <div className="grid grid-cols-1 gap-[17px] md:grid-cols-2 lg:grid-cols-3">
                                        {templates.map(tpl => (
                                            <button
                                                key={tpl.id}
                                                onClick={() => handleImportTemplate(tpl.id)}
                                                disabled={importingTpl === tpl.id}
                                                className={`
                                                    cm-card cm-card-hover group relative flex flex-col overflow-hidden p-[17px] pb-[14px] text-left
                                                    dark:border-zinc-800 dark:bg-zinc-900
                                                    ${importingTpl === tpl.id ? 'cursor-wait opacity-60' : 'cursor-pointer'}
                                                `}
                                            >
                                                <div className="flex items-start gap-3">
                                                    <span className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                                                        <Sparkles size={16} />
                                                    </span>
                                                    <div className="min-w-0 flex-1">
                                                        <span className="cm-entity-title block dark:text-zinc-100">
                                                            {tpl.name}
                                                        </span>
                                                        <span className="cm-entity-meta block dark:text-zinc-400">
                                                            {tpl.step_count} {t('orchestration.steps')}
                                                        </span>
                                                    </div>
                                                </div>
                                                <p className="mt-3 min-h-[38px] text-[12px] leading-[1.6] text-cm-secondary line-clamp-2 dark:text-zinc-400">
                                                    {tpl.description}
                                                </p>
                                                {tpl.tags?.length > 0 && (
                                                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                                                        {tpl.tags.slice(0, 3).map(tag => (
                                                            <span key={tag} className="cm-chip text-cm-accent dark:bg-zinc-800 dark:text-blue-300">
                                                                {tag}
                                                            </span>
                                                        ))}
                                                    </div>
                                                )}
                                                <div className="mt-3 flex items-center justify-between gap-2 border-t border-cm-line-soft pt-3 dark:border-zinc-800">
                                                    <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                                                        {tpl.agent_count} {t('orchestration.agents')}
                                                    </span>
                                                    <span className="inline-flex items-center gap-1 rounded-cm-sm bg-cm-primary px-2 py-[3px] text-[11px] font-medium text-white shadow-none transition-colors group-hover:bg-cm-primary-hover">
                                                        <Download size={11} />
                                                        {t('orchestration.import_btn')}
                                                    </span>
                                                </div>
                                                {importingTpl === tpl.id && (
                                                    <div className="absolute inset-0 flex items-center justify-center rounded-cm bg-white/80 dark:bg-zinc-900/80">
                                                        <Loader2 size={18} className="animate-spin text-cm-primary dark:text-blue-400" />
                                                    </div>
                                                )}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                );

            case 'browse':
                return (
                    <div className="flex h-full animate-in bg-cm-canvas dark:bg-cm-night">
                        <div className="flex w-[292px] shrink-0 flex-col border-r border-cm-line bg-white dark:border-zinc-800 dark:bg-zinc-900">
                            <div className="space-y-3 border-b border-cm-line p-4 dark:border-zinc-800">
                                <button
                                    onClick={() => {
                                        setSelectedId(null);
                                        setActiveView('welcome');
                                    }}
                                    className="group flex items-center gap-1.5 text-[11px] font-medium text-cm-muted transition-colors hover:text-cm-primary dark:text-zinc-400 dark:hover:text-blue-400"
                                >
                                    <ArrowLeft size={13} className="transition-transform group-hover:-translate-x-0.5" />
                                    {t('orchestration.back_to_options')}
                                </button>
                                <div className="cm-search dark:border-zinc-700 dark:bg-zinc-800">
                                    <Search size={14} className="shrink-0" />
                                    <input
                                        type="text"
                                        placeholder={t('orchestration.search')}
                                        className="dark:text-zinc-100 dark:placeholder:text-zinc-500"
                                        onChange={e => setSearchTerm(e.target.value)}
                                    />
                                </div>
                            </div>
                            <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto p-3">
                                {(() => {
                                    const filtered = workflows.filter(wf => wf.name.toLowerCase().includes(searchTerm.toLowerCase()));
                                    const grouped = {};
                                    filtered.forEach(wf => {
                                        const src = wf.source || 'unknown';
                                        if (!grouped[src]) grouped[src] = [];
                                        grouped[src].push(wf);
                                    });
                                    const sourceOrder = ['graph_editor', 'ai_intent', 'solution_package', 'template', 'unknown'];
                                    const sourceIcons = {
                                        graph_editor: Layout,
                                        ai_intent: MessageSquare,
                                        solution_package: Upload,
                                        template: Sparkles,
                                        unknown: Hash
                                    };
                                    const sourceColors = {
                                        graph_editor: 'text-cm-primary dark:text-blue-400',
                                        ai_intent: 'text-brand-500 dark:text-blue-400',
                                        solution_package: 'text-cm-accent dark:text-blue-300',
                                        template: 'text-brand-700 dark:text-blue-300',
                                        unknown: 'text-cm-faint dark:text-zinc-500'
                                    };
                                    return sourceOrder.filter(src => grouped[src]?.length > 0).map(src => {
                                        const Icon = sourceIcons[src] || Hash;
                                        const color = sourceColors[src] || 'text-cm-faint dark:text-zinc-500';
                                        return (
                                            <div key={src}>
                                                <div className="mb-1.5 flex items-center gap-1.5 px-2 py-1">
                                                    <Icon size={12} className={`shrink-0 ${color}`} />
                                                    <span className={`text-[11px] font-semibold ${color}`}>
                                                        {t(`orchestration.source_${src}`)}
                                                    </span>
                                                    <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                                                        ({grouped[src].length})
                                                    </span>
                                                </div>
                                                {grouped[src].map(wf => {
                                                    const isSelected = selectedId === wf.id;
                                                    return (
                                                        <div
                                                            key={wf.id}
                                                            onClick={() => {
                                                                setSelectedId(wf.id);
                                                                setBrowseMode('view');
                                                            }}
                                                            className={`group relative mb-1.5 cursor-pointer overflow-hidden rounded-cm-sm border px-3 py-2.5 transition-colors
                                                                ${isSelected
                                                                    ? 'border-cm-topbar-line bg-cm-sky dark:border-blue-800 dark:bg-blue-950/40'
                                                                    : 'border-transparent hover:border-cm-line hover:bg-cm-canvas dark:hover:border-zinc-700 dark:hover:bg-zinc-800'
                                                                }`}
                                                        >
                                                            {isSelected && (
                                                                <div className="absolute inset-y-0 left-0 w-[3px] bg-cm-primary dark:bg-blue-400" />
                                                            )}
                                                            <div className="flex items-center justify-between gap-2">
                                                                <div className={`flex min-w-0 items-center gap-2 ${isSelected ? 'text-cm-accent dark:text-blue-300' : 'text-cm-ink dark:text-zinc-200'}`}>
                                                                    <Hash size={13} className="shrink-0 opacity-70" />
                                                                    <h3 className={`truncate text-[13px] ${isSelected ? 'font-semibold' : 'font-medium'}`}>
                                                                        {wf.name}
                                                                    </h3>
                                                                </div>
                                                                <button
                                                                    onClick={(e) => {
                                                                        e.stopPropagation();
                                                                        setWfToDelete(wf);
                                                                        setShowDeleteConfirm(true);
                                                                    }}
                                                                    className="cm-icon-btn h-6 w-6 shrink-0 opacity-0 transition-all group-hover:opacity-100 hover:bg-rose-50 hover:text-rose-500 dark:hover:bg-rose-950/30 dark:hover:text-rose-400"
                                                                >
                                                                    <Trash2 size={12} />
                                                                </button>
                                                            </div>
                                                            <div className={`mt-1 truncate pl-5 text-[11px] ${isSelected ? 'text-cm-accent/80 dark:text-blue-300/80' : 'text-cm-faint dark:text-zinc-500'}`}>
                                                                {wf.tags?.length > 0 ? wf.tags.join(', ') : t('orchestration.no_tags')}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        );
                                    });
                                })()}
                                {workflows.length === 0 && (
                                    <div className="flex flex-col items-center justify-center py-16 text-cm-faint dark:text-zinc-500">
                                        <Hash size={28} className="mb-2 opacity-30" />
                                        <p className="text-[11px] font-medium">{t('orchestration.no_workflows')}</p>
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="flex flex-1 flex-col overflow-hidden">
                            {selectedId ? (
                                <>
                                    <div className="z-10 flex shrink-0 items-center gap-2 border-b border-cm-line bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900">
                                        <button
                                            onClick={() => setShowConfig(!showConfig)}
                                            className="cm-icon-btn border border-cm-line bg-white dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                                        >
                                            {showConfig ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
                                        </button>
                                        <button
                                            onClick={() => setBrowseMode(browseMode === 'view' ? 'edit' : 'view')}
                                            className="cm-btn-soft h-[30px] min-h-0 px-3 text-[12px] font-semibold text-cm-primary dark:border-zinc-700 dark:bg-zinc-800 dark:text-blue-300 dark:hover:bg-zinc-700 dark:hover:text-blue-200"
                                        >
                                            <Code2 size={13} />
                                            <span>{browseMode === 'view' ? t('orchestration.edit') : t('orchestration.preview_mode')}</span>
                                        </button>
                                    </div>
                                    <div className="flex flex-1 overflow-hidden">
                                        {showConfig && (
                                            <div className="flex w-1/3 shrink-0 flex-col overflow-hidden border-r border-cm-line bg-cm-canvas-soft p-4 dark:border-zinc-800 dark:bg-zinc-900">
                                                <div className="cm-eyebrow mb-2 text-cm-muted dark:text-zinc-500">workflow</div>
                                                <textarea
                                                    readOnly={true}
                                                    value={dump(currentWf?.rawText || {})}
                                                    className="min-h-0 flex-1 rounded-cm border border-cm-line bg-white p-3 font-mono text-[11px] leading-[1.6] text-cm-ink outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200"
                                                />
                                            </div>
                                        )}
                                        <div className="relative h-full min-w-0 flex-1">
                                            <UnifiedWorkflow
                                                mode={browseMode}
                                                isDark={isDark}
                                                nodes={nodes}
                                                edges={edges}
                                                importedNodes={nodes}
                                                importedEdges={edges}
                                                workflowId={selectedId}
                                                workflowName={currentWf?.name}
                                                workflowDescription={currentWf?.rawText?.description}
                                                workflowMetadata={currentWf?.rawText}
                                                onCancel={() => setBrowseMode('view')}
                                                onSaveSuccess={(savedId, design, graph) => {
                                                    if (savedId && savedId === selectedId) acceptCanvasSave(savedId, design, graph);
                                                    fetchWorkflows();
                                                }}
                                            />
                                        </div>
                                    </div>
                                </>
                            ) : (
                                <div className="flex h-full flex-col items-center justify-center text-cm-faint dark:text-zinc-500">
                                    <Eye size={36} className="mb-3 opacity-30" />
                                    <p className="text-[12px] font-medium">{t('orchestration.select_workflow_hint')}</p>
                                </div>
                            )}
                        </div>
                    </div>
                );

            case 'packages':
                return (
                    <SolutionPackages
                        onBack={() => setActiveView('welcome')}
                        onImportPdf={handleImportPdfFromPackage}
                        onViewWorkflow={(wfId) => {
                            setOpenedFromPackage(true);
                            setSelectedId(wfId);
                        }}
                        loading={loading && loadingStatus !== LOADING_STAGES.IDLE}
                        loadingStatus={loadingStatus}
                        progress={progress}
                        t={t}
                    />
                );

            case 'ai':
                return (
                    <div
                        className="relative flex h-full w-full flex-col items-center justify-center overflow-hidden bg-cm-canvas p-8 dark:bg-cm-night">
                        <div
                            className="pointer-events-none absolute inset-x-0 top-0 h-64 bg-gradient-to-b from-cm-sky/70 to-transparent dark:from-zinc-900/50" />
                        <div
                            className="relative w-full max-w-[820px] animate-in">
                            <div
                                className="cm-card overflow-hidden dark:border-zinc-800 dark:bg-zinc-900">
                                <div className="flex items-center justify-between gap-3 border-b border-cm-line-soft px-5 py-4 dark:border-zinc-800">
                                    <div className="flex items-center gap-3">
                                        <span
                                            className="cm-entity-icon-square dark:bg-zinc-800 dark:text-blue-400">
                                            <Sparkles size={17} />
                                        </span>
                                        <div>
                                            <h3 className="cm-entity-title dark:text-zinc-100">{t('orchestration.ai_orchestrator')}</h3>
                                        </div>
                                    </div>
                                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500 animate-pulse" />
                                </div>
                                <textarea
                                    value={aiPrompt}
                                    onChange={e => setAiPrompt(e.target.value)}
                                    className="custom-scrollbar h-40 w-full resize-none border-none bg-transparent px-5 py-4 text-[13px] leading-[1.7] text-cm-ink outline-none placeholder:text-cm-faint dark:text-zinc-100 dark:placeholder:text-zinc-600"
                                    placeholder="..."
                                />
                                <div
                                    className="flex items-center justify-between border-t border-cm-line-soft px-5 py-3.5 dark:border-zinc-800">
                                    <div className="flex items-center gap-4">
                                    </div>

                                    <button
                                        onClick={async () => {
                                            if (!aiPrompt.trim()) return;
                                            setLoading(true);
                                            setLoadingStatus(LOADING_STAGES.GENERATING);
                                            try {
                                                setGenerationError(null);
                                                const result = await generateWorkflowFromIntent(aiPrompt, undefined, { binding: generationBinding });
                                                const { nodes: n, edges: e } = transformWorkflowToReactFlow(result);
                                                setNodes(n);
                                                setEdges(e);
                                                // The backend auto-saves the generated PSOP; reuse its id
                                                // so a manual save updates that copy instead of duplicating
                                                setCurrentWf({ id: result.id, name: result.name, rawText: result });
                                                setSavedWorkflowId(null);
                                                setActiveView('editor');
                                            } catch (err) {
                                                setGenerationError(generationErrorMessage(err));
                                            } finally {
                                                setLoading(false);
                                                setLoadingStatus(LOADING_STAGES.IDLE);
                                            }
                                        }}
                                        disabled={loading}
                                        className={`group flex items-center gap-2 px-4 py-2 text-[13px]
        ${aiPrompt.trim() && !loading
                                                ? 'cm-btn-primary'
                                                : 'cm-btn cursor-not-allowed opacity-50'}
    `}
                                    >
                                        <span className="relative">
                                            {loading ? t('orchestration.generating') : t('orchestration.generate')}
                                        </span>
                                        {loading ? (
                                            <Loader2 size={15} className="animate-spin" />
                                        ) : (
                                            <ChevronRight size={15}
                                                className="transition-transform duration-200 group-hover:translate-x-0.5" />
                                        )}
                                    </button>
                                </div>
                            </div>
                        </div>

                        <button
                            onClick={() => {
                                setActiveView('welcome');
                                setAiPrompt("");
                            }}
                            className="group relative mt-6 flex items-center gap-2 text-[11px] font-medium text-cm-muted transition-colors hover:text-cm-primary dark:text-zinc-400 dark:hover:text-blue-400"
                        >
                            <div className="h-[1px] w-6 bg-cm-line-strong transition-all group-hover:w-9 dark:bg-zinc-700" />
                            {t('orchestration.back_to_options')}
                        </button>
                    </div>
                );

            case 'detail':
            case 'editor':
                return (
                    <div className="flex h-full animate-in bg-cm-canvas dark:bg-cm-night">
                        <div
                            className={`relative flex flex-col border-r border-cm-line bg-cm-canvas-soft transition-all duration-300 ease-in-out dark:border-zinc-800 dark:bg-zinc-900
                    ${showConfig ? 'w-1/3 p-4 opacity-100' : 'pointer-events-none w-0 p-0 opacity-0'}`}
                        >
                            <div className="flex items-center justify-between">
                                <div className="cm-eyebrow text-cm-muted dark:text-zinc-500">
                                    workflow
                                </div>
                            </div>
                            <textarea
                                readOnly={true}
                                value={dump(currentWf?.rawText || {})}
                                className="mt-2 flex-1 rounded-cm border border-cm-line bg-white p-4 font-mono text-[11px] leading-[1.6] text-cm-ink outline-none dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-200"
                            />
                        </div>

                        <div className="relative flex-1">
                            <button
                                onClick={() => setShowConfig(!showConfig)}
                                className={`cm-icon-btn absolute left-4 top-8 z-[70] -translate-y-1/2 border border-cm-line bg-white shadow-card transition-all hover:border-[#B8CFFC] dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-300
                        ${!showConfig ? 'translate-x-0' : 'translate-x-[-10px]'}`}
                            >
                                {showConfig ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <UnifiedWorkflow
                                mode={activeView === 'detail' ? 'view' : 'edit'}
                                newWorkflowBinding={generationBinding}
                                isDark={isDark}
                                // Props for View mode
                                nodes={nodes}
                                edges={edges}
                                // Props for Edit mode
                                importedNodes={nodes}
                                importedEdges={edges}
                                workflowId={selectedId || currentWf?.id || savedWorkflowId}
                                workflowName={currentWf?.name}
                                workflowDescription={currentWf?.rawText?.description}
                                workflowMetadata={currentWf?.rawText}
                                onCancel={() => {
                                    if (selectedId) {
                                        setActiveView('detail');
                                    } else {
                                        setCurrentWf(null);
                                        setSavedWorkflowId(null);
                                        setActiveView('welcome');
                                    }
                                }}
                                onSaveSuccess={(savedId, design, graph) => {
                                    if (savedId && !selectedId) setSavedWorkflowId(savedId);
                                    acceptCanvasSave(savedId, design, graph);
                                    fetchWorkflows();
                                }}
                                onDirtyChange={setEditorDirty}
                            />
                        </div>
                    </div>
                );
            default:
                return null;
        }
    };

    // Muted 12px line under the page title; each view reuses its existing copy.
    const headerSubtitle = activeView === 'welcome' ? t('brand.slogan')
        : activeView === 'ai' ? t('orchestration.method_ai')
            : activeView === 'packages' ? t('orchestration.packages_list_title')
                : activeView === 'browse' ? t('orchestration.browse_workflow_hint')
                    : null;

    return (
        <div
            className="flex h-full w-full items-stretch overflow-hidden bg-cm-canvas font-sans dark:bg-cm-night">
            <div
                className="relative flex flex-1 flex-col overflow-hidden">
                <div
                    className="flex shrink-0 items-start justify-between gap-4 px-6 pb-3 pt-5">
                    <div className="min-w-0">
                        <h2 className="cm-section-title truncate dark:text-zinc-100">
                            {activeView === 'welcome' ? t('orchestration.start') : (activeView === 'ai' ? t('orchestration.ai_orchestrator') : (activeView === 'packages' ? t('orchestration.packages_title') : (activeView === 'browse' ? t('orchestration.browse_workflow') : (currentWf?.name || t('orchestration.new_design')))))}
                        </h2>
                        {headerSubtitle && (
                            <p className="mt-[3px] truncate text-[12px] text-cm-muted dark:text-zinc-400">
                                {headerSubtitle}
                            </p>
                        )}
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                        {activeView === 'detail' && openedFromPackage && (
                            <button
                                onClick={() => {
                                    setActiveView('packages');
                                    setSelectedId(null);
                                    setCurrentWf(null);
                                    setOpenedFromPackage(false);
                                }}
                                className="cm-btn group h-[33px] dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:text-blue-300"
                            >
                                <ArrowLeft size={13} className="transition-transform group-hover:-translate-x-0.5" />
                                {t('orchestration.back_to_packages')}
                            </button>
                        )}
                        {(activeView === 'editor' || activeView === 'ai') && (
                            <button
                                onClick={() => {
                                    if (activeView === 'editor' && editorDirty) {
                                        setShowLeaveEditorConfirm(true);
                                        return;
                                    }
                                    setActiveView('welcome');
                                    setSelectedId(null);
                                    setCurrentWf(null);
                                    setAiPrompt('');
                                }}
                                className="cm-btn group h-[33px] dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:text-blue-300"
                            >
                                <ArrowLeft size={13} className="transition-transform group-hover:-translate-x-0.5" />
                                {t('orchestration.back_to_options')}
                            </button>
                        )}

                        {activeView === 'detail' && (
                            <button
                                onClick={() => setActiveView('editor')}
                                className="cm-btn-primary h-[33px] dark:border-blue-500 dark:bg-blue-500 dark:hover:border-blue-400 dark:hover:bg-blue-400"
                            >
                                <Code2 size={14} />
                                <span>{t('orchestration.edit')}</span>
                            </button>
                        )}
                    </div>
                </div>

                {['welcome', 'ai', 'packages'].includes(activeView) && <div className="flex shrink-0 items-center gap-3 px-6 pb-3">
                    <GenerationMode value={generationBinding} onChange={value => { setGenerationBinding(value); setGenerationError(null); }} disabled={loading} />
                </div>}
                {generationError && <p role="alert" className="border-b border-rose-100 bg-rose-50/60 px-6 py-2.5 text-[12px] text-rose-600 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-400">{generationError}</p>}
                <div className="relative flex-1 overflow-hidden">
                    {renderContent()}
                </div>
            </div>

            <input type="file" ref={fileInput} className="hidden"
                accept=".pdf"
                onChange={handleFileChange} />

            {/* Delete confirmation dialog */}
            {showDeleteConfirm && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/25 backdrop-blur-sm animate-in">
                    <div className="w-full max-w-[420px] animate-in rounded-3xl border border-cm-line bg-white p-6 shadow-modal dark:border-zinc-800 dark:bg-zinc-900">
                        <div className="flex flex-col items-center text-center">
                            <span className="mb-4 grid h-11 w-11 place-items-center rounded-cm bg-rose-50 text-rose-500 dark:bg-rose-950/30 dark:text-rose-400">
                                <Trash2 size={20} />
                            </span>
                            <h3 className="mb-1.5 text-[16px] font-bold text-cm-heading dark:text-zinc-100">
                                {t('orchestration.delete_workflow_title')}
                            </h3>
                            <p className="mb-6 text-[12px] leading-[1.7] text-cm-muted dark:text-zinc-400">
                                {t('orchestration.delete_workflow_confirm')}
                                <br />
                                <span className="font-semibold text-cm-ink italic dark:text-zinc-200">"{wfToDelete?.name}"</span>
                            </p>

                            <div className="flex w-full gap-2.5">
                                <button
                                    onClick={() => {
                                        setShowDeleteConfirm(false);
                                        setWfToDelete(null);
                                    }}
                                    className="cm-btn flex-1 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    onClick={handleDeleteWorkflow}
                                    className="cm-btn flex-1 border-rose-600 bg-rose-600 text-white hover:border-rose-500 hover:bg-rose-500 hover:text-white active:translate-y-px"
                                >
                                    {t('common.delete')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
            {/* Leave-editor confirmation dialog (global header back button) */}
            {showLeaveEditorConfirm && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/25 backdrop-blur-sm animate-in">
                    <div className="w-full max-w-[420px] animate-in rounded-3xl border border-cm-line bg-white p-6 shadow-modal dark:border-zinc-800 dark:bg-zinc-900">
                        <div className="flex flex-col items-center text-center">
                            <span className="mb-4 grid h-11 w-11 place-items-center rounded-cm bg-amber-50 text-amber-500 dark:bg-amber-950/30 dark:text-amber-400">
                                <TriangleAlert size={20} />
                            </span>
                            <h3 className="mb-1.5 text-[16px] font-bold text-cm-heading dark:text-zinc-100">
                                {t('workflow.exit.title')}
                            </h3>
                            <p className="mb-6 text-[12px] leading-[1.7] text-cm-muted dark:text-zinc-400">
                                {t('workflow.exit.desc')}
                            </p>

                            <div className="flex w-full gap-2.5">
                                <button
                                    onClick={() => setShowLeaveEditorConfirm(false)}
                                    className="cm-btn flex-1 dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    onClick={() => {
                                        setShowLeaveEditorConfirm(false);
                                        setEditorDirty(false);
                                        setActiveView('welcome');
                                        setSelectedId(null);
                                        setCurrentWf(null);
                                        setSavedWorkflowId(null);
                                    }}
                                    className="cm-btn-primary flex-1"
                                >
                                    {t('common.confirm')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default OrchestrationCenter;
