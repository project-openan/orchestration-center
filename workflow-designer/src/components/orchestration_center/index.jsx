import React, { useState, useMemo, useEffect, useRef } from 'react';
import yaml, { dump } from 'js-yaml';
import {
    Search, Loader2, Layout, FileWarning, Hash,
    Activity, Plus, Upload, X, MessageSquare,
    ChevronRight, Save, Sparkles, Edit3, ChevronLeft, ArrowLeft, Code2, LayoutDashboard, Trash2
} from 'lucide-react';
import { getAgentCards, getWorkflow, getWorkflowById, handlePlan, parsePdf, generateWorkflowFromIntent, delWorkflowById } from "@/service/api.js";
import { transformWorkflowToReactFlow } from "./workflow/utils/index.jsx";
import UnifiedWorkflow from "../orchestration_center/workflow/index.jsx";
import { useTranslation } from 'react-i18next';


const MethodCard = ({ icon: Icon, title, onClick, color, loading, progress, status, t }) => (
    <button
        onClick={onClick}
        disabled={loading}
        className={`
            group relative flex flex-col items-center gap-6 p-10 w-56
            bg-white dark:bg-zinc-800 
            rounded-[3rem] shadow-xl hover:shadow-3xl 
            ${!loading ? 'hover:-translate-y-3' : 'cursor-wait'} 
            transition-all duration-500 ease-[cubic-bezier(0.34,1.56,0.64,1)]
            animate-in fade-in slide-in-from-bottom-8 fill-mode-both
            overflow-hidden
        `}
    >
        {loading && (
            <div
                className="absolute inset-0 bg-blue-500/5 dark:bg-blue-400/5 transition-all duration-300 ease-out origin-left"
                style={{ width: `${progress}%` }}
            />
        )}

        <div className={`
            p-6 rounded-[2rem] bg-zinc-50 dark:bg-zinc-700 
            ${!loading && 'group-hover:rotate-6'} transition-all duration-500
            ${color} 
            shadow-outer z-10
        `}>
            <Icon size={32} strokeWidth={2.5} />
        </div>

        <div className="flex flex-col items-center z-10">
            <span className="text-[17px] font-black dark:text-zinc-200 mb-1">
                {title}
            </span>
            {loading && (<span className="text-[13px] font-black dark:text-zinc-200 mb-1">
                {t ? t(status) : status} {Math.floor(progress)}%
            </span>)}
            <div className={`h-1 transition-all duration-500 rounded-full w-0 group-hover:w-8 bg-blue-500`} />
        </div>

        {loading && (
            <div className="absolute bottom-0 left-0 w-full h-1.5 bg-zinc-100 dark:bg-zinc-800">
                <div
                    className="h-full bg-gradient-to-r from-blue-500 to-indigo-500 transition-all duration-300 shadow-[0_0_10px_rgba(59,130,246,0.5)]"
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
    const { t } = useTranslation();
    const [workflows, setWorkflows] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [currentWf, setCurrentWf] = useState(null);
    const [searchTerm, setSearchTerm] = useState('');
    const [activeView, setActiveView] = useState('welcome'); // 'welcome' | 'detail' | 'ai' | 'editor'
    const [aiPrompt, setAiPrompt] = useState("");
    const [showConfig, setShowConfig] = useState(false);
    const [progress, setProgress] = useState(0);
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);
    const fileInput = useRef(null);

    const [loading, setLoading] = useState(false);
    const [detailLoading, setDetailLoading] = useState(false);
    const [loadingStatus, setLoadingStatus] = useState(LOADING_STAGES.IDLE);

    // 删除确认相关状态
    const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
    const [wfToDelete, setWfToDelete] = useState(null);
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
            event.target.value = ''; // 清空选择
            return;
        }

        const formData = new FormData();
        // 注意：对应后台 request.files['file']
        formData.append('file', file);

        setLoading(true);
        setLoadingStatus(LOADING_STAGES.PARSING); // 阶段 1
        try {
            const contentData = await parsePdf(file);
            console.log("解析出的内容:", contentData);
            const agentCards = await getAgentCards();
            setLoadingStatus(LOADING_STAGES.PLANNING); // 阶段 2
            const finalPlan = await handlePlan(contentData, agentCards.data);
            console.log('finalPlan', finalPlan)

            setLoadingStatus(LOADING_STAGES.FINALIZING); // 阶段 3
            const { nodes: n, edges: e } = transformWorkflowToReactFlow(finalPlan);
            setNodes(n);
            setEdges(e);
            console.log('finalPlanWorkflow', nodes, edges)
            setActiveView('detail');
        } catch (error) {
            const errorMsg = error.response?.data?.error || "服务器响应异常";
            console.error("上传失败:", errorMsg);
        } finally {
            setLoading(false);
            setLoadingStatus(LOADING_STAGES.IDLE);
            event.target.value = '';
        }
    };

    const fetchWorkflows = async () => {
        try {
            setLoading(true);
            const res = await getWorkflow();
            console.log('getWorkflow', res)
            if (res.status === 'success') {
                const data = (res.data || []).map(item => ({
                    id: item.workflow_id,
                    name: item.name || 'Untitled',
                    tags: item.tags || [],
                    description: item.description
                }));
                console.log('item', data);
                setWorkflows(data);
            }
        } catch (e) {
            console.error("获取PSOP列表失败:", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchWorkflows();
    }, []);

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
                    console.log('detailData', detailData);

                    setCurrentWf({
                        id: detailData.id,
                        name: detailData.name,
                        rawText: detailData
                    });

                    // 转换画布节点
                    const { nodes: n, edges: e } = transformWorkflowToReactFlow(detailData);
                    setNodes(n);
                    setEdges(e);

                    if (activeView !== 'editor') setActiveView('detail');
                }
            } catch (e) {
                console.error("获取PSOP详情失败:", e);
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
                // 如果删除的是当前选中的，重置视图
                if (selectedId === wfToDelete.id) {
                    setSelectedId(null);
                    setActiveView('welcome');
                }
                await fetchWorkflows();
            }
        } catch (e) {
            console.error("删除PSOP失败:", e);
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
                    <div className="h-full w-full relative flex flex-col items-center justify-center overflow-hidden">
                        <div className="absolute inset-0 opacity-[0.03] dark:opacity-[0.05] pointer-events-none"
                            style={{
                                backgroundImage: 'radial-gradient(#000 1px, transparent 0)',
                                backgroundSize: '40px 40px'
                            }} />

                        <div className="mb-16 text-center z-10 animate-in fade-in zoom-in-95 duration-1000">
                            <h2 className="text-4xl font-black dark:text-white  mb-3">
                                {t('orchestration.build_workflow')}
                            </h2>
                        </div>

                        <div className="flex gap-8 z-10">
                            <MethodCard
                                icon={Upload} title={t('orchestration.method_import')} color="text-amber-500"
                                onClick={() => fileInput.current.click()}
                                loading={loading && loadingStatus !== LOADING_STAGES.IDLE}
                                progress={progress}
                                status={loadingStatus}
                                t={t}
                            />
                            <MethodCard
                                icon={Layout} title={t('orchestration.method_graph')} color="text-blue-500"
                                onClick={() => {
                                    setSelectedId(null);
                                    setActiveView('editor');
                                    setNodes([]);
                                    setEdges([]);
                                }}
                            />
                            <MethodCard
                                icon={MessageSquare} title={t('orchestration.method_ai')} color="text-purple-500"
                                onClick={() => setActiveView('ai')}
                                loading={loading && loadingStatus === LOADING_STAGES.GENERATING}
                                progress={progress}
                                status={loadingStatus}
                                t={t}
                            />
                        </div>

                        <div
                            className="absolute bottom-10 w-32 h-[1px] bg-gradient-to-r from-transparent via-zinc-200 dark:via-zinc-800 to-transparent" />
                    </div>
                );

            case 'ai':
                return (
                    <div
                        className="h-full w-full relative flex flex-col items-center justify-center p-10 overflow-hidden bg-zinc-50/20 dark:bg-zinc-950/20">
                        <div
                            className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-purple-500/10 blur-[120px] rounded-full pointer-events-none" />
                        <div
                            className="w-full max-w-6xl relative group animate-in zoom-in-95 slide-in-from-bottom-8 duration-700">
                            <div
                                className="absolute -inset-[1px] bg-gradient-to-r from-purple-300 via-blue-500 to-purple-200 rounded-[3rem] opacity-20 group-focus-within:opacity-40 blur-[2px] transition-opacity duration-500" />
                            <div
                                className="relative bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-[3rem] p-10 shadow-2xl overflow-hidden">
                                <div className="flex items-center justify-between mb-8">
                                    <div className="flex items-center gap-3">
                                        <div
                                            className="p-2.5 rounded-xl bg-purple-100 dark:bg-purple-500/10 text-purple-600 dark:text-purple-400">
                                            <Sparkles size={20} />
                                        </div>
                                        <div>
                                            <h3 className="text-base font-black dark:text-white uppercase tracking-tight">{t('orchestration.ai_orchestrator')}</h3>
                                        </div>
                                    </div>
                                    <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                                </div>
                                <textarea
                                    value={aiPrompt}
                                    onChange={e => setAiPrompt(e.target.value)}
                                    className="w-full bg-transparent border-none outline-none text-xl font-medium leading-relaxed dark:text-zinc-100 placeholder:text-zinc-300 dark:placeholder:text-zinc-700 h-40 resize-none custom-scrollbar transition-all"
                                    placeholder="..."
                                />
                                <div
                                    className="flex items-center justify-between mt-6 pt-6 border-t border-zinc-50 dark:border-zinc-800/50">
                                    <div className="flex items-center gap-4">
                                    </div>

                                    <button
                                        onClick={async () => {
                                            if (!aiPrompt.trim()) return;
                                            setLoading(true);
                                            setLoadingStatus(LOADING_STAGES.GENERATING);
                                            try {
                                                const result = await generateWorkflowFromIntent(aiPrompt);
                                                const { nodes: n, edges: e } = transformWorkflowToReactFlow(result);
                                                setNodes(n);
                                                setEdges(e);
                                                setActiveView('editor');
                                            } catch (err) {
                                                console.error("生成失败:", err);
                                            } finally {
                                                setLoading(false);
                                                setLoadingStatus(LOADING_STAGES.IDLE);
                                            }
                                        }}
                                        disabled={loading}
                                        className={`
        group flex items-center gap-3 px-8 py-4 rounded-2xl font-black text-xs tracking-widest transition-all duration-500
        ${aiPrompt.trim() && !loading
                                                ? 'bg-zinc-900 text-white dark:bg-white dark:text-zinc-950 shadow-[0_10px_30px_rgba(0,0,0,0.2)] dark:shadow-[0_10px_30px_rgba(255,255,255,0.1)] hover:-translate-x-1 active:scale-95'
                                                : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-400 cursor-not-allowed opacity-50'}
    `}
                                    >
                                        <span className="relative">
                                            {loading ? t('orchestration.generating') : t('orchestration.generate')}
                                        </span>
                                        {loading ? (
                                            <Loader2 size={18} className="animate-spin" />
                                        ) : (
                                            <ChevronRight size={18}
                                                className="group-hover:translate-x-1 transition-transform duration-300" />
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
                            className="mt-12 group flex items-center gap-2 text-[11px] font-black text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 transition-all uppercase tracking-[0.2em]"
                        >
                            <div className="w-6 h-[1px] bg-zinc-300 dark:bg-zinc-700 group-hover:w-10 transition-all" />
                            {t('orchestration.back_to_options')}
                        </button>
                    </div>
                );

            case 'detail':
            case 'editor':
                return (
                    <div className="h-full flex animate-in fade-in duration-300">
                        <div
                            className={`border-r border-zinc-100 dark:border-zinc-900 flex flex-col bg-zinc-50/30 dark:bg-zinc-900  duration-500 ease-in-out relative
                    ${showConfig ? 'w-1/3 p-8 opacity-100' : 'w-0 p-0 opacity-0 pointer-events-none'}`}
                        >
                            <div className="flex items-center justify-between">
                                <div className="text-[10px] font-black text-zinc-400 uppercase">
                                    workflow
                                </div>
                            </div>
                            <textarea
                                readOnly={true}
                                value={dump(currentWf?.rawText || {})}
                                className="flex-1 bg-white dark:bg-zinc-950 border border-zinc-200 dark:border-zinc-800 rounded-[2rem] p-6 font-mono text-xs shadow-inner outline-none"
                            />
                        </div>

                        <div className="flex-1 relative">
                            <button
                                onClick={() => setShowConfig(!showConfig)}
                                className={`absolute left-4 top-8 -translate-y-1/2 z-[70] p-2 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-full shadow-lg hover:scale-110 transition-all
                        ${!showConfig ? 'translate-x-0' : 'translate-x-[-10px]'}`}
                            >
                                {showConfig ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
                            </button>
                            <UnifiedWorkflow
                                mode={activeView === 'detail' ? 'view' : 'edit'}
                                isDark={isDark}
                                // View 模式使用的 Props
                                nodes={nodes}
                                edges={edges}
                                // Edit 模式使用的 Props
                                importedNodes={nodes}
                                importedEdges={edges}
                                workflowId={selectedId}
                                workflowName={currentWf?.name}
                                workflowDescription={currentWf?.rawText?.description}
                                onCancel={() => {
                                    if (selectedId) {
                                        setActiveView('detail');
                                    } else {
                                        setActiveView('welcome');
                                    }
                                }}
                                onSaveSuccess={fetchWorkflows}
                            />
                        </div>
                    </div>
                );
            default:
                return null;
        }
    };

    return (
        <div
            className="h-full p-8 flex items-stretch gap-8 w-full bg-zinc-50 dark:bg-zinc-950 overflow-hidden font-sans">
            <div className="w-[300px] flex flex-col gap-6 shrink-0">
                <div
                    className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-[2.5rem] p-6 shadow-xl">
                    <div className="flex items-center justify-between mb-5">
                        <h1 className="text-xl font-black dark:text-white tracking-tighter uppercase">{t('orchestration.title')}</h1>
                        <button
                            onClick={() => {
                                setSelectedId(null);
                                setActiveView('welcome');
                            }}
                            className="p-2.5 bg-zinc-900 dark:bg-white dark:text-zinc-900 text-white rounded-xl hover:scale-105 transition-all shadow-lg"
                        >
                            <Plus size={18} strokeWidth={3} />
                        </button>
                    </div>
                    <div className="relative">
                        <input
                            type="text"
                            placeholder={t('orchestration.search')}
                            className="w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 rounded-2xl text-xs font-bold outline-none"
                            onChange={e => setSearchTerm(e.target.value)}
                        />
                        <Search className="absolute left-3.5 top-3.5 text-zinc-400" size={14} />
                    </div>
                </div>
                <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar px-1">
                    {workflows.filter(wf => wf.name.toLowerCase().includes(searchTerm.toLowerCase())).map(wf => {
                        const isSelected = selectedId === wf.id;
                        return (
                            <div
                                key={wf.id}
                                onClick={() => {
                                    if (selectedId !== wf.id) {
                                        setSelectedId(wf.id);
                                    } else {
                                        if (activeView !== 'editor') setActiveView('detail');
                                    }
                                }}
                                className={`
                        group p-5 rounded-2xl border transition-all duration-300 cursor-pointer relative overflow-hidden
                        ${isSelected
                                        ? 'bg-zinc-100 dark:bg-zinc-800 border-transparent shadow-inner'
                                        : 'border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900 opacity-60 hover:opacity-100'
                                    }
                    `}
                            >
                                {isSelected && (
                                    <div className="absolute left-0 top-0 bottom-0 w-1.5 bg-blue-600 animate-pulse" />
                                )}

                                <div className="flex items-center justify-between mb-2 pl-2">
                                    <div
                                        className={`flex items-center gap-3 ${isSelected ? 'text-zinc-900 dark:text-white' : 'text-zinc-400'}`}>
                                        <Hash size={16} />
                                        <h3 className="font-black text-base uppercase leading-none truncate max-w-[180px]">
                                            {wf.name}
                                        </h3>
                                    </div>
                                    <button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setWfToDelete(wf);
                                            setShowDeleteConfirm(true);
                                        }}
                                        className="opacity-0 group-hover:opacity-100 p-1.5 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/30 dark:hover:text-red-400 rounded-lg transition-all"
                                    >
                                        <Trash2 size={14} />
                                    </button>
                                </div>

                                <div
                                    className={`pl-8 text-[11px] font-black uppercase truncate max-w-[200px] ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-zinc-400'}`}>
                                    {wf.tags?.length > 0 ? wf.tags.join(', ') : t('orchestration.no_tags')}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </div>
            <div
                className="flex-1 bg-white dark:bg-zinc-900 rounded-[3.5rem] border border-zinc-200 dark:border-zinc-800 shadow-2xl relative overflow-hidden flex flex-col">
                <div
                    className="px-10 py-6 border-b border-zinc-50 dark:border-zinc-800 flex justify-between items-center  bg-white dark:bg-zinc-900 backdrop-blur-md shrink-0">
                    <div className="flex items-center gap-4">
                        <h2 className="text-lg font-black dark:text-white uppercase">
                            {activeView === 'welcome' ? t('orchestration.start') : (activeView === 'ai' ? t('orchestration.ai_orchestrator') : (currentWf?.name || t('orchestration.new_design')))}
                        </h2>

                        {activeView === 'detail' && (

                            <button
                                onClick={() => setActiveView('editor')}
                                className={`
        flex items-center gap-2 px-3 py-1.5 rounded-md  uppercase text-[12px] font-bold shadow-sm
        active:scale-95 active:shadow-inner
        ${isDark
                                        ? 'bg-zinc-100 hover:bg-slate-500 text-black shadow-blue-900/20'
                                        : 'bg-slate-900 hover:bg-slate-800 text-white shadow-blue-200'}
    `}
                            >
                                <Code2 size={14} />
                                <span>{t('orchestration.edit')}</span>
                            </button>
                        )}
                    </div>
                </div>

                <div className="flex-1 relative overflow-hidden">
                    {renderContent()}
                </div>
            </div>

            <input type="file" ref={fileInput} className="hidden"
                accept=".pdf"
                onChange={handleFileChange} />

            {/* 删除确认弹窗 */}
            {showDeleteConfirm && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/20 backdrop-blur-sm animate-in fade-in duration-300">
                    <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl w-full max-w-md scale-in-center animate-in zoom-in-95 duration-300">
                        <div className="flex flex-col items-center text-center">
                            <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-2xl mb-6">
                                <Trash2 size={32} />
                            </div>
                            <h3 className="text-xl font-black dark:text-white mb-2 uppercase tracking-tight">
                                {t('orchestration.delete_workflow_title')}
                            </h3>
                            <p className="text-zinc-500 dark:text-zinc-400 text-sm mb-8">
                                {t('orchestration.delete_workflow_confirm')}
                                <br />
                                <span className="font-bold text-zinc-900 dark:text-zinc-100 italic">"{wfToDelete?.name}"</span>
                            </p>

                            <div className="flex gap-4 w-full">
                                <button
                                    onClick={() => {
                                        setShowDeleteConfirm(false);
                                        setWfToDelete(null);
                                    }}
                                    className="flex-1 px-6 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-bold text-xs uppercase tracking-widest hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    onClick={handleDeleteWorkflow}
                                    className="flex-1 px-6 py-3 rounded-xl bg-red-500 text-white font-bold text-xs uppercase tracking-widest hover:bg-red-600 shadow-lg shadow-red-500/20 active:scale-95 transition-all"
                                >
                                    {t('common.delete')}
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
