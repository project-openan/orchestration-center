import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Play,
    StopCircle,
    Activity,
    Terminal,
    CheckCircle,
    AlertCircle,
    Clock,
    Search,
    Hash,
    ChevronRight,
    MessageSquare,
    History,
    Plus,
    Bot
} from 'lucide-react';
import { getWorkflow, getWorkflowById, getStartProcessStreamUrl, matchWorkflows } from '@/service/api.js';
import { transformWorkflowToReactFlow } from '@/components/orchestration_center/workflow/utils/index.jsx';
import UnifiedWorkflow from '../orchestration_center/workflow/index.jsx';

const parseLogData = (data, type) => {
    const raw = type === 'agent_request' ? data.request : data.response;
    try {
        let parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;

        // Unwrap the outermost 'request' or 'response' key if it exists
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            if (type === 'agent_request' && parsed.request) {
                parsed = parsed.request;
            } else if (type === 'agent_response' && parsed.response) {
                parsed = parsed.response;
            }
        }

        return parsed; // Return the object instead of string for better processing
    } catch (e) {
        return raw;
    }
};

const LogEntry = React.memo(({ event, isDark, t, isSelected }) => {
    const [showDetail, setShowDetail] = useState(false);
    const parsed = useMemo(() => parseLogData(event.data, event.type), [event]);

    const textContent = useMemo(() => {
        if (!parsed) return '';
        if (typeof parsed === 'string') return parsed;

        const findText = (obj) => {
            if (!obj || typeof obj !== 'object') return typeof obj === 'string' ? [obj] : [];
            if (Array.isArray(obj)) return obj.flatMap(findText);

            let results = [];
            // Collect specific content keys
            if (obj.text && typeof obj.text === 'string') results.push(obj.text);
            if (obj.message && typeof obj.message === 'string') results.push(obj.message);

            // Recurse into common containers if no text was found at this level
            if (results.length === 0) {
                if (obj.parts) results = results.concat(findText(obj.parts));
                if (obj.artifacts) results = results.concat(findText(obj.artifacts));
            }

            // If still nothing, do a shallow scan for nested structures that might have text
            if (results.length === 0) {
                Object.keys(obj).forEach(key => {
                    if (typeof obj[key] === 'object' && obj[key] !== null) {
                        results = results.concat(findText(obj[key]));
                    }
                });
            }

            return results;
        };

        const allText = Array.from(new Set(findText(parsed))); // Deduplicate just in case
        return allText.join('\n\n');
    }, [parsed]);

    return (
        <div 
            data-agent={event.data.agent}
            className={`relative pl-10 border-l-2 py-4 animate-in-basic transition-all duration-500 rounded-r-2xl
                ${isSelected 
                    ? 'bg-blue-500/5 border-blue-500 shadow-[inset_4px_0_0_0_#3b82f6]' 
                    : 'border-zinc-100 dark:border-zinc-800/50'}`}
        >
            <div className={`absolute -left-[9px] top-6 w-4 h-4 rounded-full border-4 ${isDark ? 'border-zinc-900' : 'border-white'} 
                ${event.type === 'agent_request' ? 'bg-blue-600' : 'bg-purple-600'}
                ${isSelected ? 'ring-4 ring-blue-500/20 scale-125 transition-transform' : ''}`}
            />

            <div className="flex items-center gap-4 mb-3">
                <div className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border-2 shadow-sm transition-all
                    ${event.type === 'agent_request'
                        ? 'bg-blue-50 border-blue-100 text-blue-700 dark:bg-blue-900/20 dark:border-blue-800/50 dark:text-blue-400'
                        : 'bg-purple-50 border-purple-100 text-purple-700 dark:bg-purple-900/20 dark:border-purple-800/50 dark:text-purple-400'}`}
                >
                    <Bot size={15} className="opacity-80" />
                    <span className="text-[12.5px] font-black uppercase tracking-widest font-mono">{event.data.agent}</span>
                </div>

                <span className="ml-auto text-[11px] font-mono opacity-30">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
            </div>

            <div className={`group relative opacity-95 break-words font-sans text-[14.5px] leading-relaxed bg-white dark:bg-black/30 p-6 rounded-2xl border transition-all duration-300 ring-1 ring-black/5 dark:ring-white/5
                ${isSelected ? 'border-blue-500/40 shadow-blue-500/10' : 'border-zinc-100 dark:border-zinc-800/50'}
                ${showDetail ? 'ring-blue-500/30' : ''}`}>
                {showDetail ? (
                    <pre className="font-mono text-[12.5px] overflow-x-auto whitespace-pre-wrap max-h-[600px] custom-scrollbar">
                        {JSON.stringify(parsed, null, 2)}
                    </pre>
                ) : (
                    <div className="text-zinc-800 dark:text-zinc-200">
                        {textContent || <span className="italic opacity-40">{t('execution.no_text')}</span>}
                    </div>
                )}

                <button
                    onClick={() => setShowDetail(!showDetail)}
                    className="mt-5 flex items-center gap-2 ml-auto text-[11px] font-black uppercase tracking-tighter text-blue-600 hover:text-blue-500 transition-colors py-1.5 px-4 bg-blue-500/5 hover:bg-blue-500/10 rounded-full border border-blue-500/10"
                >
                    {showDetail ? t('execution.show_less') : t('execution.view_detail')}
                </button>
            </div>
        </div>
    );
});

const ExecutionCenter = ({ isDark }) => {
    const { t } = useTranslation();
    const [selectedId, setSelectedId] = useState(null);
    const [isRunning, setIsRunning] = useState(false);
    const [events, setEvents] = useState([]);
    const [psopStatus, setPsopStatus] = useState(null);
    const [error, setError] = useState(null);
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);
    const [eventSource, setEventSource] = useState(null);

    const [userIntent, setUserIntent] = useState('');
    const [workflowSource, setWorkflowSource] = useState(null); // 'retrieved' | 'generated'
    const [isMatching, setIsMatching] = useState(false);
    const [matchedWorkflows, setMatchedWorkflows] = useState([]);
    const [runningId, setRunningId] = useState(null);

    const logScrollRef = useRef(null);
    const [autoScroll, setAutoScroll] = useState(true);
    const [selectedNodeId, setSelectedNodeId] = useState(null);

    const handleNodeSelect = useCallback((node) => {
        if (!node) {
            setSelectedNodeId(null);
            return;
        }

        setSelectedNodeId(node.id);
        const agentName = node.data?.agent || node.data?.name;
        if (!agentName || !logScrollRef.current) return;

        // Search for all log entries for this agent
        const entries = logScrollRef.current.querySelectorAll(`[data-agent="${agentName}"]`);
        if (entries.length > 0) {
            // Scroll to the last entry of this agent to see the most recent context
            const target = entries[entries.length - 1];
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setAutoScroll(false); // Stop auto-scrolling if user clicked something
        }
    }, []);

    const handleMatchIntent = async () => {
        if (!userIntent.trim()) return;

        setIsMatching(true);
        setNodes([]);
        setEdges([]);
        setSelectedId(null);
        setMatchedWorkflows([]);
        setWorkflowSource(null);
        setError(null);

        try {
            const results = await matchWorkflows(userIntent);

            if (results && results.length > 0) {
                setMatchedWorkflows(results);
                setSelectedId(results[0].workflow_id);
                setWorkflowSource('retrieved');
            } else {
                setError(t('execution.no_match'));
            }
        } catch (err) {
            console.error("Failed to match workflows:", err);
            setError(t('execution.match_failed'));
        } finally {
            setIsMatching(false);
        }
    };

    useEffect(() => {
        if (autoScroll && logScrollRef.current) {
            const container = logScrollRef.current;
            container.scrollTo({
                top: container.scrollHeight,
                behavior: 'smooth'
            });
        }
    }, [events, autoScroll]);

    const handleScroll = useCallback((e) => {
        const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
        const isAtBottom = scrollHeight - scrollTop - clientHeight < 50; // Increased threshold slightly for better feel
        if (autoScroll !== isAtBottom) {
            setAutoScroll(isAtBottom);
        }
    }, [autoScroll]);

    useEffect(() => {
        if (psopStatus) {
            const { nodes: n, edges: e } = transformWorkflowToReactFlow(psopStatus);
            setNodes(n);
            setEdges(e);
        } else if (selectedId) {
            (async () => {
                try {
                    const res = await getWorkflowById(selectedId);
                    if (res.status === 'success') {
                        const { nodes: n, edges: e } = transformWorkflowToReactFlow(res.data);
                        setNodes(n);
                        setEdges(e);
                    }
                } catch (err) {
                    console.error("Failed to fetch workflow detail:", err);
                }
            })();
        }
    }, [psopStatus, selectedId]);

    // 停止执行
    const stopExecution = useCallback(() => {
        if (eventSource) {
            eventSource.close();
            setEventSource(null);
        }
        setIsRunning(false);
        setRunningId(null);
    }, [eventSource]);

    // 开始执行
    const startExecution = useCallback((overrideId) => {
        const idToRun = overrideId || selectedId;
        if (!idToRun) return;

        setError(null);
        setEvents([]);
        setPsopStatus(null);
        setIsRunning(true);
        setRunningId(idToRun);
        setAutoScroll(true);

        const url = getStartProcessStreamUrl(idToRun);
        const es = new EventSource(url);

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'agent_request' || data.type === 'agent_response') {
                    setEvents(prev => [...prev, data]);
                }

                switch (data.type) {
                    case 'psop_update':
                        try {
                            const status = typeof data.data.psop === 'string'
                                ? JSON.parse(data.data.psop)
                                : data.data.psop;
                            setPsopStatus(status);
                        } catch (e) {
                            console.error("Failed to parse psop_update data:", e);
                        }
                        break;
                    case 'complete':
                    case 'close':
                        setIsRunning(false);
                        setRunningId(null);
                        es.close();
                        break;
                    case 'error':
                        setError(data.data.error);
                        setIsRunning(false);
                        setRunningId(null);
                        es.close();
                        break;
                }
            } catch (err) {
                console.error("Failed to parse event data:", err);
            }
        };

        es.onerror = (err) => {
            setError("SSE Connection Error");
            setIsRunning(false);
            setRunningId(null);
            es.close();
        };

        setEventSource(es);
    }, [selectedId]);

    useEffect(() => {
        return () => {
            if (eventSource) eventSource.close();
        };
    }, [eventSource]);

    const theme = useMemo(() => ({
        panel: isDark
            ? 'bg-zinc-900 border-zinc-800 shadow-2xl backdrop-blur-xl'
            : 'bg-white border-zinc-200 shadow-2xl backdrop-blur-xl',
        header: isDark
            ? 'bg-zinc-800/20 border-zinc-800'
            : 'bg-zinc-50/50 border-zinc-100',
        input: isDark
            ? 'bg-zinc-800 border-zinc-700 text-white placeholder-zinc-500'
            : 'bg-zinc-100 border-zinc-200 text-zinc-900 placeholder-zinc-400',
        content: isDark
            ? 'bg-black/20'
            : 'bg-zinc-50/50',
    }), [isDark]);



    return (
        <div className="h-full p-10 flex flex-col gap-6 w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans">
            <div className={`shrink-0 rounded-[2.5rem] border flex items-center justify-between px-8 py-5 ${theme.panel}`}>

                <div className="flex-1 relative group mr-12 min-w-0">
                    <Search size={22} className="absolute left-6 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-blue-500 transition-colors" />
                    <input
                        type="text"
                        value={userIntent}
                        onChange={(e) => setUserIntent(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleMatchIntent()}
                        placeholder={t('execution.intent_placeholder')}
                        className={`w-full h-14 pl-14 pr-6 rounded-[1.25rem] border-2 text-base font-bold outline-none transition-all duration-300 focus:shadow-[0_0_0_6px_rgba(59,130,246,0.1)] focus:border-blue-500 ${theme.input} shadow-inner`}
                    />
                </div>

                <div className="shrink-0 flex items-center gap-6">
                    <div className="flex items-center gap-3 pr-6 border-r border-zinc-100 dark:border-zinc-800">
                        <button
                            onClick={handleMatchIntent}
                            disabled={isMatching || !userIntent.trim()}
                            className="flex items-center gap-3 px-6 h-14 bg-blue-600 hover:bg-blue-500 text-white rounded-[1.25rem] text-sm font-black uppercase tracking-wider transition-all active:scale-95 disabled:opacity-50 shadow-lg shadow-blue-500/20"
                        >
                            <Search size={16} strokeWidth={3} />
                            {isMatching ? t('execution.matching') : t('execution.match')}
                        </button>
                    </div>

                    <div className="flex flex-col items-end">
                        <span className="text-[9px] font-black uppercase tracking-widest text-zinc-400">{t('execution.engine_status')}</span>
                        <div className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-ping' : (psopStatus ? 'bg-emerald-500' : 'bg-zinc-300 dark:bg-zinc-700')}`} />
                            <span className={`text-[11px] font-black uppercase tracking-wider ${isRunning ? 'text-emerald-500' : 'dark:text-white'}`}>
                                {isRunning ? t('execution.running') : (psopStatus ? t('execution.completed') : t('execution.ready'))}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="flex-1 flex gap-6 min-h-0">
                {matchedWorkflows.length > 0 && (
                    <div className={`w-[320px] rounded-[2.5rem] border flex flex-col overflow-hidden ${theme.panel} shrink-0 animate-in slide-in-from-left duration-500`}>
                        <div className={`h-16 px-8 border-b flex items-center gap-3 shrink-0 ${theme.header}`}>
                            <History size={18} className="text-blue-500" />
                            <h3 className="text-lg font-black dark:text-white">{t('execution.workflow_list')}</h3>
                        </div>
                        <div className={`flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar ${theme.content}`}>
                            {matchedWorkflows.map(wf => (
                                <div 
                                    key={wf.workflow_id}
                                    onClick={() => setSelectedId(wf.workflow_id)}
                                    className={`group relative p-5 rounded-[2rem] border-2 transition-all cursor-pointer box-border
                                        ${selectedId === wf.workflow_id 
                                            ? 'bg-blue-500/10 border-blue-500/50 shadow-[0_8px_30px_rgb(59,130,246,0.1)]' 
                                            : 'bg-white/50 dark:bg-black/20 border-transparent hover:border-zinc-200 dark:hover:border-zinc-700'}
                                    `}
                                >
                                    <div className="flex flex-col gap-2 pr-12">
                                        <div className="flex items-center gap-2">
                                            <div className={`w-1.5 h-1.5 rounded-full ${selectedId === wf.workflow_id ? 'bg-blue-500 animate-pulse' : 'bg-zinc-300 dark:bg-zinc-600'}`} />
                                            <span className="text-sm font-black dark:text-white truncate uppercase tracking-tight">{wf.name}</span>
                                        </div>
                                        <span className="text-[11px] font-medium opacity-60 dark:text-zinc-400 line-clamp-2 leading-normal">
                                            {wf.description || t('execution.no_description')}
                                        </span>
                                    </div>
                                    
                                    <button 
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            if (runningId === wf.workflow_id) {
                                                stopExecution();
                                            } else {
                                                setSelectedId(wf.workflow_id);
                                                startExecution(wf.workflow_id);
                                            }
                                        }}
                                        className={`absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-2xl transition-all duration-300 shadow-xl
                                            ${runningId === wf.workflow_id 
                                                ? 'opacity-100 scale-100 bg-rose-500 shadow-rose-500/20' 
                                                : (selectedId === wf.workflow_id ? 'opacity-100 scale-100 bg-emerald-500 shadow-emerald-500/20' : 'opacity-0 scale-75 bg-blue-600 group-hover:opacity-100 group-hover:scale-100 shadow-blue-500/20')}
                                            hover:scale-110 active:scale-95 text-white z-10`}
                                    >
                                        {runningId === wf.workflow_id ? (
                                            <StopCircle size={14} fill="white" strokeWidth={3} />
                                        ) : (
                                            <Play size={14} fill="white" strokeWidth={3} />
                                        )}
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                <div className={`flex-1 flex flex-col rounded-[2.5rem] border overflow-hidden relative ${theme.panel}`}>
                    <div className={`h-16 px-8 border-b flex justify-between items-center ${theme.header}`}>
                        <div className="flex items-center gap-3">
                            <h2 className="text-lg font-black dark:text-white ">
                                {isMatching ? t('execution.processing_input') : (nodes.length > 0 ? (workflowSource === 'generated' ? t('execution.ai_planned') : t('execution.workflow_label')) : t('execution.interface_label'))}
                            </h2>
                            {workflowSource && (
                                <span className={`px-2 py-0.5 rounded-full text-[9px] font-black  ${workflowSource === 'generated' ? 'bg-purple-100 dark:bg-purple-900/40 text-purple-600' : 'bg-blue-100 dark:bg-blue-900/40 text-blue-600'}`}>
                                    {workflowSource === 'generated' ? t('execution.ai_gen') : t('execution.native')}
                                </span>
                            )}
                        </div>
                    </div>

                    <div className={`flex-1 relative ${theme.content}`}>


                        {selectedId || nodes.length > 0 ? (
                            <UnifiedWorkflow
                                mode="view"
                                isDark={isDark}
                                nodes={nodes}
                                edges={edges}
                                isLoading={(isRunning && nodes.length === 0) || isMatching}
                                loadingMessage={isMatching ? t('execution.matching') : t('execution.init')}
                                onSelectChange={handleNodeSelect}
                            />
                        ) : (
                            <div className="h-full flex flex-col items-center justify-center opacity-[0.15] dark:opacity-[0.25] text-zinc-400">
                                <Bot size={64} strokeWidth={1.5} />
                                <p className="text-xl font-black mt-4 uppercase tracking-widest">{t('execution.standby')}</p>
                            </div>
                        )}

                        {error && (
                            <div className="absolute top-6 left-1/2 -translate-x-1/2 px-8 py-4 bg-white dark:bg-rose-500/10 border border-rose-500/50 backdrop-blur-xl rounded-2xl flex items-center gap-4 text-rose-500 shadow-2xl z-[50]">
                                <AlertCircle size={20} />
                                <p className="text-sm font-bold uppercase font-mono tracking-tighter">{error}</p>
                                <button onClick={() => setError(null)} className="ml-4 opacity-50 hover:opacity-100">
                                    <Plus size={18} className="rotate-45" />
                                </button>
                            </div>
                        )}
                    </div>
                </div>

                <div className={`w-[450px] rounded-[2.5rem] border flex flex-col overflow-hidden ${theme.panel} shrink-0`}>
                    <div className={`h-16 px-8 border-b flex items-center justify-between shrink-0 ${theme.header}`}>
                        <div className="flex items-center gap-3">
                            <div className="p-2.5 bg-blue-500/10 rounded-xl">
                                <Terminal size={18} className="text-blue-500" />
                            </div>
                            <h3 className="text-lg font-black dark:text-white">{t('execution.interaction')}</h3>
                        </div>
                        {!autoScroll && (
                            <button onClick={() => setAutoScroll(true)} className="text-[10px] font-black text-blue-600 hover:text-blue-500 uppercase">
                                {t('execution.sync')}
                            </button>
                        )}
                    </div>

                    <div ref={logScrollRef} onScroll={handleScroll} className={`flex-1 overflow-y-auto p-10 space-y-8 custom-scrollbar scroll-smooth ${theme.content}`}>
                        {events.length === 0 ? (
                            <div className="h-full flex flex-col items-center justify-center opacity-[0.15] dark:opacity-[0.25] text-zinc-400">
                                <History size={64} strokeWidth={1.5} />
                                <p className="text-xl font-black mt-4 uppercase tracking-widest">{t('execution.idle')}</p>
                            </div>
                        ) : (
                            events.map((event, index) => {
                                const agentName = event.data.agent;
                                // We also try to match if the selected node's agent matches this event's agent
                                const isSelected = selectedNodeId && (nodes.find(n => n.id === selectedNodeId)?.data?.name === agentName || nodes.find(n => n.id === selectedNodeId)?.data?.agent === agentName);
                                
                                return (
                                    <LogEntry 
                                        key={`${event.timestamp}-${event.data.agent}-${index}`} 
                                        event={event} 
                                        isDark={isDark} 
                                        t={t} 
                                        isSelected={isSelected}
                                    />
                                );
                            })
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};


export default ExecutionCenter;
