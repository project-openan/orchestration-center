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
import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Play,
    StopCircle,
    Terminal,
    AlertCircle,
    Search,
    History,
    Plus,
    Bot,
    PanelLeftOpen,
    PanelLeftClose,
    ChevronDown,
    ChevronRight,
    Hash,
    Trash2,
    Clock,
    CheckCircle2,
    XCircle,
    RotateCcw,
    MessageSquare,
    BarChart3,
    SlidersHorizontal,
    X,
    FileText,
    ChevronUp,
    Loader
} from 'lucide-react';
import { usePortalContext } from '@openan/portal-sdk';
import { transformWorkflowToReactFlow, UnifiedWorkflow } from '@openan/shared-workflow';
import ExecutionStatistics from './execution_statistics/index.jsx';
import ExecutionTimeline from './timeline/index.jsx';

const parseProtobufText = (raw) => {
    if (!raw || typeof raw !== 'string') return { text: raw, metadata: null };
    const result = { text: '', metadata: {} };
    const lines = raw.split('\n');
    let inParts = false;
    let partsText = [];
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        const msgIdMatch = trimmed.match(/^message_id:\s*"(.+)"$/);
        if (msgIdMatch) { result.metadata.message_id = msgIdMatch[1]; continue; }
        const roleMatch = trimmed.match(/^role:\s*(.+)$/);
        if (roleMatch) { result.metadata.role = roleMatch[1]; continue; }
        if (trimmed.startsWith('parts')) {
            const partsInlineMatch = trimmed.match(/^parts\s*\{[^}]*text:\s*"(.+)"[^}]*\}$/);
            if (partsInlineMatch) { partsText.push(partsInlineMatch[1].replace(/\\n/g, '\n')); continue; }
            inParts = true; continue;
        }
        if (inParts && trimmed === '}') { inParts = false; continue; }
        if (inParts) {
            const textMatch = trimmed.match(/^text:\s*"(.+)"$/);
            if (textMatch) partsText.push(textMatch[1].replace(/\\n/g, '\n'));
        }
    }
    if (partsText.length > 0) {
        result.text = partsText.join('\n');
    } else {
        const textOnlyMatch = raw.match(/text:\s*"([^"]+)"/);
        if (textOnlyMatch) result.text = textOnlyMatch[1].replace(/\\n/g, '\n');
        else result.text = raw;
    }
    return result;
};

