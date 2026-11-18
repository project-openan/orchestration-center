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
import React, { useMemo, useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import { useTranslation } from 'react-i18next';
import { errorStepNames, formatRoleResolution, formatWorkflowError } from '../workflowErrors.js';
import remarkGfm from 'remark-gfm';
import {
    CheckCircle2,
    XCircle,
    Loader,
    Clock,
    ChevronRight,
    ChevronDown,
    Bot,
    ArrowRight,
    ArrowLeft,
    MessageSquare,
    GitBranch,
    RotateCcw,
    FileText,
    Shield,
    Bell,
} from 'lucide-react';
import {
    getExtensionLabel,
    getNegotiationPayload,
    getRequestPayload,
    getResponsePayload,
} from '../a2atEvents';

/* ──────────────────────────────────────────────────────────────────
 * Event grouping logic (Phase 3.2: groupEventsByStep)
 * ────────────────────────────────────────────────────────────────── */

function groupEventsByStep(events, workflow) {
    const steps = new Map();
    let currentStep = null;

    // Build agent -> step mapping from task_request events so that
    // agent_request/agent_response (which lack a step field) can be
    // attributed to the correct step.
    const agentToStep = new Map();

   for (const event of events) {
       const stepName = event.data?.step;
       if (event.type === 'error' || event.type === 'dispatch_error') {
           // Error task IDs belong to the original PSOP namespace. An SDK ID,
           // agent name, or the most recently active step is not a mapping.
           const targets = errorStepNames(workflow, event.data);
           if (!event.data?.code && !event.data?.task_ids && stepName) targets.push(stepName);
           for (const name of new Set(targets)) {
               const target = steps.get(name);
               if (target) {
                   target.status = 'failed';
                   target.endTime = event.timestamp;
                   target.error = event.data;
               }
           }
           continue;
       }
       if (event.type === 'step_start') {
           currentStep = stepName;
           steps.set(stepName, {
               name: stepName,
               status: 'running',
               startTime: event.timestamp,
               endTime: null,
               interactions: [],
               route: null,
               output: null,
               error: null,
               isSelfLoop: false,
           });
       }
        // Track step from task_request: also register agent->step mapping
        else if (event.type === 'task_request' && stepName && event.data?.agent) {
            agentToStep.set(event.data.agent, stepName);
            if (steps.has(stepName)) currentStep = stepName;
        }
        // Track step from event data (handles parallel steps where
        // agent interactions arrive for earlier steps after later ones start)
        else if (stepName && steps.has(stepName)) {
            currentStep = stepName;
        }
        // For events without step field (agent_request, agent_response, etc.),
        // use the agent->step mapping to find the correct step
        else if (!stepName && event.data?.agent && agentToStep.has(event.data.agent)) {
            currentStep = agentToStep.get(event.data.agent);
        }
       if (!currentStep || !steps.has(currentStep)) continue;
       const step = steps.get(currentStep);

        switch (event.type) {
            case 'agent_request':
                step.interactions.push({
                    agent: event.data.agent,
                    request: event.data,
                    response: null,
                    negotiations: [],
                    timestamp: event.timestamp,
                });
                break;
            case 'agent_response': {
                const last = step.interactions.findLast(i => i.agent === event.data.agent && !i.response);
                if (last) last.response = event.data;
                break;
            }
            case 'negotiation_request':
            case 'negotiation_resolved':
            case 'negotiation_failed': {
                const interaction = step.interactions.findLast(i => i.agent === event.data.agent);
                if (interaction) {
                    interaction.negotiations.push(event);
                }
                break;
            }
            case 'authorization_request':
                step.interactions.push({
                    agent: event.data.agent,
                    request: { authorization: true, ...event.data },
                    response: null,
                    negotiations: [],
                    timestamp: event.timestamp,
                });
                break;
            case 'notification':
                step.interactions.push({
                    agent: event.data.agent,
                    request: { notification: true, ...event.data },
                    response: null,
                    negotiations: [],
                    timestamp: event.timestamp,
                });
                break;
            case 'route_decision':
                step.route = event.data;
                break;
            case 'task_response':
                if (stepName && (event.data?.output ?? event.data?.outputs) !== undefined) {
                    const taskDesc = event.data.task || '';
                    const output = event.data.output ?? event.data.outputs;
                    const normalizedOutput = Array.isArray(output) && output.length === 1
                        ? output[0]
                        : output;
                    const existing = step.output && typeof step.output === 'object' ? step.output : {};
                    existing[taskDesc || 'output'] = normalizedOutput;
                    step.output = existing;
                }
                break;
            case 'step_complete':
                step.status = 'completed';
                step.endTime = event.timestamp;
                if (event.data?.results && !step.output) {
                    step.output = event.data.results;
                }
                break;
            case 'task_status_changed':
                if (event.data?.result && stepName) {
                    step.output = event.data.result;
                }
                break;
        }
    }

    // Mark self-loop steps: only COMPLETED steps with 0 interactions.
    // Running steps may still be waiting for agent_request events to arrive,
    // so marking them as self-loop prematurely is wrong.
    for (const step of steps.values()) {
        if (step.interactions.length === 0 && step.status === 'completed') {
            step.isSelfLoop = true;
        }
    }

    return Array.from(steps.values());
}

/* ──────────────────────────────────────────────────────────────────
 * Step status visualization (Phase 3.6)
 * ────────────────────────────────────────────────────────────────── */

const StepStatusMap = {
    pending:   { icon: Clock,        color: 'text-cm-faint',    dot: 'bg-cm-line-strong' },
    running:   { icon: Loader,       color: 'text-cm-primary',  dot: 'bg-cm-primary animate-pulse' },
    completed: { icon: CheckCircle2, color: 'text-emerald-500', dot: 'bg-emerald-500' },
    failed:    { icon: XCircle,      color: 'text-rose-500',    dot: 'bg-rose-500' },
};

function formatDuration(startTime, endTime) {
    if (!startTime) return '';
    const end = endTime || Date.now() / 1000;
    const secs = Math.max(0, Math.round(end - startTime));
    if (secs < 60) return `${secs}s`;
    return `${Math.floor(secs / 60)}m ${secs % 60}s`;
}

/* ──────────────────────────────────────────────────────────────────
 * MarkdownRenderer (react-markdown + remark-gfm)
 * ────────────────────────────────────────────────────────────────── */

const mdComponents = {
    h1: ({ children }) => <h1 className="text-[15px] font-bold text-cm-heading dark:text-zinc-100 mt-4 mb-2">{children}</h1>,
    h2: ({ children }) => <h2 className="text-[14px] font-bold text-cm-heading dark:text-zinc-100 mt-4 mb-2">{children}</h2>,
    h3: ({ children }) => <h3 className="text-[13px] font-bold text-cm-ink dark:text-zinc-200 mt-3 mb-1">{children}</h3>,
    p: ({ children }) => <p className="text-[12px] text-cm-secondary dark:text-zinc-400 leading-relaxed mb-1">{children}</p>,
    ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 my-2">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 my-2">{children}</ol>,
    li: ({ children }) => <li className="text-[12px] text-cm-secondary dark:text-zinc-400">{children}</li>,
    strong: ({ children }) => <strong className="font-bold text-cm-ink dark:text-zinc-200">{children}</strong>,
    em: ({ children }) => <em className="italic">{children}</em>,
    code: ({ className, children }) => {
        const isBlock = className?.includes('language-');
        if (isBlock) return <code className="block bg-cm-canvas dark:bg-zinc-800 rounded-[5px] p-2 text-[10px] font-mono text-cm-ink dark:text-zinc-300 overflow-x-auto">{children}</code>;
        return <code className="bg-cm-canvas dark:bg-zinc-800 rounded-[5px] px-1 py-0.5 text-[10px] font-mono text-cm-ink dark:text-zinc-300">{children}</code>;
    },
    pre: ({ children }) => <pre className="bg-cm-canvas dark:bg-zinc-800 rounded-cm-sm p-3 my-2 overflow-x-auto">{children}</pre>,
    table: ({ children }) => <table className="w-full text-[10px] border-collapse my-2">{children}</table>,
    thead: ({ children }) => <thead className="bg-cm-canvas dark:bg-zinc-800">{children}</thead>,
    th: ({ children }) => <th className="border border-cm-line dark:border-zinc-700 px-2 py-1 text-left font-semibold text-cm-ink dark:text-zinc-300">{children}</th>,
    td: ({ children }) => <td className="border border-cm-line dark:border-zinc-700 px-2 py-1 text-cm-secondary dark:text-zinc-400">{children}</td>,
    a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-cm-primary hover:underline">{children}</a>,
    hr: () => <hr className="border-cm-line-soft dark:border-zinc-700 my-3" />,
    blockquote: ({ children }) => <blockquote className="border-l-2 border-cm-line-strong dark:border-zinc-600 pl-3 my-2 text-cm-muted dark:text-zinc-400 italic">{children}</blockquote>,
};

const MarkdownRenderer = React.memo(({ text }) => {
    if (!text) return null;
    const normalized = String(text).replace(/\\n/g, '\n');
    return (
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {normalized}
        </ReactMarkdown>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * ProtocolCard - Request/Response card with improved readability
 * ────────────────────────────────────────────────────────────────── */

const ProtocolCard = React.memo(({ direction, data, timestamp, isDark }) => {
    const [showText, setShowText] = useState(false);
    const [expanded, setExpanded] = useState(false);
    if (!data) return null;

    const isRequest = direction === 'request';
    const payload = isRequest ? getRequestPayload(data) : getResponsePayload(data);
    const raw = payload.content;
    const text = payload.text;
    const metadata = payload.metadata;
    const hasMetadata = Object.keys(metadata).length > 0;
    const hasA2atContent = payload.hasA2atContent;
    const state = data.state || data.task_state;
    const hasAuth = data.authorization;
    const hasNotif = data.notification;

    const icon = hasAuth ? <Shield size={12} className="text-amber-500" />
        : hasNotif ? <Bell size={12} className="text-cm-primary" />
        : isRequest ? <ArrowRight size={12} className="text-cm-primary" />
        : <ArrowLeft size={12} className="text-emerald-500" />;

    const label = hasAuth ? 'AUTH' : hasNotif ? 'NOTIF' : isRequest ? 'REQUEST' : 'RESPONSE';
    const bgClass = isRequest
        ? 'bg-cm-primary-soft dark:bg-zinc-800/40 border-cm-line dark:border-zinc-700'
        : 'bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800';
    const ts = timestamp ? new Date(timestamp * 1000).toLocaleTimeString('en-GB') : '';

    return (
        <div className={`rounded-cm-sm border ${bgClass} overflow-hidden`}>
            {/* Card Header (clickable) */}
            <div
                className="flex items-center gap-2 px-3 py-2 border-b border-inherit bg-white/70 dark:bg-zinc-900/40 cursor-pointer select-none hover:bg-white dark:hover:bg-zinc-900/60 transition-colors"
                onClick={() => setExpanded(!expanded)}
            >
                {icon}
                <span className="text-[11px] font-semibold text-cm-secondary dark:text-zinc-400">{label}</span>
                {ts && <span className="text-[11px] text-cm-faint font-mono">{ts}</span>}
                {state && (
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-[5px] ${
                        state.includes('COMPLETED') ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : state.includes('FAILED') ? 'bg-rose-50 text-rose-600 dark:bg-rose-900/40 dark:text-rose-300'
                        : 'bg-cm-primary-faint text-cm-accent dark:bg-zinc-800 dark:text-zinc-300'
                    }`}>
                        {state.replace('TASK_STATE_', '')}
                    </span>
                )}
                <span className="ml-auto text-cm-faint dark:text-zinc-500">
                    {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                </span>
            </div>

            {/* Expandable Content */}
            {expanded && (
                <>
                    {/* A2A-T Headers */}
                    {(() => {
                        const headerKeys = Object.keys(metadata).filter(k => k.includes('tmforum.org') || k.includes('a2aproject'));
                        if (headerKeys.length === 0) return null;
                        return (
                            <div className="px-3 py-2 border-b border-inherit bg-cm-canvas/60 dark:bg-zinc-800/30">
                            <div className="text-[10px] font-semibold text-cm-muted dark:text-zinc-400 mb-1">A2A-Extensions</div>
                                <div className="flex flex-wrap gap-1">
                                    {headerKeys.map((k, idx) => (
                                        <span key={idx} className="text-[10px] font-mono px-1.5 py-0.5 rounded-[5px] bg-cm-canvas border border-cm-line text-cm-muted dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-300">
                                            {k.split('/').pop()}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        );
                    })()}

                    {/* Metadata (primary, expanded by default) */}
                    {hasMetadata && (
                        <div className="px-3 py-2 bg-white/80 dark:bg-zinc-900/40 overflow-y-auto custom-scrollbar">
                            <div className="space-y-2">
                                {Object.entries(metadata).map(([key, val], idx) => (
                                    <div key={idx} className="text-[11px]">
                                        <span className="font-semibold text-cm-secondary dark:text-zinc-400 break-all">{getExtensionLabel(key)}:</span>
                                        <div className="ml-2 mt-0.5">
                                            <MarkdownRenderer text={typeof val === 'string' ? val : JSON.stringify(val, null, 2)} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Text Part (secondary, collapsed by default) */}
                    {text && !hasA2atContent && (
                        <div className="px-3 py-2 border-t border-inherit bg-cm-canvas/40 dark:bg-zinc-800/20">
                            <button
                                onClick={(e) => { e.stopPropagation(); setShowText(!showText); }}
                                className="flex items-center gap-1 text-[11px] font-medium text-cm-muted hover:text-cm-primary dark:text-zinc-400 dark:hover:text-zinc-200 transition-colors"
                            >
                                {showText ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                                Text Part
                            </button>
                            {showText && (
                                <div className="mt-2 overflow-y-auto custom-scrollbar">
                                    <MarkdownRenderer text={text} />
                                </div>
                            )}
                        </div>
                    )}
                </>
            )}
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * AgentInteraction - Agent call card with improved layout
 * ────────────────────────────────────────────────────────────────── */

const AgentInteraction = React.memo(({ interaction, isDark }) => {
    const agent = interaction.agent || 'Unknown';
    const [negExpanded, setNegExpanded] = useState(false);
    return (
        <div className="rounded-cm-sm border border-cm-line dark:border-zinc-700 bg-white dark:bg-zinc-800/30 overflow-hidden">
            {/* Agent Header */}
            <div className="flex items-center gap-2.5 px-3 py-2 border-b border-cm-line-soft dark:border-zinc-700 bg-cm-canvas/70 dark:bg-zinc-900/30">
                <div className="w-6 h-6 rounded-[5px] bg-cm-primary-faint dark:bg-zinc-800 flex items-center justify-center shrink-0">
                    <Bot size={12} className="text-cm-primary" />
                </div>
                <span className="text-[12px] font-semibold text-cm-ink dark:text-zinc-200 truncate">{agent}</span>
            </div>

            {/* Interaction Content */}
            <div className="p-3 space-y-2">
                {interaction.request && (
                    <ProtocolCard direction="request" data={interaction} timestamp={interaction.timestamp} isDark={isDark} />
                )}
                {interaction.response && (
                    <ProtocolCard direction="response" data={interaction} timestamp={interaction.timestamp} isDark={isDark} />
                )}
                {interaction.negotiations && interaction.negotiations.length > 0 && (
                    <div className="rounded-cm-sm border border-amber-200 dark:border-amber-800 bg-amber-50/60 dark:bg-amber-950/20 p-3">
                        <div
                            className="flex items-center gap-1.5 text-[11px] font-semibold text-amber-600 dark:text-amber-400 cursor-pointer select-none"
                            onClick={() => setNegExpanded(!negExpanded)}
                        >
                            <MessageSquare size={11} />
                            协商 ({interaction.negotiations.length} 轮)
                            <span className="ml-auto text-amber-400">
                                {negExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                            </span>
                        </div>
                        {negExpanded && (
                            <div className="space-y-3 mt-2">
                                {interaction.negotiations.map((neg, idx) => {
                                    const label = neg.type.replace('negotiation_', '');
                                    const negotiation = getNegotiationPayload(neg);
                                    const content = negotiation.text;
                                    const labelColor = label === 'request' ? 'text-cm-primary dark:text-blue-400'
                                        : label === 'resolved' ? 'text-emerald-600 dark:text-emerald-400'
                                        : label === 'failed' ? 'text-rose-600 dark:text-rose-400'
                                        : 'text-amber-600 dark:text-amber-400';
                                    const borderColor = label === 'request' ? 'border-[#A9C8FB] dark:border-blue-700'
                                        : label === 'resolved' ? 'border-emerald-300 dark:border-emerald-700'
                                        : label === 'failed' ? 'border-rose-300 dark:border-rose-700'
                                        : 'border-amber-300 dark:border-amber-700';
                                    return (
                                        <div key={idx} className={`pl-3 border-l-2 ${borderColor}`}>
                                            <div className={`text-[10px] font-bold uppercase mb-1 ${labelColor}`}>{label}</div>
                                            <div className="overflow-y-auto custom-scrollbar">
                                                {content ? (
                                                    <MarkdownRenderer text={content} />
                                                ) : (
                                                    <span className="text-[10px] italic text-cm-faint">No Negotiation-T content</span>
                                                )}
                                                {Object.entries(negotiation.metadata).length > 0 && (
                                                    <div className="mt-2 space-y-1">
                                                        {Object.entries(negotiation.metadata).map(([key, value], metaIdx) => (
                                                            <div key={metaIdx} className="text-[10px]">
                                                                <span className="font-semibold text-cm-muted dark:text-zinc-400 break-all">
                                                                    {getExtensionLabel(key)}:
                                                                </span>
                                                                <div className="ml-2 mt-0.5">
                                                                    <MarkdownRenderer text={typeof value === 'string' ? value : JSON.stringify(value, null, 2)} />
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * SelfLoopCard (Phase 3.4)
 * ────────────────────────────────────────────────────────────────── */

const SelfLoopCard = React.memo(({ step, isDark }) => {
    const [expanded, setExpanded] = useState(false);
    const renderOutput = () => {
        if (!step.output) return null;
        if (typeof step.output === 'string') {
            return <MarkdownRenderer text={step.output} />;
        }
        return Object.entries(step.output).map(([taskDesc, output], idx) => (
            <div key={idx} className="mb-3 last:mb-0">
                <div className="text-[10px] font-semibold text-cm-accent dark:text-blue-300 mb-1">{taskDesc}</div>
                <MarkdownRenderer text={typeof output === 'string' ? output : JSON.stringify(output, null, 2)} />
            </div>
        ));
    };
    return (
        <div className="flex flex-col gap-2 pl-3 border-l-2 border-[#A9C8FB] dark:border-blue-800 ml-2">
            <div
                className="flex items-center gap-2 cursor-pointer select-none"
                onClick={() => step.output && setExpanded(!expanded)}
            >
                <div className="w-6 h-6 rounded-[5px] bg-cm-primary-faint dark:bg-zinc-800 flex items-center justify-center shrink-0">
                    <RotateCcw size={12} className="text-cm-primary" />
                </div>
                <span className="text-[12px] font-bold text-cm-primary dark:text-blue-300">Self-Loop (Local Processing)</span>
                {step.output && (
                    <span className="ml-auto text-cm-faint dark:text-zinc-500">
                        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                    </span>
                )}
            </div>
            {expanded && step.output && (
                <div className="rounded-cm-sm bg-cm-primary-soft dark:bg-zinc-800/40 border border-cm-line dark:border-zinc-700 p-3 overflow-y-auto custom-scrollbar">
                    {renderOutput()}
                </div>
            )}
            {step.status === 'running' && !step.output && (
                <div className="flex items-center gap-2 text-[12px] text-cm-primary">
                    <Loader size={12} className="animate-spin" />
                    <span>Processing...</span>
                </div>
            )}
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * RouteDecisionCard (Phase 3.6 inner)
 * ────────────────────────────────────────────────────────────────── */

const RouteDecisionCard = React.memo(({ data }) => {
    if (!data) return null;
    return (
        <div className="flex items-center gap-2 rounded-cm-sm border border-cm-line dark:border-zinc-700 bg-cm-canvas/70 dark:bg-zinc-900/40 p-2 ml-4">
            <GitBranch size={14} className="text-cm-faint" />
            <span className="text-[10px] font-bold text-cm-secondary dark:text-zinc-400">
                Route: <span className="text-cm-ink dark:text-zinc-200">{data.step || ''}</span>
                <ChevronRight size={10} className="inline mx-1" />
                <span className="text-cm-primary dark:text-blue-400">{data.next || data.next_step || ''}</span>
            </span>
            {data.reason && <span className="text-[10px] text-cm-faint ml-2">{data.reason}</span>}
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * StepPhase - Step container with improved visual hierarchy
 * ────────────────────────────────────────────────────────────────── */

const StepPhase = React.memo(({ step, isDark }) => {
    const statusInfo = StepStatusMap[step.status] || StepStatusMap.pending;
    const StatusIcon = statusInfo.icon;
    const duration = formatDuration(step.startTime, step.endTime);
    const [collapsed, setCollapsed] = useState(step.status === 'completed');

    const interactionCount = step.interactions.length;
    const hasContent = step.isSelfLoop || interactionCount > 0 || step.route || step.output || step.error;

    return (
        <div className="rounded-cm border border-cm-line dark:border-zinc-700 bg-white dark:bg-zinc-900/40 overflow-hidden">
            {/* Step Header (clickable) */}
            <div
                className={`px-4 py-3 cursor-pointer select-none transition-colors hover:bg-cm-canvas dark:hover:bg-zinc-800/50 ${
                    step.status === 'running' ? 'bg-cm-primary-soft dark:bg-zinc-800/60' : 'bg-white dark:bg-transparent'
                } ${!collapsed ? 'border-b border-cm-line-soft dark:border-zinc-800' : ''}`}
                onClick={() => hasContent && setCollapsed(!collapsed)}
            >
                <div className="flex items-center gap-2.5">
                    <div className={`w-7 h-7 rounded-cm-sm flex items-center justify-center ${
                        step.status === 'running' ? 'bg-cm-primary-faint dark:bg-zinc-800' :
                        step.status === 'completed' ? 'bg-emerald-50 dark:bg-emerald-900/30' :
                        step.status === 'failed' ? 'bg-rose-50 dark:bg-rose-900/30' :
                        'bg-cm-canvas dark:bg-zinc-800'
                    }`}>
                        <StatusIcon size={14} className={statusInfo.color + (step.status === 'running' ? ' animate-spin' : '')} />
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                            <span className="text-[13px] font-semibold text-cm-heading dark:text-zinc-100 truncate">{step.name}</span>
                            {step.isSelfLoop && (
                                <span className="cm-chip tracking-wide dark:bg-zinc-800 dark:text-blue-300">
                                    SELF-LOOP
                                </span>
                            )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                            <span className={`text-[11px] font-medium ${statusInfo.color}`}>
                                {step.status === 'running' ? '执行中' : step.status === 'completed' ? '已完成' : step.status === 'failed' ? '失败' : '等待中'}
                            </span>
                            {duration && <span className="text-[11px] text-cm-faint dark:text-zinc-500">· {duration}</span>}
                            {interactionCount > 0 && <span className="text-[11px] text-cm-faint dark:text-zinc-500">· {interactionCount} 次交互</span>}
                        </div>
                    </div>
                    {hasContent && (
                        <div className="text-cm-faint transition-transform duration-200">
                            {collapsed ? <ChevronRight size={16} /> : <ChevronDown size={16} />}
                        </div>
                    )}
                </div>
            </div>

            {/* Step Content (collapsible) */}
            {!collapsed && (
                <div className="p-3.5 space-y-2.5">
                    {step.isSelfLoop ? (
                        <SelfLoopCard step={step} isDark={isDark} />
                    ) : (
                        step.interactions.map((interaction, idx) => (
                            <AgentInteraction key={idx} interaction={interaction} isDark={isDark} />
                        ))
                    )}
                    {step.route && <RouteDecisionCard data={step.route} />}

                    {step.error && (
                        <div className="rounded-cm-sm bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-800 p-3">
                            <div className="flex items-start gap-2">
                                <XCircle size={14} className="text-rose-500 shrink-0 mt-0.5" />
                                <span className="text-[12px] font-medium text-rose-600 dark:text-rose-400">
                                    {formatWorkflowError(step.error)}
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * WorkflowHeader - Compact workflow status card
 * ────────────────────────────────────────────────────────────────── */

const WorkflowHeader = React.memo(({ events, steps, isRunning }) => {
    const startEvent = events.find(e => e.type === 'start');
    const completeEvent = events.find(e => e.type === 'complete');
    const errorEvent = events.find(e => e.type === 'error' || e.type === 'dispatch_error');
    const wfName = startEvent?.data?.workflow || '';
    const totalSteps = startEvent?.data?.steps || 0;
    const completedSteps = steps.filter(s => s.status === 'completed').length;
    const failedSteps = steps.filter(s => s.status === 'failed').length;
    const startTime = startEvent?.timestamp;
    const endTime = completeEvent?.timestamp || errorEvent?.timestamp;
    const duration = formatDuration(startTime, endTime);
    const overallStatus = errorEvent ? 'failed' : completeEvent ? 'completed' : isRunning ? 'running' : 'pending';
    const statusInfo = StepStatusMap[overallStatus] || StepStatusMap.pending;
    const StatusIcon = statusInfo.icon;
    const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

    return (
        <div className="rounded-cm border border-cm-line dark:border-zinc-700 bg-white dark:bg-zinc-900/40 p-4">
            <div className="flex items-center gap-3 mb-3">
                <div className={`w-9 h-9 rounded-cm flex items-center justify-center ${
                    overallStatus === 'failed' ? 'bg-rose-50 dark:bg-rose-900/30' :
                    overallStatus === 'completed' ? 'bg-emerald-50 dark:bg-emerald-900/30' :
                    overallStatus === 'running' ? 'bg-cm-primary-faint dark:bg-zinc-800' :
                    'bg-cm-canvas dark:bg-zinc-800'
                }`}>
                    <StatusIcon size={18} className={statusInfo.color + (overallStatus === 'running' ? ' animate-spin' : '')} />
                </div>
                <div className="flex-1 min-w-0">
                    <div className="text-[14px] font-bold text-cm-heading dark:text-zinc-100 truncate">{wfName || 'Workflow Execution'}</div>
                    <div className="flex items-center gap-2 mt-0.5">
                        <span className={`text-[12px] font-medium ${statusInfo.color}`}>
                            {overallStatus === 'running' ? '执行中' : overallStatus === 'completed' ? '已完成' : overallStatus === 'failed' ? '失败' : '等待中'}
                        </span>
                        {totalSteps > 0 && (
                            <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                                · {completedSteps}/{totalSteps} 步骤
                                {failedSteps > 0 && <span className="text-rose-500"> ({failedSteps} 失败)</span>}
                            </span>
                        )}
                        {duration && <span className="text-[11px] text-cm-faint dark:text-zinc-500">· {duration}</span>}
                    </div>
                </div>
            </div>
            {totalSteps > 0 && (
                <div className="w-full h-1 rounded-[2px] bg-cm-line-soft dark:bg-zinc-800 overflow-hidden">
                    <div
                        className={`h-full rounded-[2px] transition-all duration-500 ${
                            overallStatus === 'failed' ? 'bg-rose-500' : overallStatus === 'completed' ? 'bg-emerald-500' : 'bg-cm-primary'
                        }`}
                        style={{ width: `${progress}%` }}
                    />
                </div>
            )}
        </div>
    );
});

/* ──────────────────────────────────────────────────────────────────
 * ExecutionTimeline - Main timeline container
 * ────────────────────────────────────────────────────────────────── */

const ExecutionTimeline = React.memo(({ events, isDark, isRunning, workflow }) => {
    const { t } = useTranslation();
    const steps = useMemo(() => {
        const result = groupEventsByStep(events, workflow);
        if (result.length > 0) {
            console.log('[Timeline] steps:', result.map(s => ({ name: s.name, status: s.status, selfLoop: s.isSelfLoop, interactions: s.interactions.length })));
        }
        return result;
    }, [events, workflow]);

    if (events.length === 0) {
        return (
            <div className="h-full flex flex-col items-center justify-center text-cm-faint dark:text-zinc-500 py-16">
                <div className="w-14 h-14 rounded-cm bg-cm-primary-faint dark:bg-zinc-800 flex items-center justify-center mb-3 text-cm-primary dark:text-zinc-400">
                    <Clock size={24} strokeWidth={1.5} />
                </div>
                <p className="text-[13px] font-medium text-cm-muted dark:text-zinc-400">等待执行</p>
                <p className="text-[11px] text-cm-faint dark:text-zinc-500 mt-1">执行工作流后将在此显示进度</p>
            </div>
        );
    }

    return (
        <div className="space-y-3">
            <WorkflowHeader events={events} steps={steps} isRunning={isRunning} />
            {events.filter(event => ['resolution', 'error', 'dispatch_error'].includes(event.type)).map((event, index) => (
                <section key={index} role={event.type === 'resolution' ? 'status' : 'alert'}
                    className={`rounded-cm border p-4 ${
                        event.type === 'resolution'
                            ? 'border-cm-line bg-cm-primary-soft dark:border-zinc-700 dark:bg-zinc-800/40'
                            : 'border-rose-200 bg-rose-50 dark:border-rose-800 dark:bg-rose-950/20 text-rose-600 dark:text-rose-400'
                    }`}>
                    {event.type === 'resolution' && <h3 className="text-[13px] font-bold text-cm-heading dark:text-zinc-100 mb-2">{t('execution.roleResolution')}</h3>}
                    <p className="text-[12px] whitespace-pre-wrap break-words">{event.type === 'resolution'
                        ? formatRoleResolution(event.data) : formatWorkflowError(event.data)}</p>
                </section>
            ))}
            <div className="space-y-3">
                {steps.map((step, idx) => (
                    <StepPhase key={idx} step={step} isDark={isDark} />
                ))}
            </div>

        </div>
    );
});

export default ExecutionTimeline;
