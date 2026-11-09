// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React, { useState, useRef } from 'react';
import { Bot } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Tooltip from '@/components/common/tooltip_component/index.jsx';

/** The same palette shell and cards for instance agents and role identities. */
export default function TemplatePalette({ title, items, isDark, disabled = false }) {
    const scrollRef = useRef(null);
    return <div className="flex items-center px-4 gap-6 select-none max-w-[75vw]" aria-label={title}>
        <div className="shrink-0 pr-6 border-r border-zinc-200 dark:border-zinc-700">
            <h2 className={`text-[10px] font-black tracking-widest opacity-40 uppercase ${isDark ? 'text-zinc-100' : 'text-zinc-800'}`}>{title}</h2>
        </div>
        <div ref={scrollRef} onWheel={event => { scrollRef.current.scrollLeft += event.deltaY; }}
            className={`flex items-start gap-10 overflow-x-auto overflow-y-hidden px-5 pt-4 pb-5 custom-scrollbar ${isDark ? '' : 'bg-white'}`}>
            {items.map(item => <PaletteItem key={item.id} item={item} isDark={isDark} disabled={disabled} />)}
        </div>
    </div>;
}

function PaletteItem({ item, isDark, disabled }) {
    const { t } = useTranslation();
    const [skillId, setSkillId] = useState(item.skills?.[0]?.id);
    const skill = item.skills?.find(value => value.id === skillId) || item.skills?.[0];
    const template = skill?.template || item.template;
    return <div className="flex flex-col items-center w-28 shrink-0 gap-2">
        <Tooltip side="top" sideOffset={25} content={<div className="space-y-1">
            <div className="font-bold text-sm border-b pb-1 border-white/20">{item.label}</div>
            {item.version && <p className="text-xs font-mono">{item.id}</p>}
            <p className="text-xs">{skill?.description || item.description || t('execution.no_description')}</p>
        </div>}>
            <div draggable={!disabled && Boolean(template)} aria-disabled={disabled}
                aria-label={skill ? `${item.label}: ${skill.label}` : item.label}
                data-skill-id={skill?.id} style={{ touchAction: 'none' }}
                onDragStart={event => {
                    if (disabled || !template) { event.preventDefault(); return; }
                    event.dataTransfer.setData('application/agent-template', JSON.stringify(template));
                    event.dataTransfer.effectAllowed = 'move';
                }}
                className={`group relative w-16 h-16 shrink-0 transition-transform ${disabled ? 'opacity-50' : 'cursor-grab active:scale-90'}`}>
                <div className={`w-full h-full rounded-full flex items-center justify-center border-2 border-transparent shadow-sm transition-all duration-300 group-hover:border-blue-500 group-hover:shadow-lg ${isDark ? 'bg-zinc-800 text-zinc-100' : 'bg-zinc-100 text-zinc-600'}`}>
                    <Bot size={28} />
                </div>
                <div className={`absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 max-w-28 min-w-10 px-2.5 rounded-full text-[13px] font-black text-center whitespace-nowrap shadow-md border group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600 transition-colors z-20 ${isDark ? 'bg-gray-700 text-gray-200 border-zinc-600' : 'bg-white text-gray-900 border-zinc-200'}`}>
                    <span className="block truncate">{item.label}</span>
                </div>
            </div>
        </Tooltip>
        {item.skills && <div className="w-full pt-2 space-y-1">
            <p className={`text-[10px] text-center ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>v{item.version}</p>
            <select aria-label={`${t('workflow.roleEditSkill')}: ${item.label}`} value={skill?.id || ''}
                disabled={disabled} onChange={event => setSkillId(event.target.value)}
                className={`w-full rounded-full border px-2 py-1 text-[11px] outline-none focus:border-blue-500 ${isDark ? 'bg-zinc-800 border-zinc-700 text-zinc-200' : 'bg-zinc-50 border-zinc-200 text-zinc-600'}`}>
                {item.skills.map(value => <option key={value.id} value={value.id}>{value.label}</option>)}
            </select>
        </div>}
    </div>;
}