const MarkdownRenderer = React.memo(({ text }) => {
    if (!text) return null;
    const normalized = text.replace(/\\n/g, '\n');
    const lines = normalized.split('\n');
    const elements = [];
    let elementKey = 0;
    const nextElementKey = () => `md-${elementKey++}`;
    let i = 0;
    while (i < lines.length) {
        const line = lines[i];
        if (!line.trim()) { i++; elements.push(<div key={nextElementKey()} className="h-3" />); continue; }

        const h3Match = line.match(/^###\s+(.+)/);
        const h2Match = line.match(/^##\s+(.+)/);
        const h1Match = line.match(/^#\s+(.+)/);
        if (h3Match) {
            elements.push(<h3 key={nextElementKey()} className="text-base font-bold text-zinc-800 dark:text-zinc-100 mt-5 mb-2">{h3Match[1]}</h3>);
            i++; continue;
        }
        if (h2Match) {
            elements.push(<h2 key={nextElementKey()} className="text-lg font-bold text-zinc-800 dark:text-zinc-100 mt-6 mb-3 pb-1.5 border-b border-zinc-200 dark:border-zinc-700">{h2Match[1]}</h2>);
            i++; continue;
        }
        if (h1Match) {
            elements.push(<h1 key={nextElementKey()} className="text-xl font-bold text-zinc-800 dark:text-zinc-100 mt-7 mb-3">{h1Match[1]}</h1>);
            i++; continue;
        }

        const ulMatch = line.match(/^[-*]\s+(.+)/);
        if (ulMatch) {
            const items = [];
            while (i < lines.length && lines[i].match(/^[-*]\s+(.+)/)) {
                items.push(lines[i].replace(/^[-*]\s+/, ''));
                i++;
            }
            elements.push(
                <ul key={nextElementKey()} className="list-disc pl-5 my-2 space-y-1 text-zinc-700 dark:text-zinc-300">
                    {items.map((item, idx) => <li key={idx}>{renderInlineMarkdown(item)}</li>)}
                </ul>
            );
            continue;
        }

        const olMatch = line.match(/^\d+[.)]\s+(.+)/);
        if (olMatch) {
            const items = [];
            while (i < lines.length && lines[i].match(/^\d+[.)]\s+(.+)/)) {
                items.push(lines[i].replace(/^\d+[.)]\s+/, ''));
                i++;
            }
            elements.push(
                <ol key={nextElementKey()} className="list-decimal pl-5 my-2 space-y-1 text-zinc-700 dark:text-zinc-300">
                    {items.map((item, idx) => <li key={idx}>{renderInlineMarkdown(item)}</li>)}
                </ol>
            );
            continue;
        }

        const tableRowMatch = line.match(/^\|(.+)\|$/);
        if (tableRowMatch) {
            const tableLines = [];
            while (i < lines.length && lines[i].match(/^\|(.+)\|$/)) {
                tableLines.push(lines[i]);
                i++;
            }
            const isSeparator = (row) => /^\|[\s\-:]+\|[\s\-:]+\|/.test(row);
            const dataRows = tableLines.filter(r => !isSeparator(r));
            if (dataRows.length >= 1) {
                const headerCells = dataRows[0].split('|').filter(c => c.trim() !== '').map(c => c.trim());
                const bodyRows = dataRows.slice(1).map(r => r.split('|').filter(c => c.trim() !== '').map(c => c.trim()));
                elements.push(
                    <div key={nextElementKey()} className="my-3 overflow-x-auto">
                        <table className="w-full text-sm border-collapse rounded-xl overflow-hidden border border-zinc-200 dark:border-zinc-700">
                            <thead>
                                <tr className="bg-zinc-50 dark:bg-zinc-800/80">
                                    {headerCells.map((cell, idx) => (
                                        <th key={idx} className="px-4 py-2.5 text-left font-bold text-zinc-700 dark:text-zinc-200 border-b border-zinc-200 dark:border-zinc-700">{renderInlineMarkdown(cell)}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {bodyRows.map((row, rIdx) => (
                                    <tr key={rIdx} className="border-b border-zinc-100 dark:border-zinc-800/50 hover:bg-zinc-50/50 dark:hover:bg-zinc-800/30 transition-colors">
                                        {row.map((cell, cIdx) => (
                                            <td key={cIdx} className="px-4 py-2 text-zinc-600 dark:text-zinc-300">{renderInlineMarkdown(cell)}</td>
                                        ))}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                );
            }
            continue;
        }

        const hrMatch = line.match(/^[-*_]{3,}$/);
        if (hrMatch) { elements.push(<hr key={nextElementKey()} className="my-4 border-zinc-200 dark:border-zinc-700" />); i++; continue; }

        const codeBlockMatch = line.match(/^```/);
        if (codeBlockMatch) {
            i++;
            const codeLines = [];
            while (i < lines.length && !lines[i].match(/^```/)) {
                codeLines.push(lines[i]);
                i++;
            }
            i++;
            elements.push(
                <pre key={nextElementKey()} className="my-3 p-4 bg-zinc-100 dark:bg-zinc-800 rounded-xl text-xs font-mono overflow-x-auto border border-zinc-200 dark:border-zinc-700">
                    <code>{codeLines.join('\n')}</code>
                </pre>
            );
            continue;
        }

        const blockquoteMatch = line.match(/^>\s+(.+)/);
        if (blockquoteMatch) {
            const qLines = [];
            while (i < lines.length && lines[i].match(/^>\s+(.+)/)) {
                qLines.push(lines[i].replace(/^>\s+/, ''));
                i++;
            }
            elements.push(
                <blockquote key={nextElementKey()} className="my-3 pl-4 border-l-4 border-blue-400 text-zinc-600 dark:text-zinc-400 italic">
                    {qLines.map((ql, idx) => <p key={idx} className="my-1">{renderInlineMarkdown(ql)}</p>)}
                </blockquote>
            );
            continue;
        }

        elements.push(<p key={nextElementKey()} className="my-1.5 text-zinc-700 dark:text-zinc-300 leading-relaxed">{renderInlineMarkdown(line)}</p>);
        i++;
    }
    return <div className="markdown-body">{elements}</div>;
});

const renderInlineMarkdown = (text) => {
    if (!text) return '';
    const parts = [];
    let remaining = text;
    let key = 0;
    while (remaining.length > 0) {
        const boldMatch = remaining.match(/\*\*(.+?)\*\*/);
        const codeMatch = remaining.match(/`(.+?)`/);
        let match = null;
        let type = '';
        if (boldMatch && (!codeMatch || boldMatch.index <= codeMatch.index)) {
            match = boldMatch;
            type = 'bold';
        } else if (codeMatch) {
            match = codeMatch;
            type = 'code';
        }
        if (!match) {
            parts.push(<span key={key++}>{remaining}</span>);
            break;
        }
        if (match.index > 0) {
            parts.push(<span key={key++}>{remaining.slice(0, match.index)}</span>);
        }
        if (type === 'bold') {
            parts.push(<strong key={key++} className="font-bold text-zinc-900 dark:text-zinc-100">{match[1]}</strong>);
        } else {
            parts.push(<code key={key++} className="px-1.5 py-0.5 bg-zinc-100 dark:bg-zinc-800 rounded text-xs font-mono text-rose-600 dark:text-rose-400">{match[1]}</code>);
        }
        remaining = remaining.slice(match.index + match[0].length);
    }
    return parts;
};

const parseLogData = (data, type) => {
    const raw = type === 'agent_request' ? data.request : data.response;
    if (type === 'agent_request' && typeof raw === 'string') {
        const parsed = parseProtobufText(raw);
        return { parsed, type: 'protobuf' };
    }
    try {
        let parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;

        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            if (type === 'agent_request' && parsed.request) {
                parsed = parsed.request;
            } else if (type === 'agent_response' && parsed.response) {
                parsed = parsed.response;
            }
        }

        // Merge event-level metadata so findText and Show Raw can surface extension content
        if (data.metadata && typeof parsed === 'object' && parsed !== null) {
            if (!parsed.metadata) parsed.metadata = {};
            Object.assign(parsed.metadata, data.metadata);
        } else if (data.metadata && typeof parsed === 'string') {
            parsed = { response: parsed, metadata: data.metadata };
        }
        return { parsed, type: 'json' };
    } catch (e) {
        return { parsed: raw, type: 'text' };
    }
};

const LogEntry = React.memo(({ event, isDark, t, isSelected }) => {
    const [showRaw, setShowRaw] = useState(false);
    const [showMeta, setShowMeta] = useState(false);
    const { parsed, type: dataType } = useMemo(() => parseLogData(event.data, event.type), [event]);

    const isProtobuf = dataType === 'protobuf';
    const isJson = dataType === 'json';

    const displayText = useMemo(() => {
        if (!parsed) return '';
        if (isProtobuf && parsed.text) return parsed.text;
        if (typeof parsed === 'string') return parsed;
        if (typeof parsed !== 'object') return String(parsed);

        const findText = (obj, seen = new WeakSet()) => {
            if (!obj || typeof obj !== 'object') return typeof obj === 'string' ? [obj] : [];
            if (seen.has(obj)) return [];
            seen.add(obj);
            if (Array.isArray(obj)) return obj.flatMap(item => findText(item, seen));

            let results = [];
            if (obj.text && typeof obj.text === 'string') results.push(obj.text);
            if (obj.message && typeof obj.message === 'string') results.push(obj.message);
            if (obj.response && typeof obj.response === 'string') results.push(obj.response);
            if (obj.concern && typeof obj.concern === 'string') results.push(obj.concern);
            if (obj.clarification && typeof obj.clarification === 'string') results.push(obj.clarification);
            if (obj.reason && typeof obj.reason === 'string') results.push(obj.reason);

            if (results.length === 0) {
                if (obj.parts) results = results.concat(findText(obj.parts, seen));
                if (obj.artifacts) results = results.concat(findText(obj.artifacts, seen));
                if (obj.metadata && typeof obj.metadata === 'object') {
                    Object.entries(obj.metadata).forEach(([key, val]) => {
                        if (typeof val === 'string' && val.length > 10) {
                            results.push(val);
                        }
                    });
                }
            }

            if (results.length === 0) {
                Object.keys(obj).forEach(key => {
                    if (typeof obj[key] === 'object' && obj[key] !== null) {
                        results = results.concat(findText(obj[key], seen));
                    }
                });
            }

            return results;
        };

        const negotiationMarkers = /^\[NEGOTIATION_(RESOLUTION|REQUEST|CONTEXT)\]/;
        const contextJsonPattern = /^\s*\{\s*"negotiation(?:Type|Id)"\s*:/;

        const allText = Array.from(new Set(findText(parsed)))
            .filter(t => {
                if (typeof t !== 'string') return true;
                if (contextJsonPattern.test(t.trim())) return false;
                return true;
            })
            .map(t => {
                if (typeof t !== 'string') return t;
                let text = t;
                text = text.replace(/\[NEGOTIATION_CONTEXT\]\s*\n[\s\S]*$/, '').trimEnd();
                text = text.replace(/\[NEGOTIATION_RESOLUTION\]\s*\n/g, '');
                text = text.replace(/\[NEGOTIATION_REQUEST\]\s*\n/g, '');
                text = text.replace(/^The engine has reviewed your negotiation request and provides the following clarification:\s*\n/m, '');
                text = text.replace(/^-{3,}\s*\nOriginal Task:\s*\n/m, '---\n\n**Original Task:**\n\n');
                return text.trim();
            })
            .filter(t => typeof t === 'string' && t.length > 0);
        return allText.join('\n\n');
    }, [parsed, isProtobuf]);

    const isRequest = event.type === 'agent_request';
    const isNegotiation = event.type === 'negotiation_request' || event.type === 'negotiation_resolved' || event.type === 'negotiation_failed';
    const isNegotiationFailed = event.type === 'negotiation_failed';
    const accentColor = isNegotiationFailed ? 'rose' : (isNegotiation ? 'amber' : (isRequest ? 'blue' : 'purple'));
    const bgLight = isNegotiationFailed
        ? 'bg-rose-50 border-rose-200 text-rose-700 dark:bg-rose-900/20 dark:border-rose-800/50 dark:text-rose-400'
        : (isNegotiation
            ? 'bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-900/20 dark:border-amber-800/50 dark:text-amber-400'
            : (isRequest ? 'bg-blue-50 border-blue-100 text-blue-700 dark:bg-blue-900/20 dark:border-blue-800/50 dark:text-blue-400'
            : 'bg-purple-50 border-purple-100 text-purple-700 dark:bg-purple-900/20 dark:border-purple-800/50 dark:text-purple-400'));
    const dotColor = isNegotiationFailed ? 'bg-rose-500' : (isNegotiation ? 'bg-amber-500' : (isRequest ? 'bg-blue-600' : 'bg-purple-600'));

    return (
        <div 
            data-agent={event.data.agent}
            className={`relative pl-10 border-l-2 py-4 animate-in-basic transition-all duration-500 rounded-r-2xl
                ${isSelected 
                    ? 'bg-blue-500/5 border-blue-500 shadow-[inset_4px_0_0_0_#3b82f6]' 
                    : 'border-zinc-100 dark:border-zinc-800/50'}`}
        >
                                            className={`absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-2xl transition-all duration-300 shadow-xl
                                                ${runningId === wf.workflow_id 
                                                    ? 'opacity-100 scale-100 bg-rose-500 shadow-rose-500/20' 
                                                    : (selectedId === wf.workflow_id ? 'opacity-100 scale-100 bg-emerald-500 shadow-emerald-500/20' : 'opacity-0 scale-75 bg-blue-600 group-hover:opacity-100 group-hover:scale-100 shadow-blue-500/20')}
                                                hover:scale-110 active:scale-95 text-white z-10`}
            <div className="flex items-center gap-4 mb-3">
                <div className={`flex items-center gap-2 px-3.5 py-2 rounded-xl border-2 shadow-sm transition-all ${bgLight}`}>
                    {isNegotiation ? <MessageSquare size={15} className="opacity-80" /> : <Bot size={15} className="opacity-80" />}
                    <span className="text-[12.5px] font-black uppercase tracking-widest font-mono">
                        {isNegotiationFailed
                            ? t('execution.negotiation_failed')
                            : (isNegotiation
                                ? (event.type === 'negotiation_request' ? t('execution.negotiation_request') : t('execution.negotiation_resolved'))
                                : event.data.agent)}
                    </span>
                </div>
                <span className="ml-auto text-[11px] font-mono opacity-30">{new Date(event.timestamp * 1000).toLocaleTimeString()}</span>
            </div>

            {isProtobuf && parsed.metadata && Object.keys(parsed.metadata).length > 0 && (
                <div className="mb-3">
                    <button
                        onClick={() => setShowMeta(!showMeta)}
                        className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-tight text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200 transition-colors"
                    >
                        {showMeta ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                        <Hash size={10} />
                        {t('execution.request_meta')}
                    </button>
                    {showMeta && (
                        <div className="mt-2 p-3 bg-zinc-50 dark:bg-zinc-800/50 rounded-xl border border-zinc-200 dark:border-zinc-700 text-xs font-mono space-y-1">
                            {parsed.metadata.message_id && (
                                <div className="flex gap-2"><span className="text-zinc-400">message_id:</span><span className="text-zinc-600 dark:text-zinc-300 truncate">{parsed.metadata.message_id}</span></div>
                            )}
                            {parsed.metadata.role && (
                                <div className="flex gap-2"><span className="text-zinc-400">role:</span><span className="text-zinc-600 dark:text-zinc-300">{parsed.metadata.role}</span></div>
                            )}
                        </div>
                    )}
                </div>
            )}

            <div className={`group relative opacity-95 break-words font-sans text-[14.5px] leading-relaxed bg-white dark:bg-black/30 p-6 rounded-2xl border transition-all duration-300 ring-1 ring-black/5 dark:ring-white/5
                ${isSelected ? 'border-blue-500/40 shadow-blue-500/10' : 'border-zinc-100 dark:border-zinc-800/50'}
                ${showRaw ? 'ring-blue-500/30' : ''}`}>
                {showRaw ? (
                    <pre className="font-mono text-[12px] overflow-x-auto whitespace-pre-wrap max-h-[600px] custom-scrollbar text-zinc-800 dark:text-zinc-200">
                        {isJson ? JSON.stringify(parsed, null, 2) : JSON.stringify(event.data, null, 2)}
                    </pre>
                ) : (
                    <div className="text-zinc-800 dark:text-zinc-200">
                        {displayText ? (
                            <MarkdownRenderer text={displayText} />
                        ) : (
                            <span className="italic opacity-40">{t('execution.no_text')}</span>
                        )}
                    </div>
                )}

                <button
                    onClick={() => setShowRaw(!showRaw)}
                    className="mt-5 flex items-center gap-2 ml-auto text-[11px] font-black uppercase tracking-tighter text-blue-600 hover:text-blue-500 transition-colors py-1.5 px-4 bg-blue-500/5 hover:bg-blue-500/10 rounded-full border border-blue-500/10"
                >
                    {showRaw ? t('execution.show_less') : t('execution.view_detail')}
                </button>
            </div>
        </div>
    );
});

const ExecutionCenter = () => {
    const { theme: portalTheme, api } = usePortalContext();
    const { t, i18n } = useTranslation('execution-center');
    const isDark = portalTheme.isDark;

    const API_BASE = '/rest/v1/orchestrate';
    const getAgentCards = () => api.get(`${API_BASE}/agent-cards`);
    const getWorkflow = () => api.get(`${API_BASE}/workflows`);
    const getWorkflowById = (id) => api.get(`${API_BASE}/workflows/${id}`);
    const getExecutionRecords = () => api.get(`${API_BASE}/execution-records`);
    const getExecutionRecord = (executionId) => api.get(`${API_BASE}/execution-records/${executionId}`);
    const deleteExecutionRecord = (executionId) => api.delete(`${API_BASE}/execution-records/${executionId}`);
    const matchWorkflowsTopN = async (intent, topN = 3) => {
        const body = await api.post(`${API_BASE}/retrieve-topn-by-intent`, {
            user_intent: intent,
            top_n: topN
        });
        const data = body.data;
        if (!data) return [];
        return (Array.isArray(data) ? data : [data]).map(item => ({
            workflow_id: item.workflow_id,
            name: item.name,
            description: item.description,
            tags: item.tags || [],
            score: item.score
        }));
    };
    const getStartProcessStreamUrl = (psopId, userIntent = '', lang = '', targetAgent = '') => {
        const base = `${API_BASE}/execute?psop_id=${psopId}`;
        const params = [];
        if (userIntent) {
            params.push(`user_intent=${encodeURIComponent(userIntent)}`);
        }
        if (lang) {
            params.push(`lang=${encodeURIComponent(lang)}`);
        }
        if (targetAgent) {
            params.push(`target_agent=${encodeURIComponent(targetAgent)}`);
        }
        if (params.length > 0) {
            return `${base}&${params.join('&')}`;
        }
        return base;
    };
    const getDispatchStreamUrl = (intent, agentName, lang = '') => {
        const base = `${API_BASE}/dispatch`;
        const params = [];
        params.push(`intent=${encodeURIComponent(intent)}`);
        params.push(`agent_name=${encodeURIComponent(agentName)}`);
        if (lang) {
            params.push(`lang=${encodeURIComponent(lang)}`);
        }
        return `${base}?${params.join('&')}`;
    };
    const [activeSubMenu, setActiveSubMenu] = useState('execution');
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
    const [selectedExecutionId, setSelectedExecutionId] = useState(null);

    const logScrollRef = useRef(null);
    const [autoScroll, setAutoScroll] = useState(true);
    const [selectedNodeId, setSelectedNodeId] = useState(null);
    const [isPanelExpanded, setIsPanelExpanded] = useState(false);
    const [activeTab, setActiveTab] = useState('match');
    const [executionRecords, setExecutionRecords] = useState([]);
    const [isLoadingRecords, setIsLoadingRecords] = useState(false);
    const [showSelectionDialog, setShowSelectionDialog] = useState(false);
    const [workflowCandidates, setWorkflowCandidates] = useState([]);
    const [showDeleteDialog, setShowDeleteDialog] = useState(false);
    const [recordToDelete, setRecordToDelete] = useState(null);

    // Dispatch: host agent selection
    const [agentCards, setAgentCards] = useState([]);
    const [selectedAgent, setSelectedAgent] = useState('');
    const [isDispatching, setIsDispatching] = useState(false);

    // Search mode: 'fuzzy' | 'exact'
    const [searchMode, setSearchMode] = useState(() => {
        return localStorage.getItem('execution_search_mode') || 'fuzzy';
    });

    // Exact search filters
    const [exactFilters, setExactFilters] = useState({
        name: '',
        workflowId: '',
        tags: [],
        status: '',
        dateFrom: '',
        dateTo: ''
    });
    const [showFilters, setShowFilters] = useState(false);
    const [availableTags, setAvailableTags] = useState([]);
    const [showSummary, setShowSummary] = useState(false);
    const [isLeftPanelCollapsed, setIsLeftPanelCollapsed] = useState(false);

    // Save search mode to localStorage
    const handleSearchModeChange = useCallback((mode) => {
        setSearchMode(mode);
        localStorage.setItem('execution_search_mode', mode);
        setUserIntent('');
        setMatchedWorkflows([]);
        setSelectedId(null);
        setPsopStatus(null);
        setNodes([]);
        setEdges([]);
    }, []);

    // Fetch agent cards for dispatch dropdown
    useEffect(() => {
        let mounted = true;
        getAgentCards()
            .then(resp => {
                if (mounted && resp?.data) {
                    const cards = Array.isArray(resp.data) ? resp.data : [];
                    setAgentCards(cards);
                    // Auto-select Workbench Agent if available, otherwise first agent
                    if (cards.length > 0 && !selectedAgent) {
                        const workbenchAgent = cards.find(card => 
                            card.name && card.name.toLowerCase().includes('workbench')
                        );
                        setSelectedAgent(workbenchAgent ? workbenchAgent.name : cards[0].name);
                    }
                }
            })
            .catch(err => console.error('Failed to fetch agent cards:', err));
        return () => { mounted = false; };
    }, []);

    // Dispatch intent to the selected host agent via A2A-T
    const handleDispatch = useCallback(() => {
        if (!userIntent.trim() || !selectedAgent) return;

        if (eventSource) {
            eventSource.close();
            setEventSource(null);
        }

        setError(null);
        setEvents([]);
        setPsopStatus(null);
        setIsDispatching(true);
        setIsRunning(true);
        setAutoScroll(true);
        setSelectedExecutionId(null);
        setSelectedId(null);
        setWorkflowSource(null);
        setMatchedWorkflows([]);
        setNodes([]);
        setEdges([]);

        const url = getDispatchStreamUrl(userIntent, selectedAgent, i18n.language);
        const es = new EventSource(url, { withCredentials: true });

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setEvents(prev => [...prev, data]);
                console.log('[SSE event]', data.type, data.data?.step || data.data?.agent || '', JSON.stringify(data.data).slice(0, 120));

               switch (data.type) {
                    case 'start':
                        setAutoScroll(true);
                        setSelectedId('dispatch');
                        setWorkflowSource('retrieved');
                        setMatchedWorkflows([{ workflow_id: 'dispatch', name: data.data?.workflow || 'Workflow', description: userIntent || '' }]);
                        break;
                    case 'psop_update':
                        try {
                            const status = typeof data.data.psop === 'string'
                                ? JSON.parse(data.data.psop)
                                : data.data.psop;
                            setPsopStatus(status);
                        } catch (e) {
                            console.error('Failed to parse psop_update data:', e);
                        }
                        break;
                    case 'dispatch_result':
                    case 'complete':
                    case 'close':
                        setIsRunning(false);
                        setIsDispatching(false);
                        setRunningId(null);
                        es.close();
                        break;
                    case 'dispatch_error':
                    case 'error':
                        setError(data.data.error || 'Dispatch failed');
                        setIsRunning(false);
                        setIsDispatching(false);
                        setRunningId(null);
                        es.close();
                        break;
                }
            } catch (err) {
                console.error("Failed to parse dispatch event data:", err);
            }
        };

        es.onerror = () => {
            if (es.readyState === EventSource.CLOSED) {
                setError("Dispatch SSE Connection Error");
                setIsRunning(false);
                setIsDispatching(false);
                setRunningId(null);
            }
        };

        setEventSource(es);
    }, [userIntent, selectedAgent, eventSource, i18n.language]);

    // Update exact filter
    const updateFilter = useCallback((key, value) => {
        setExactFilters(prev => ({ ...prev, [key]: value }));
    }, []);

    // Toggle tag in exact filter
    const toggleTag = useCallback((tag) => {
        setExactFilters(prev => ({
            ...prev,
            tags: prev.tags.includes(tag)
                ? prev.tags.filter(t => t !== tag)
                : [...prev.tags, tag]
        }));
    }, []);

    // Clear all exact filters
    const clearFilters = useCallback(() => {
        setExactFilters({
            name: '',
            workflowId: '',
            tags: [],
            status: '',
            dateFrom: '',
            dateTo: ''
        });
        setMatchedWorkflows([]);
        setSelectedId(null);
        setPsopStatus(null);
        setNodes([]);
        setEdges([]);
    }, []);

    // Handle exact search
    const handleExactSearch = useCallback(async () => {
        try {
            setIsMatching(true);
            setNodes([]);
            setEdges([]);
            setSelectedId(null);
            setPsopStatus(null);
            setError(null);

            const res = await getWorkflow();
            if (res.status === 'success') {
                let results = (res.data || []).map(item => ({
                    workflow_id: item.workflow_id,
                    name: item.name || 'Untitled',
                    tags: item.tags || [],
                    description: item.description,
                    created_at: item.created_at,
                    status: item.status || 'unknown'
                }));

                // Apply filters
                if (exactFilters.name) {
                    const nameLower = exactFilters.name.toLowerCase();
                    results = results.filter(wf =>
                        wf.name.toLowerCase().includes(nameLower)
                    );
                }

                if (exactFilters.workflowId) {
                    const idLower = exactFilters.workflowId.toLowerCase();
                    results = results.filter(wf =>
                        wf.workflow_id.toLowerCase().includes(idLower)
                    );
                }

                if (exactFilters.tags.length > 0) {
                    results = results.filter(wf =>
                        exactFilters.tags.some(tag => wf.tags.includes(tag))
                    );
                }

                if (exactFilters.status) {
                    results = results.filter(wf => wf.status === exactFilters.status);
                }

                if (exactFilters.dateFrom) {
                    const fromDate = new Date(exactFilters.dateFrom);
                    results = results.filter(wf => new Date(wf.created_at) >= fromDate);
                }

                if (exactFilters.dateTo) {
                    const toDate = new Date(exactFilters.dateTo);
                    results = results.filter(wf => new Date(wf.created_at) <= toDate);
                }

                // Extract all unique tags for filter options
                const allTags = new Set();
                (res.data || []).forEach(item => {
                    (item.tags || []).forEach(tag => allTags.add(tag));
                });
                setAvailableTags(Array.from(allTags));

                setMatchedWorkflows(results);
                if (results.length === 1) {
                    setSelectedId(results[0].workflow_id);
                    setWorkflowSource('retrieved');
                } else if (results.length === 0) {
                    setError(t('execution.no_match'));
                }
            }
        } catch (err) {
            console.error("Exact search failed:", err);
            setError(t('execution.match_failed'));
        } finally {
            setIsMatching(false);
        }
    }, [exactFilters, t]);

    // Auto-search when filters change in exact mode
    useEffect(() => {
        if (searchMode === 'exact') {
            const hasFilters = exactFilters.name || exactFilters.workflowId ||
                exactFilters.tags.length > 0 || exactFilters.status ||
                exactFilters.dateFrom || exactFilters.dateTo;
            if (hasFilters) {
                const timer = setTimeout(() => handleExactSearch(), 300);
                return () => clearTimeout(timer);
            }
        }
    }, [exactFilters, searchMode, handleExactSearch]);

    // Load available tags on mount
    useEffect(() => {
        const loadTags = async () => {
            try {
                const res = await getWorkflow();
                if (res.status === 'success') {
                    const allTags = new Set();
                    (res.data || []).forEach(item => {
                        (item.tags || []).forEach(tag => allTags.add(tag));
                    });
                    setAvailableTags(Array.from(allTags));
                }
            } catch (err) {
                console.error("Failed to load tags:", err);
            }
        };
        loadTags();
    }, []);

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
        setPsopStatus(null);
        setMatchedWorkflows([]);
        setWorkflowSource(null);
        setError(null);

        try {
            const results = await matchWorkflowsTopN(userIntent, 3);

            if (results && results.length > 1) {
                setWorkflowCandidates(results);
                setShowSelectionDialog(true);
            } else if (results && results.length === 1) {
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

    const handleSelectCandidate = (workflowId) => {
        setShowSelectionDialog(false);
        setSelectedId(workflowId);
        setWorkflowSource('retrieved');
        setPsopStatus(null);
        setMatchedWorkflows(workflowCandidates);
        setWorkflowCandidates([]);
    };

    const loadHistoryRecords = useCallback(async () => {
        setIsLoadingRecords(true);
        try {
            const res = await getExecutionRecords();
            if (res.status === 'success') {
                setExecutionRecords(res.data || []);
            }
        } catch (err) {
            console.error("Failed to load execution records:", err);
        } finally {
            setIsLoadingRecords(false);
        }
    }, []);

    const loadHistoryDetail = useCallback(async (executionId) => {
        try {
            const res = await getExecutionRecord(executionId);
            if (res.status === 'success') {
                const record = res.data;
                setSelectedExecutionId(executionId);
                if (record.final_psop) setPsopStatus(record.final_psop);
                if (record.events && record.events.length > 0) {
                    const displayEvents = record.events.filter(e => {
                        const t = e.type;
                        return t === 'step_start' || t === 'step_complete' ||
                            t === 'task_request' || t === 'task_response' ||
                            t === 'task_status_changed' ||
                            t === 'agent_request' || t === 'agent_response' ||
                            t === 'agent_status_update' || t === 'agent_artifact_update' ||
                            t === 'negotiation_request' || t === 'negotiation_resolved' ||
                            t === 'negotiation_failed' ||
                            t === 'complete' || t === 'error' || t === 'close' ||
                            t === 'workflow_complete';
                    });
                    setEvents(displayEvents);
                }
                setIsRunning(false);
                setRunningId(null);
                setSelectedId(record.psop_id);
                setWorkflowSource('retrieved');
                setError(null);
            }
        } catch (err) {
            console.error("Failed to load execution record detail:", err);
            setError(t('execution.load_history_failed'));
        }
    }, [t]);

    const handleDeleteRecord = useCallback(async () => {
        if (!recordToDelete) return;
        try {
            await deleteExecutionRecord(recordToDelete.execution_id);
            setExecutionRecords(prev => prev.filter(r => r.execution_id !== recordToDelete.execution_id));
        } catch (err) {
            console.error("Failed to delete execution record:", err);
        } finally {
            setShowDeleteDialog(false);
            setRecordToDelete(null);
        }
    }, [recordToDelete]);

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
        } else if (selectedId && selectedId !== 'dispatch') {
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

    // Stop execution
    const stopExecution = useCallback(() => {
        if (eventSource) {
            eventSource.close();
            setEventSource(null);
        }
        setIsRunning(false);
        setRunningId(null);
    }, [eventSource]);

    // Start execution
    const startExecution = useCallback((overrideId) => {
        const idToRun = overrideId || selectedId;
        if (!idToRun) return;

        if (eventSource) {
            eventSource.close();
            setEventSource(null);
        }

        setError(null);
        setEvents([]);
        setPsopStatus(null);
        setIsRunning(true);
        setRunningId(idToRun);
        setAutoScroll(true);
        setSelectedExecutionId(null);

        const url = getStartProcessStreamUrl(idToRun, userIntent, i18n.language, selectedAgent);
        const es = new EventSource(url, { withCredentials: true });

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                setEvents(prev => [...prev, data]);

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

        es.onerror = () => {
            if (es.readyState === EventSource.CLOSED) {
                setError("SSE Connection Error");
                setIsRunning(false);
                setRunningId(null);
            }
        };

        setEventSource(es);
    }, [selectedId, userIntent, selectedAgent]);

    useEffect(() => {
        return () => {
            if (eventSource) eventSource.close();
        };
    }, [eventSource]);

    const theme = useMemo(() => ({
        panel: isDark
            ? 'bg-zinc-900/95 border-zinc-800 shadow-xl'
            : 'bg-white border-zinc-200 shadow-lg',
        header: isDark
            ? 'bg-zinc-800/30 border-zinc-800'
            : 'bg-zinc-50 border-zinc-100',
        input: isDark
            ? 'bg-zinc-800 border-zinc-700 text-white placeholder-zinc-500'
            : 'bg-zinc-50 border-zinc-200 text-zinc-900 placeholder-zinc-400',
        content: isDark
            ? 'bg-zinc-950/30'
            : 'bg-zinc-50/30',
    }), [isDark]);



    return (
        <div className="h-full flex flex-col w-full overflow-hidden">
            {/* Header */}
            <div className="shrink-0 px-8 pt-6 pb-4">
                <div className="flex items-center justify-between mb-6">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                            <Play size={18} className="text-white" fill="white" />
                        </div>
                        <div>
                            <h1 className="text-xl font-bold text-zinc-900 dark:text-white">
                                {t('nav.tabs.execution')}
                            </h1>
                            <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-0.5">
                                {activeSubMenu === 'execution' ? t('execution.sub_menu_execution') : t('execution.sub_menu_statistics')}
                            </p>
                        </div>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setActiveSubMenu('execution')}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                                activeSubMenu === 'execution'
                                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                                    : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
                            }`}
                        >
                            {t('execution.sub_menu_execution')}
                        </button>
                        <button
                            onClick={() => setActiveSubMenu('statistics')}
                            className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                                activeSubMenu === 'statistics'
                                    ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                                    : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
                            }`}
                        >
                            {t('execution.sub_menu_statistics')}
                        </button>
                    </div>
                </div>
            </div>

            <div className="flex-1 min-h-0 overflow-hidden">
                {activeSubMenu === 'execution' ? (
                    <div className="h-full px-8 pb-6 flex flex-col gap-4 w-full overflow-hidden">
                        {/* Search & Control Bar */}
                        <div className={`shrink-0 rounded-2xl border p-5 ${theme.panel}`}>

                {/* Search Mode Toggle */}
                <div className="flex items-center gap-3 mb-4">
                    <div className="flex items-center gap-1 bg-zinc-100 dark:bg-zinc-800 p-1 rounded-lg">
                        <button
                            onClick={() => handleSearchModeChange('fuzzy')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all
                                ${searchMode === 'fuzzy'
                                    ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-sm'
                                    : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'}`}
                        >
                            <Search size={13} />
                            {t('execution.search_fuzzy')}
                        </button>
                        <button
                            onClick={() => handleSearchModeChange('exact')}
                            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all
                                ${searchMode === 'exact'
                                    ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-sm'
                                    : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'}`}
                        >
                            <SlidersHorizontal size={13} />
                            {t('execution.search_exact')}
                        </button>
                    </div>
                    {searchMode === 'exact' && (
                        <button
                            onClick={() => setShowFilters(!showFilters)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all
                                ${showFilters
                                    ? 'bg-blue-600 text-white'
                                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'}`}
                        >
                            <SlidersHorizontal size={13} />
                            {t('execution.filters')}
                        </button>
                    )}
                </div>

                {/* Search Input Row */}
                <div className="flex items-center gap-3">
                    <div className="flex-1 relative group">
                        <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400 group-focus-within:text-blue-500 transition-colors" />
                        <input
                            type="text"
                            value={searchMode === 'fuzzy' ? userIntent : exactFilters.name}
                            onChange={(e) => {
                                if (searchMode === 'fuzzy') {
                                    setUserIntent(e.target.value);
                                } else {
                                    updateFilter('name', e.target.value);
                                }
                            }}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' && searchMode === 'fuzzy') {
                                    handleMatchIntent();
                                }
                            }}
                            placeholder={searchMode === 'fuzzy' ? t('execution.intent_placeholder') : t('execution.search_by_name')}
                            className={`w-full h-11 pl-11 pr-4 rounded-xl border text-sm font-medium outline-none transition-all focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 ${theme.input}`}
                        />
                    </div>

                    {/* Action Buttons */}
                    {searchMode === 'fuzzy' ? (
                        <>
                            <button
                                onClick={handleMatchIntent}
                                disabled={isMatching || !userIntent.trim()}
                                className="flex items-center gap-2 px-5 h-11 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-sm font-medium transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-blue-500/20"
                            >
                                <Search size={15} />
                                {isMatching ? t('execution.matching') : t('execution.match')}
                            </button>

                            <div className="h-8 w-px bg-zinc-200 dark:bg-zinc-700" />

                            <select
                                value={selectedAgent}
                                onChange={(e) => setSelectedAgent(e.target.value)}
                                className={`h-11 px-3 rounded-xl border text-sm font-medium outline-none transition-all focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 ${theme.input} min-w-[160px]`}
                            >
                                <option value="">{t('execution.select_agent') || 'Select Agent'}</option>
                                {agentCards.map(agent => (
                                    <option key={agent.name} value={agent.name}>
                                        {agent.name}
                                    </option>
                                ))}
                            </select>
                            <button
                                onClick={handleDispatch}
                                disabled={isDispatching || !userIntent.trim() || !selectedAgent}
                                className="flex items-center gap-2 px-5 h-11 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-sm font-medium transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-emerald-500/20"
                            >
                                <Bot size={15} />
                                {isDispatching ? (t('execution.dispatching') || 'Dispatching...') : (t('execution.dispatch') || 'Dispatch')}
                            </button>
                        </>
                    ) : (
                        <button
                            onClick={clearFilters}
                            className="flex items-center gap-2 px-5 h-11 bg-zinc-200 dark:bg-zinc-700 hover:bg-zinc-300 dark:hover:bg-zinc-600 text-zinc-700 dark:text-zinc-300 rounded-xl text-sm font-medium transition-all active:scale-95"
                        >
                            <X size={15} />
                            {t('execution.clear_filters')}
                        </button>
                    )}

                    {/* Status Indicator */}
                    <div className="flex items-center gap-2 pl-3 border-l border-zinc-200 dark:border-zinc-700">
                        <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : (psopStatus ? 'bg-emerald-500' : 'bg-zinc-300 dark:bg-zinc-600')}`} />
                        <span className={`text-xs font-medium ${isRunning ? 'text-emerald-600 dark:text-emerald-400' : 'text-zinc-500 dark:text-zinc-400'}`}>
                            {isRunning ? t('execution.running') : (psopStatus ? t('execution.completed') : t('execution.ready'))}
                        </span>
                    </div>
                </div>

                {searchMode === 'exact' && showFilters && (
                    <div className="mt-4 pt-4 border-t border-zinc-200 dark:border-zinc-700 grid grid-cols-4 gap-4 animate-in slide-in-from-top duration-300">
                        <div>
                            <label className="block text-xs font-bold text-zinc-500 dark:text-zinc-400 mb-2 uppercase">{t('execution.filter_workflow_id')}</label>
                            <input
                                type="text"
                                value={exactFilters.workflowId}
                                onChange={(e) => updateFilter('workflowId', e.target.value)}
                                placeholder={t('execution.filter_workflow_id_placeholder')}
                                className={`w-full h-10 px-4 rounded-lg border text-sm font-bold outline-none transition-all focus:border-blue-500 ${theme.input}`}
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-zinc-500 dark:text-zinc-400 mb-2 uppercase">{t('execution.filter_status')}</label>
                            <select
                                value={exactFilters.status}
                                onChange={(e) => updateFilter('status', e.target.value)}
                                className={`w-full h-10 px-4 rounded-lg border text-sm font-bold outline-none transition-all focus:border-blue-500 ${theme.input}`}
                            >
                                <option value="">{t('execution.filter_status_all')}</option>
                                <option value="success">{t('execution.filter_status_success')}</option>
                                <option value="failed">{t('execution.filter_status_failed')}</option>
                                <option value="running">{t('execution.filter_status_running')}</option>
                            </select>
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-zinc-500 dark:text-zinc-400 mb-2 uppercase">{t('execution.filter_date_from')}</label>
                            <input
                                type="date"
                                value={exactFilters.dateFrom}
                                onChange={(e) => updateFilter('dateFrom', e.target.value)}
                                className={`w-full h-10 px-4 rounded-lg border text-sm font-bold outline-none transition-all focus:border-blue-500 ${theme.input}`}
                            />
                        </div>
                        <div>
                            <label className="block text-xs font-bold text-zinc-500 dark:text-zinc-400 mb-2 uppercase">{t('execution.filter_date_to')}</label>
                            <input
                                type="date"
                                value={exactFilters.dateTo}
                                onChange={(e) => updateFilter('dateTo', e.target.value)}
                                className={`w-full h-10 px-4 rounded-lg border text-sm font-bold outline-none transition-all focus:border-blue-500 ${theme.input}`}
                            />
                        </div>
                        {availableTags.length > 0 && (
                            <div className="col-span-4">
                                <label className="block text-xs font-bold text-zinc-500 dark:text-zinc-400 mb-2 uppercase">{t('execution.filter_tags')}</label>
                                <div className="flex flex-wrap gap-2">
                                    {availableTags.map(tag => (
                                        <button
                                            key={tag}
                                            onClick={() => toggleTag(tag)}
                                            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all
                                                ${exactFilters.tags.includes(tag)
                                                    ? 'bg-blue-600 text-white'
                                                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'}`}
                                        >
                                            {tag}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Main Content Area - Three Column Layout */}
            <div className="flex-1 flex gap-4 min-h-0">
                {/* Left Panel - Workflow List */}
                {isLeftPanelCollapsed ? (
                    <button
                        onClick={() => setIsLeftPanelCollapsed(false)}
                        className={`shrink-0 w-10 rounded-xl border flex items-center justify-center ${theme.panel} hover:shadow-md transition-all`}
                        title={t('execution.expand')}
                    >
                        <ChevronRight size={16} className="text-zinc-400" />
                    </button>
                ) : (
                    <div className={`w-[280px] rounded-xl border flex flex-col overflow-hidden ${theme.panel} shrink-0`}>
                        {/* Panel Header with Tabs */}
                        <div className={`border-b ${theme.header}`}>
                            <div className="flex items-center justify-between px-2">
                                <div className="flex flex-1">
                                    <button
                                        onClick={() => setActiveTab('match')}
                                        className={`flex-1 h-12 flex items-center justify-center gap-2 text-sm font-medium transition-all border-b-2
                                            ${activeTab === 'match' 
                                                ? 'text-blue-600 dark:text-blue-400 border-blue-500' 
                                                : 'text-zinc-500 dark:text-zinc-400 border-transparent hover:text-zinc-700 dark:hover:text-zinc-300'}`}
                                    >
                                        <Search size={14} />
                                        {t('execution.match_tab')}
                                    </button>
                                    <button
                                        onClick={() => { setActiveTab('history'); loadHistoryRecords(); }}
                                        className={`flex-1 h-12 flex items-center justify-center gap-2 text-sm font-medium transition-all border-b-2
                                            ${activeTab === 'history' 
                                                ? 'text-blue-600 dark:text-blue-400 border-blue-500' 
                                                : 'text-zinc-500 dark:text-zinc-400 border-transparent hover:text-zinc-700 dark:hover:text-zinc-300'}`}
                                    >
                                        <History size={14} />
                                        {t('execution.history_tab')}
                                    </button>
                                </div>
                                <button
                                    onClick={() => setIsLeftPanelCollapsed(true)}
                                    className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                                    title={t('execution.collapse')}
                                >
                                    <PanelLeftClose size={14} className="text-zinc-400" />
                                </button>
                            </div>
                        </div>

                    {/* Match Tab Content */}
                    {activeTab === 'match' && (
                        <div className={`flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar ${theme.content}`}>
                            {matchedWorkflows.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-500 py-12">
                                    <div className="w-16 h-16 rounded-2xl bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center mb-4">
                                        <Search size={28} strokeWidth={1.5} />
                                    </div>
                                    <p className="text-sm font-medium">{t('execution.no_match_yet')}</p>
                                    <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">输入意图开始搜索</p>
                                </div>
                            ) : (
                                matchedWorkflows.map(wf => (
                                    <div 
                                        key={wf.workflow_id}
                                        onClick={() => { setSelectedId(wf.workflow_id); setWorkflowSource('retrieved'); setPsopStatus(null); }}
                                        className={`group relative p-4 rounded-xl border transition-all cursor-pointer
                                            ${selectedId === wf.workflow_id 
                                                ? 'bg-blue-50 dark:bg-blue-950/20 border-blue-300 dark:border-blue-800 shadow-sm' 
                                                : 'bg-white dark:bg-zinc-900/50 border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-sm'}
                                        `}
                                    >
                                        <div className="flex items-start gap-3 pr-10">
                                            <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                                                selectedId === wf.workflow_id 
                                                    ? 'bg-blue-500 text-white' 
                                                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400'
                                            }`}>
                                                <FileText size={14} />
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <span className="text-sm font-semibold text-zinc-900 dark:text-white truncate">{wf.name}</span>
                                                </div>
                                                <p className="text-xs text-zinc-500 dark:text-zinc-400 line-clamp-2 leading-relaxed">
                                                    {wf.description || t('execution.no_description')}
                                                </p>
                                            </div>
                                        </div>
                                        
                                        {isDispatching && wf.workflow_id === 'dispatch' ? (
                                            <div className='absolute right-3 top-1/2 -translate-y-1/2'>
                                                <Loader size={16} className='text-blue-500 animate-spin' />
                                            </div>
                                        ) : (
                                        <button 
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (runningId === wf.workflow_id) {
                                                    stopExecution();
                                                } else if (wf.workflow_id === 'dispatch') {
                                                    handleDispatch();
                                                } else {
                                                    setSelectedId(wf.workflow_id);
                                                    startExecution(wf.workflow_id);
                                                }
                                            }}
                                            className={`absolute right-3 top-1/2 -translate-y-1/2 w-8 h-8 rounded-lg flex items-center justify-center transition-all
                                                ${runningId === wf.workflow_id 
                                                    ? 'bg-rose-500 text-white shadow-md shadow-rose-500/20' 
                                                    : (selectedId === wf.workflow_id 
                                                        ? 'bg-emerald-500 text-white shadow-md shadow-emerald-500/20' 
                                                        : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 opacity-0 group-hover:opacity-100 hover:bg-zinc-200 dark:hover:bg-zinc-700')}
                                                active:scale-90`}
                                        >
                                            {runningId === wf.workflow_id ? (
                                                <StopCircle size={14} fill='white' />
                                            ) : (
                                                <Play size={14} fill='currentColor' />
                                            )}
                                        </button>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>
                    )}

                    {/* History Tab Content */}
                    {activeTab === 'history' && (
                        <div className={`flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar ${theme.content}`}>
                            {isLoadingRecords ? (
                                <div className="h-full flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-500 py-12">
                                    <Loader size={28} className="animate-spin mb-4" />
                                    <p className="text-sm font-medium">加载中...</p>
                                </div>
                            ) : executionRecords.length === 0 ? (
                                <div className="h-full flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-500 py-12">
                                    <div className="w-16 h-16 rounded-2xl bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center mb-4">
                                        <History size={28} strokeWidth={1.5} />
                                    </div>
                                    <p className="text-sm font-medium">暂无执行记录</p>
                                    <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">执行工作流后将在此保存记录</p>
                                </div>
                            ) : (
                                executionRecords.map(record => {
                                    const statusColor = record.status === 'success'
                                        ? 'bg-emerald-500'
                                        : record.status === 'failed'
                                            ? 'bg-rose-500'
                                            : record.status === 'running'
                                                ? 'bg-blue-500 animate-pulse'
                                                : 'bg-zinc-400';
                                    const statusLabel = record.status === 'success'
                                        ? '成功'
                                        : record.status === 'failed'
                                            ? '失败'
                                            : record.status === 'running'
                                                ? '运行中'
                                                : record.status || '未知';
                                    const isSelected = selectedExecutionId === record.execution_id;
                                    return (
                                        <div
                                            key={record.execution_id}
                                            onClick={() => loadHistoryDetail(record.execution_id)}
                                            className={`group relative p-3 rounded-xl border transition-all cursor-pointer
                                                ${isSelected
                                                    ? 'bg-blue-50 dark:bg-blue-950/20 border-blue-300 dark:border-blue-800 shadow-sm'
                                                    : 'bg-white dark:bg-zinc-900/50 border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 hover:shadow-sm'}
                                            `}
                                        >
                                            <div className="flex items-start gap-2.5 pr-8">
                                                <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${statusColor}`} />
                                                <div className="flex-1 min-w-0">
                                                    <div className="text-sm font-semibold text-zinc-900 dark:text-white truncate">
                                                        {record.psop_name || record.psop_id}
                                                    </div>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                                            record.status === 'success'
                                                                ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                                                                : record.status === 'failed'
                                                                    ? 'bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400'
                                                                    : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400'
                                                        }`}>
                                                            {statusLabel}
                                                        </span>
                                                        {record.started_at && (
                                                            <span className="text-[10px] text-zinc-400 dark:text-zinc-500">
                                                                {new Date(record.started_at).toLocaleString()}
                                                            </span>
                                                        )}
                                                    </div>
                                                    {record.error && (
                                                        <p className="text-[10px] text-rose-500 dark:text-rose-400 mt-1 truncate">
                                                            {record.error}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setRecordToDelete(record);
                                                    setShowDeleteDialog(true);
                                                }}
                                                className="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 text-zinc-400 hover:text-rose-500 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-all"
                                            >
                                                <Trash2 size={13} />
                                            </button>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                    )}
                </div>
                )}
                {/* Center Panel - Workflow Visualization */}
                <div className={`flex-1 flex flex-col rounded-xl border overflow-hidden ${theme.panel}`}>
                    {/* Panel Header */}
                    <div className={`h-14 px-5 border-b flex items-center justify-between ${theme.header}`}>
                        <div className="flex items-center gap-3">
                            <h2 className="text-sm font-semibold text-zinc-900 dark:text-white">
                                {isMatching ? t('execution.processing_input') : (nodes.length > 0 ? (workflowSource === 'generated' ? t('execution.ai_planned') : t('execution.workflow_label')) : t('execution.interface_label'))}
                            </h2>
                            {workflowSource && (
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-medium ${
                                    workflowSource === 'generated' 
                                        ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400' 
                                        : 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                                }`}>
                                    {workflowSource === 'generated' ? t('execution.ai_gen') : t('execution.native')}
                                </span>
                            )}
                        </div>
                    </div>

                    {/* Workflow Canvas */}
                    <div className={`flex-1 relative min-h-0 ${theme.content}`}>
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
                            <div className="h-full flex flex-col items-center justify-center text-zinc-400 dark:text-zinc-500">
                                <div className="w-20 h-20 rounded-2xl bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center mb-4">
                                    <Bot size={36} strokeWidth={1.5} />
                                </div>
                                <p className="text-base font-medium">{t('execution.standby')}</p>
                                <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">选择或搜索工作流开始执行</p>
                            </div>
                        )}

                        {/* Error Toast */}
                        {error && (
                            <div className="absolute top-4 left-1/2 -translate-x-1/2 px-5 py-3 bg-white dark:bg-zinc-900 border border-rose-200 dark:border-rose-800 backdrop-blur-xl rounded-xl flex items-center gap-3 text-rose-600 dark:text-rose-400 shadow-lg z-50 max-w-md">
                                <AlertCircle size={18} className="shrink-0" />
                                <p className="text-sm font-medium flex-1">{error}</p>
                                <button onClick={() => setError(null)} className="shrink-0 p-1 rounded-lg hover:bg-rose-100 dark:hover:bg-rose-900/30 transition-colors">
                                    <X size={14} />
                                </button>
                            </div>
                        )}
                    </div>

                    {/* Summary Section (Collapsible) */}
                    <div className={`shrink-0 border-t ${theme.header}`}>
                        <button
                            onClick={() => setShowSummary(!showSummary)}
                            className="w-full flex items-center justify-between px-5 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-800/50 transition-colors"
                        >
                            <div className="flex items-center gap-2">
                                <FileText size={15} className="text-blue-500" />
                                <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                                    {t('execution.summary_title')}
                                </span>
                            </div>
                            {showSummary
                                ? <ChevronDown size={15} className="text-zinc-400" />
                                : <ChevronUp size={15} className="text-zinc-400" />}
                        </button>
                        {showSummary && (
                            <div className="px-5 pb-4">
                                <div className={`rounded-lg border-2 border-dashed p-6 flex flex-col items-center justify-center gap-2
                                    ${isDark ? 'border-zinc-700 bg-zinc-800/30' : 'border-zinc-200 bg-zinc-50'}`}>
                                    <FileText size={24} className="text-zinc-300 dark:text-zinc-600" />
                                    <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400">
                                        {t('execution.summary_placeholder')}
                                    </p>
                                    <p className="text-xs text-zinc-400 dark:text-zinc-500">
                                        {t('execution.summary_hint')}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Panel - Interaction Log */}
                {isPanelExpanded && (
                    <div 
                        className="fixed inset-0 bg-black/30 dark:bg-black/50 z-40 transition-opacity"
                        onClick={() => setIsPanelExpanded(false)}
                    />
                )}
                <div className={`rounded-xl border flex flex-col overflow-hidden ${theme.panel} shrink-0 transition-all duration-300
                    ${isPanelExpanded 
                        ? 'w-[60vw] fixed right-0 top-0 bottom-0 z-50 shadow-2xl' 
                        : 'w-[380px]'}`}>
                    {/* Panel Header */}
                    <div className={`h-14 px-5 border-b flex items-center justify-between ${theme.header}`}>
                        <div className="flex items-center gap-2.5">
                            <div className="w-8 h-8 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                                <Terminal size={15} className="text-blue-600 dark:text-blue-400" />
                            </div>
                            <div>
                                <h3 className="text-sm font-semibold text-zinc-900 dark:text-white">{t('execution.interaction')}</h3>
                                <p className="text-[10px] text-zinc-500 dark:text-zinc-400">
                                    {events.length > 0 ? `${events.length} 条事件` : '等待执行'}
                                </p>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            {!autoScroll && (
                                <button 
                                    onClick={() => setAutoScroll(true)} 
                                    className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-500 px-2 py-1 rounded-md hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                                >
                                    {t('execution.sync')}
                                </button>
                            )}
                            <button
                                onClick={() => setIsPanelExpanded(!isPanelExpanded)}
                                className="p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                                title={isPanelExpanded ? t('execution.collapse') : t('execution.expand')}
                            >
                                {isPanelExpanded ? <PanelLeftClose size={15} className="text-zinc-500" /> : <PanelLeftOpen size={15} className="text-zinc-500" />}
                            </button>
                        </div>
                    </div>

                    {/* Log Content */}
                    <div ref={logScrollRef} onScroll={handleScroll} className={`flex-1 overflow-y-auto p-4 custom-scrollbar ${theme.content}`}>
                        <ExecutionTimeline events={events} isDark={isDark} isRunning={isRunning || isDispatching} />
                    </div>
                </div>
            </div>

            {showDeleteDialog && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-zinc-950/20 backdrop-blur-sm animate-in fade-in duration-300">
                    <div className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-[2.5rem] p-8 shadow-2xl w-full max-w-md scale-in-center animate-in zoom-in-95 duration-300">
                        <div className="flex flex-col items-center text-center">
                            <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-500 rounded-2xl mb-6">
                                <Trash2 size={32} />
                            </div>
                            <h3 className="text-xl font-black dark:text-white mb-2 uppercase tracking-tight">
                                {t('execution.delete_record_title')}
                            </h3>
                            <p className="text-zinc-500 dark:text-zinc-400 text-sm mb-8">
                                {t('execution.delete_record_confirm')}
                                <br />
                                <span className="font-bold text-zinc-900 dark:text-zinc-100 italic">"{recordToDelete?.psop_name || recordToDelete?.execution_id}"</span>
                            </p>

                            <div className="flex gap-4 w-full">
                                <button
                                    onClick={() => {
                                        setShowDeleteDialog(false);
                                        setRecordToDelete(null);
                                    }}
                                    className="flex-1 px-6 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 font-bold text-xs uppercase tracking-widest hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all"
                                >
                                    {t('common.cancel')}
                                </button>
                                <button
                                    onClick={handleDeleteRecord}
                                    className="flex-1 px-6 py-3 rounded-xl bg-red-500 text-white font-bold text-xs uppercase tracking-widest hover:bg-red-600 shadow-lg shadow-red-500/20 active:scale-95 transition-all"
                                >
                                    {t('common.delete')}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            )}

            {showSelectionDialog && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center">
                    <div className="absolute inset-0 bg-black/50 dark:bg-black/70 backdrop-blur-sm" onClick={() => setShowSelectionDialog(false)} />
                    <div className={`relative rounded-[2.5rem] border p-10 w-[560px] max-h-[80vh] overflow-y-auto custom-scrollbar shadow-2xl animate-in zoom-in-95 duration-200 ${theme.panel}`}>
                        <div className="flex flex-col gap-6">
                            <div className="text-center">
                                <h2 className="text-xl font-black dark:text-white tracking-tight">{t('execution.select_workflow')}</h2>
                                <p className="text-sm text-zinc-400 mt-2 font-medium">{t('execution.select_workflow_hint')}</p>
                            </div>
                            <div className="space-y-3">
                                {workflowCandidates.map((wf, idx) => (
                                    <button
                                        key={wf.workflow_id}
                                        onClick={() => handleSelectCandidate(wf.workflow_id)}
                                        className={`w-full text-left p-5 rounded-2xl border-2 transition-all duration-200 group hover:border-blue-500/50 hover:bg-blue-500/5 active:scale-[0.98]
                                            ${isDark ? 'bg-zinc-800/50 border-zinc-700/50 hover:bg-zinc-800' : 'bg-white border-zinc-100 hover:bg-blue-50/50'}`}
                                    >
                                        <div className="flex items-start gap-4">
                                            <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center text-sm font-black
                                                ${isDark ? 'bg-zinc-700 text-zinc-300' : 'bg-zinc-100 text-zinc-600'}`}>
                                                {idx + 1}
                                            </div>
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-2 mb-1">
                                                    <h3 className="text-sm font-black dark:text-white truncate">{wf.name}</h3>
                                                    {wf.score && (
                                                        <span className={`shrink-0 text-[10px] font-black px-2 py-0.5 rounded-full ${wf.score >= 0.8 ? 'bg-emerald-500/10 text-emerald-500' : wf.score >= 0.5 ? 'bg-amber-500/10 text-amber-500' : 'bg-zinc-500/10 text-zinc-500'}`}>
                                                            {Math.round(wf.score * 100)}%
                                                        </span>
                                                    )}
                                                </div>
                                                <p className={`text-xs leading-relaxed line-clamp-2 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                                                    {wf.description || t('execution.no_description')}
                                                </p>
                                                {wf.tags && wf.tags.length > 0 && (
                                                    <div className="flex flex-wrap gap-1.5 mt-2">
                                                        {wf.tags.map(tag => (
                                                            <span key={tag} className={`text-[10px] font-medium px-2 py-0.5 rounded-md ${isDark ? 'bg-zinc-700 text-zinc-400' : 'bg-zinc-100 text-zinc-600'}`}>{tag}</span>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                            <div className="shrink-0 self-center opacity-0 group-hover:opacity-100 transition-opacity">
                                                <ChevronRight size={20} className="text-blue-500" />
                                            </div>
                                        </div>
                                    </button>
                                ))}
                            </div>
                            <button
                                onClick={() => setShowSelectionDialog(false)}
                                className={`text-sm font-bold py-3 px-6 rounded-2xl transition-all mx-auto ${isDark ? 'text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800' : 'text-zinc-400 hover:text-zinc-600 hover:bg-zinc-100'}`}
                            >
                                {t('common.cancel')}
                            </button>
                        </div>
                    </div>
                </div>
            )}
                    </div>
                ) : (
                    <ExecutionStatistics isDark={isDark} />
                )}
            </div>
        </div>
    );
};


export default ExecutionCenter;
