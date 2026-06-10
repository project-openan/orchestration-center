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
import React, { memo, useMemo } from 'react';
import { Handle, Position, useConnection } from '@xyflow/react';
import { useTranslation } from 'react-i18next';

const AGENT_COLORS = [
    { light: 'bg-blue-100 text-blue-700', dark: 'bg-blue-500/20 text-blue-300', bar: 'bg-blue-500' },
    { light: 'bg-purple-100 text-purple-700', dark: 'bg-purple-500/20 text-purple-300', bar: 'bg-purple-500' },
    { light: 'bg-teal-100 text-teal-700', dark: 'bg-teal-500/20 text-teal-300', bar: 'bg-teal-500' },
    { light: 'bg-orange-100 text-orange-700', dark: 'bg-orange-500/20 text-orange-300', bar: 'bg-orange-500' },
    { light: 'bg-pink-100 text-pink-700', dark: 'bg-pink-500/20 text-pink-300', bar: 'bg-pink-500' },
    { light: 'bg-emerald-100 text-emerald-700', dark: 'bg-emerald-500/20 text-emerald-300', bar: 'bg-emerald-500' },
    { light: 'bg-indigo-100 text-indigo-700', dark: 'bg-indigo-500/20 text-indigo-300', bar: 'bg-indigo-500' },
    { light: 'bg-rose-100 text-rose-700', dark: 'bg-rose-500/20 text-rose-300', bar: 'bg-rose-500' },
];

const getAgentTheme = (agentName) => {
    if (!agentName || agentName === 'Agent') {
        return { light: 'bg-slate-100 text-slate-500', dark: 'bg-slate-800 text-slate-400', bar: 'bg-slate-400' };
    }
    let hash = 0;
    for (let i = 0; i < agentName.length; i++) {
        hash = agentName.charCodeAt(i) + ((hash << 5) - hash);
    }
    const index = Math.abs(hash) % AGENT_COLORS.length;
    return AGENT_COLORS[index];
};

const StepTypeIcon = ({ isAnySuccess, isDark }) => {
    if (isAnySuccess) {
        return (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="flex-shrink-0" title="AnySuccess: step succeeds if any subtask succeeds">
                <circle cx="7" cy="2.5" r="2" fill="currentColor" opacity="0.85" />
                <line x1="7" y1="4.5" x2="3" y2="12" stroke="currentColor" strokeWidth="1.2" opacity="0.25" strokeLinecap="round" />
                <line x1="7" y1="4.5" x2="11" y2="12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
        );
    }
    return (
        <svg width="12" height="14" viewBox="0 0 12 14" fill="none" className="flex-shrink-0" title="AllSuccess: step succeeds only if all subtasks succeed">
            <rect x="4.5" y="1" width="3" height="2.5" rx="1.2" fill="currentColor" opacity="0.35" />
            <rect x="3.5" y="5.75" width="5" height="2.5" rx="1.2" fill="currentColor" opacity="0.6" />
            <rect x="2" y="10.5" width="8" height="2.5" rx="1.2" fill="currentColor" />
        </svg>
    );
};

