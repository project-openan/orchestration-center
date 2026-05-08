import React, { useState, useEffect, useRef } from 'react';
import { getAgentCards } from "../../../../service/api.js";
import { useTranslation } from "react-i18next";
import Tooltip from "../../../common/tooltip_component/index.tsx";

import { Bot } from 'lucide-react';

const Sidebar = ({ isDark }) => {
    const { t } = useTranslation();
    const [agentGroups, setAgentGroups] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchAgents = async () => {
            try {
                const res = await getAgentCards();
                console.log('getAgentCards-sidebar', res)
                setAgentGroups(res.data || []);
            } catch (error) {
                console.error("Failed to fetch agents:", error);
            } finally {
                setLoading(false);
            }
        };
        fetchAgents();
    }, []);

    const onDragStart = (event, agentKey, agentInfo) => {
        const defaultSkill = agentInfo.skills?.[0];
        const templateData = {
            agent: agentKey,
            skill: defaultSkill?.name || "",
            skillsList: agentInfo.skills || [],
            inputs: {},
            outputs: {},
            description: agentInfo.description,
            defaultTask: t('workflow.sidebar.defaultTask', { name: agentInfo.name || agentKey })
        };

        event.dataTransfer.setData('application/agent-template', JSON.stringify(templateData));
        event.dataTransfer.effectAllowed = 'move';
    };

    const styles = {
        header: isDark
            ? 'border-zinc-800 bg-zinc-900/90 shadow-sm'
            : 'border-zinc-200 bg-zinc-50/50',
        title: isDark ? 'text-zinc-100' : 'text-zinc-800',

        listArea: isDark ? 'custom-scrollbar' : 'custom-scrollbar bg-white',

        card: isDark
            ? 'bg-zinc-900 border-zinc-800 hover:border-zinc-500 hover:bg-zinc-800/80 hover:shadow-[0_0_15px_rgba(255,255,255,0.05)]'
            : 'bg-white border-zinc-200 hover:border-zinc-400 hover:shadow-md',

        cardTitle: isDark ? 'text-zinc-100' : 'text-zinc-800',
        cardDesc: isDark ? 'text-zinc-400 border-zinc-800' : 'text-zinc-500 border-zinc-100',

        icon: isDark ? 'bg-zinc-800 text-zinc-100 border border-zinc-700' : 'bg-zinc-100 text-zinc-600',
        versionTag: isDark ? 'bg-zinc-950 text-zinc-500 border border-zinc-800' : 'bg-zinc-100 text-zinc-400',

        skillBadge: isDark
            ? 'bg-zinc-950 text-zinc-300 border-zinc-700/60'
            : 'bg-zinc-50 text-zinc-500 border-zinc-200'
    };

    const scrollRef = useRef(null);

    const handleWheel = (event) => {
        if (scrollRef.current) {
            scrollRef.current.scrollLeft += event.deltaY;
        }
    };

    if (loading) return <div
        className={`p-4 text-xs ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>{t('common.loading')}</div>;

    return (
        <div className="flex items-center px-4 py-0 gap-6 select-none">
            <style>{`
                @keyframes scrollTextOneWay {
                    0%, 15% { transform: translateX(0); }
                    85%, 100% { transform: translateX(var(--overflow)); }
                }
                .group:hover .scroll-text-target {
                    animation: scrollTextOneWay var(--duration) linear infinite;
                }
            `}</style>

            <div className="shrink-0 flex flex-col justify-center pr-6 border-r border-zinc-200 dark:border-zinc-700">
                <h2 className={`text-[10px] font-black tracking-widest opacity-40 uppercase ${styles.title}`}>
                    {t('workflow.sidebar.title')}
                </h2>
            </div>

            <div
                ref={scrollRef}
                onWheel={handleWheel}
                className={`flex items-center space-x-14 overflow-x-auto overflow-y-hidden px-4 pt-3 pb-8 transition-colors ${styles.listArea}`}
            >
                {agentGroups.map((info) => {
                    const key = info.name || info.id;
                    return (
                        <Tooltip
                            key={key}
                            side="top"
                            sideOffset={25}
                            content={
                                <div className="flex flex-col gap-1 px-1">
                                    <div className="font-bold text-sm border-b pb-1 mb-1 border-white/20">
                                        {info.displayName || key}
                                    </div>
                                    <div className="text-xs opacity-90 leading-relaxed">
                                        {info.description || t('execution.no_description')}
                                    </div>
                                </div>
                            }
                        >
                            <div
                                draggable
                                onDragStart={(e) => onDragStart(e, key, info)}
                                style={{ touchAction: 'none' }}
                                className="group relative w-16 h-16 shrink-0 cursor-grab active:scale-90 transition-transform"
                            >
                                <div className={`
                            w-full h-full rounded-full flex items-center justify-center text-xl
                            bg-zinc-100 dark:bg-zinc-800 border-2 border-transparent
                            shadow-sm transition-all duration-300
                            group-hover:border-blue-500 group-hover:shadow-lg
                            ${styles.icon}
                        `}>
                                    <Bot size={28} />
                                </div>

                                <div className={`
                            absolute bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2
                            w-auto max-w-[100px] min-w-[40px] px-2.5 py-0
                            rounded-full text-[13px] font-black text-center whitespace-nowrap
                            shadow-md border bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-200
                            group-hover:bg-blue-600 group-hover:text-white group-hover:border-blue-600
                            transition-all duration-100 z-20
                            ${styles.nameBadge || ''}
                        `}>
                                    <AutoScrollText text={key} />
                                </div>
                            </div>
                        </Tooltip>

                    )
                })
                }
            </div>
        </div>
    );
};

const AutoScrollText = ({ text }) => {
    const [overflowAmount, setOverflowAmount] = useState(0);
    const textRef = useRef(null);
    const containerRef = useRef(null);

    useEffect(() => {
        const checkOverflow = () => {
            if (textRef.current && containerRef.current) {
                const scrollWidth = textRef.current.scrollWidth;
                const clientWidth = containerRef.current.clientWidth;

                if (scrollWidth > clientWidth) {
                    setOverflowAmount(scrollWidth - clientWidth);
                } else {
                    setOverflowAmount(0);
                }
            }
        };

        checkOverflow();
        window.addEventListener('resize', checkOverflow);
        return () => window.removeEventListener('resize', checkOverflow);
    }, [text]);

    return (
        <div
            ref={containerRef}
            className={`w-full overflow-hidden ${overflowAmount > 0 ? 'text-left' : 'text-center'}`}
            style={{
                '--overflow': `-${overflowAmount}px`,
                '--duration': `${Math.max(2, overflowAmount * 0.03)}s`
            }}
        >
            <div
                ref={textRef}
                className={`whitespace-nowrap inline-block ${overflowAmount > 0 ? 'scroll-text-target' : ''}`}
            >
                {text}
            </div>
        </div>
    );
};
export default Sidebar;