const AgentNode = ({ data, selected }) => {
    const connection = useConnection();
    const { t } = useTranslation();
    const isConnecting = connection.inProgress;

    const isDark = data.isDark || false;
    const status = data.status || 'pending';
    const stepName = data.label || 'Step';
    const stepType = data.type || 'AllSuccess';
    const isAnySuccess = stepType === 'AnySuccess';
    const subtasks = data.subtasks || [];
    const selectedSubtaskIndex = data.selectedSubtaskIndex;

    const theme = {
        bg: isDark ? 'bg-zinc-900/95' : 'bg-white',
        border: isDark ? 'border-zinc-700/50' : 'border-slate-200',
        textMain: isDark ? 'text-zinc-100' : 'text-slate-800',
        textSub: isDark ? 'text-zinc-400' : 'text-slate-500',
        shadow: selected
            ? (isDark ? 'shadow-[0_0_20px_rgba(59,130,246,0.15)]' : 'shadow-xl shadow-blue-500/10')
            : 'shadow-sm hover:shadow-md'
    };

    const stepTypeColor = isAnySuccess
        ? (isDark ? 'text-amber-400' : 'text-amber-600')
        : (isDark ? 'text-blue-400' : 'text-blue-600');

    const handleBaseStyle = `
        !w-[10px] !h-[10px] !bg-blue-500 border-2 border-white dark:border-zinc-800
        transition-all duration-300 ease-out cursor-crosshair
        hover:!w-[18px] hover:!h-[18px] hover:shadow-lg
        z-[110]
        
        [&.react-flow__handle-connecting]:ring-4 [&.react-flow__handle-connecting]:ring-blue-500/20
        
        after:content-[''] after:absolute after:top-1/2 after:left-1/2 after:-translate-x-1/2 after:-translate-y-1/2 
        after:w-[80px] after:h-[80px] after:bg-transparent
    `;

    const targetHandleBaseClasses = `
        !w-0 !h-0 !bg-transparent !border-0 !absolute !transform-none
        z-[100]
        after:content-[''] after:absolute after:bg-transparent
        ${isConnecting ? 'after:pointer-events-auto' : 'after:pointer-events-none'}
    `;

    const getStatusColor = (s) => {
        const normalized = (s || '').toLowerCase();
        if (normalized === 'running' || normalized === 'executing' || normalized === 'current') return 'bg-blue-500';
        if (normalized === 'success' || normalized === 'completed' || normalized === 'executed') return 'bg-emerald-500';
        if (normalized === 'failed' || normalized === 'error') return 'bg-rose-500';
        return isDark ? 'bg-zinc-700' : 'bg-slate-200';
    };

    return (
        <div
            className={`
                touch-none relative min-w-[200px] max-w-[400px] rounded-xl border transition-all duration-500
                ${theme.bg} ${theme.border} ${theme.shadow} ${theme.textMain}
                backdrop-blur-sm overflow-hidden
                ${selected ? 'ring-2 ring-blue-500/50 ring-offset-2 ' + (isDark ? 'ring-offset-zinc-950' : 'ring-offset-white') : ''}
            `}
        >
            <div className={`h-[4px] w-full transition-colors duration-500 ${isAnySuccess ? 'bg-amber-500/70' : 'bg-blue-500/50'}`} />

            <div className="px-4 py-3 flex flex-col gap-2">
                {/* Step Header: icon + name + status */}
                <div className="flex items-center gap-2">
                    <span className={stepTypeColor}>
                        <StepTypeIcon isAnySuccess={isAnySuccess} isDark={isDark} />
                    </span>
                    <h3 className="text-[14px] font-bold leading-[1.15] break-words whitespace-normal flex-1">
                        {stepName}
                    </h3>
                    <div className="relative flex h-2.5 w-2.5 flex-shrink-0">
                        {(status === 'running' || status === 'current') && (
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                        )}
                        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 transition-colors duration-300 ${getStatusColor(status)}`}></span>
                    </div>
                </div>

                {/* Subtasks List */}
                <div className="flex flex-col gap-1.5">
                    {subtasks.map((task, idx) => {
                        const isSubtaskSelected = selectedSubtaskIndex === idx;
                        const agentTheme = getAgentTheme(task.agent);
                        return (
                            <button
                                key={idx}
                                type="button"
                                onClick={(event) => {
                                    event.stopPropagation();
                                    data.onSubtaskClick?.(idx, task);
                                }}
                                className={`
                                    group/task relative p-2 px-3 rounded-lg border flex flex-col gap-0.5 transition-all text-left
                                    ${isSubtaskSelected ? 'ring-2 ring-blue-500/50 border-blue-400/60' : ''}
                                    ${isDark ? 'bg-zinc-800/40 border-zinc-700/30 hover:bg-zinc-800' : 'bg-slate-50/50 border-slate-100 hover:bg-slate-100'}
                                `}
                            >
                                <div className="flex justify-between items-center">
                                    <span className={`text-[9px] font-bold uppercase tracking-tight opacity-80 break-words whitespace-normal ${isDark ? agentTheme.dark : agentTheme.light}`}>
                                        {task.agent || 'Agent'}
                                    </span>
                                    <div className={`h-1.5 w-1.5 rounded-full ${getStatusColor(task.status)} opacity-60`} />
                                </div>
                                <div className={`text-[11px] font-medium leading-[1.15] break-words whitespace-normal ${isDark ? 'text-zinc-300' : 'text-slate-700'}`}>
                                    {task.skill || t('node_label.no_skill')}
                                </div>
                            </button>
                        );
                    })}
                    {subtasks.length === 0 && (
                        <div className={`text-[10px] italic px-2 py-1 ${theme.textSub} opacity-50`}>
                            {t('node_label.no_subtasks')}
                        </div>
                    )}
                </div>
            </div>

            {/* Target Handle */}
            <Handle type="target" position={Position.Left} id="t-left" style={{ top: '50%', left: 0 }} className={`${targetHandleBaseClasses} after:w-[500px] after:h-[800px] after:left-[250px] after:top-0 after:-translate-x-1/2 after:-translate-y-1/2`} />

            {/* Source Handle */}
            <Handle type="source" position={Position.Right} id="s-right" style={{ top: '50%' }} className={handleBaseStyle} />
        </div>
    );
};

export default memo(AgentNode);
