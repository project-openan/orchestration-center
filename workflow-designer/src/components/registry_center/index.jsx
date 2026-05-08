import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Search, Activity, Terminal, Wrench, ChevronRight,
    Zap, ShieldCheck, Cpu, Box, Bot, Database, Network, Globe, Code2, LayoutDashboard
} from 'lucide-react';
import { getAgentCards } from "@/service/api.js";
import CodeInspector from "./code_inspector/index.jsx";
import AgentCard from "./agentcard_visualization/index.tsx";

const THEMES = ['emerald', 'blue', 'indigo', 'rose', 'cyan', 'amber', 'violet'];
const ICONS = [
    <Network size={22} />, <Zap size={22} />, <ShieldCheck size={22} />,
    <Cpu size={22} />, <Box size={22} />, <Bot size={22} />,
    <Database size={22} />, <Globe size={22} />
];

const getAssetsBySeed = (seed) => {
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        hash = seed.charCodeAt(i) + ((hash << 5) - hash);
    }
    return {
        theme: THEMES[Math.abs(hash) % THEMES.length],
        icon: ICONS[Math.abs(hash) % ICONS.length]
    };
};

const AgentRegistry = ({ isDark, t }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [agents, setAgents] = useState([]);
    const [selectedId, setSelectedId] = useState(null);
    const [loading, setLoading] = useState(true);
    const [viewMode, setViewMode] = useState('structured'); // 'structured' | 'raw'

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const response = await getAgentCards();
                const rawList = response?.data || [];

                const enhancedData = rawList.map((val) => {
                    const key = val.name;

                    const ui = getAssetsBySeed(key);
                    const finalProvider = val.provider;

                    const syncedRaw = {
                        ...val,
                        provider: finalProvider
                    };

                    const modifiedSkills = (syncedRaw.skills || []).map(skill => {
                        const { inputs, outputs, ...rest } = skill;
                        return rest;
                    });

                    return {
                        ...syncedRaw,
                        id: key, // 用 name 作为 id
                        displayName: key.toUpperCase(),
                        ...ui,
                        _raw: { ...syncedRaw, skills: modifiedSkills },
                    };
                });

                setAgents(enhancedData);

                setSelectedId(prevId => {
                    const isPrevIdStillValid = enhancedData.some(a => a.id === prevId);

                    if (isPrevIdStillValid) {
                        return prevId;
                    } else if (enhancedData.length > 0) {
                        return enhancedData[0].id;
                    } else {
                        return null;
                    }
                });
            } catch (err) {
                console.error("Fetch Error:", err);
                setAgents([]);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    const agent = agents.find(a => a.id === selectedId);

    return (
        <div
            className="h-full p-6 flex items-stretch gap-6 w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans">
            <div className="w-[380px] flex flex-col p-2 shrink-0 min-h-0">
                <div className="flex flex-col gap-6 h-full min-h-0">
                    <div
                        className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-[2rem] p-6 shadow-xl border-t-4 border-t-zinc-300 dark:border-t-zinc-700 shrink-0">
                        <div className="flex items-center justify-between mb-6 px-1">
                            <h1 className="text-xl font-black text-zinc-900 dark:text-white uppercase leading-none">
                                {t('registry.title')}
                            </h1>
                            <span
                                className="text-zinc-400 text-[10px] font-black px-2 py-1 rounded-full uppercase border border-zinc-100 dark:border-zinc-800">
                                {agents.length} {t('registry.units')}
                            </span>
                        </div>
                        <div className="relative">
                            <input
                                type="text"
                                placeholder={t('registry.search_placeholder')}
                                className="w-full pl-10 pr-4 py-3 bg-zinc-50 dark:bg-zinc-800 border border-zinc-100 dark:border-zinc-700 rounded-xl text-base font-bold focus:ring-2 focus:ring-blue-500/20 outline-none transition-all dark:text-white"
                                onChange={(e) => setSearchTerm(e.target.value)}
                            />
                            <Search className="absolute left-3.5 top-3.5 text-zinc-400" size={16} />
                        </div>
                    </div>

                    <div className="flex-1 overflow-y-auto pr-2 space-y-3 custom-scrollbar min-h-0">
                        {agents.filter(a => a.id.toLowerCase().includes(searchTerm.toLowerCase())).map((a) => {
                            const isSelected = selectedId === a.id;
                            return (
                                <div key={a.id} onClick={() => setSelectedId(a.id)}
                                    className={`group p-5 rounded-2xl border transition-all duration-300 cursor-pointer relative overflow-hidden
                                    ${isSelected ? 'bg-zinc-100 dark:bg-zinc-800 border-transparent shadow-inner' : 'border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900 opacity-60 hover:opacity-100'}`}>
                                    {isSelected && <div
                                        className={`absolute left-0 top-0 bottom-0 w-1.5 animate-pulse ${a.theme === 'emerald' ? 'bg-emerald-500' : a.theme === 'blue' ? 'bg-blue-600' : 'bg-orange-500'}`} />}
                                    <div className="flex items-center justify-between mb-2 pl-2">
                                        <div
                                            className={`flex items-center gap-3 ${isSelected ? 'text-zinc-900 dark:text-white' : 'text-zinc-400'}`}>
                                            {a.icon}
                                            <h3 className="font-black text-base  leading-none">{a.id}</h3>
                                        </div>
                                        <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]" />
                                    </div>
                                    <div
                                        className={`pl-8 text-[10px] font-black uppercase ${isSelected ? 'text-blue-600 dark:text-blue-400' : 'text-zinc-400'}`}>
                                        {a.provider?.organization} · V{a.version}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            <div className="flex-1 min-w-0 flex flex-col p-2 min-h-0">
                {!agent ? (
                    <div
                        className="h-full flex items-center justify-center italic text-zinc-400 font-bold bg-white dark:bg-zinc-900 rounded-[2.5rem] border border-zinc-200 dark:border-zinc-800 shadow-2xl opacity-40">
                        {loading ? t('registry.synchronizing') : t('registry.select_agent')}
                    </div>
                ) : (
                    <div
                        className="bg-white dark:bg-zinc-900 rounded-[2.5rem] border border-zinc-200 dark:border-zinc-800 shadow-2xl flex flex-col h-full relative overflow-hidden">

                        <div
                            className="p-6 border-b border-zinc-100 dark:border-zinc-800 flex justify-between items-center bg-zinc-50/30 dark:bg-zinc-900 shrink-0">
                            <div className="flex items-center gap-5">
                                <div className={`p-4 rounded-2xl text-white shadow-lg ${agent.theme === 'emerald' ? 'bg-emerald-500 shadow-emerald-500/20' :
                                    agent.theme === 'blue' ? 'bg-blue-600 shadow-blue-600/20' : 'bg-orange-600 shadow-orange-600/20'
                                    }`}>
                                    {React.cloneElement(agent.icon, { size: 28 })}
                                </div>
                                <div>
                                    <div className="flex items-center gap-3">
                                        <h2 className="text-2xl font-black  dark:text-white leading-none">{agent.id}</h2>
                                        <div className="flex gap-2">
                                            <span
                                                className="px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-[10px] font-black text-blue-600">V{agent.version}</span>
                                            <button
                                                onClick={() => setViewMode(viewMode === 'structured' ? 'raw' : 'structured')}
                                                className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-zinc-200 dark:bg-zinc-800 hover:bg-zinc-300 dark:hover:bg-zinc-700 text-[10px] font-black text-zinc-600 dark:text-zinc-300 transition-colors uppercase"
                                            >
                                                {viewMode === 'structured' ? <Code2 size={12} /> :
                                                    <LayoutDashboard size={12} />}
                                                {viewMode === 'structured' ? t('registry.raw') : t('registry.gui')}
                                            </button>
                                        </div>
                                    </div>
                                    <div className="flex gap-3 mt-2 items-center">
                                        <span className="text-[10px] font-black text-zinc-400 uppercase">{t('registry.org')}</span>
                                        <span
                                            className="text-[10px] font-black text-zinc-900 dark:text-zinc-200 uppercase">{agent.provider?.organization}</span>
                                        <div className="w-1 h-1 rounded-full bg-zinc-300" />
                                        <span
                                            className="text-[10px] font-black text-zinc-400 uppercase">{t('registry.protocol')}</span>
                                        <span
                                            className="text-[10px] font-black text-zinc-900 dark:text-zinc-200">{agent.protocolVersion}</span>
                                    </div>
                                </div>
                            </div>
                            <button
                                onClick={() => setViewMode(viewMode === 'structured' ? 'raw' : 'structured')}
                                className={`
        flex items-center gap-2 px-3 py-1.5 rounded-md transition-all uppercase text-[12px] font-bold shadow-sm
        active:scale-95 active:shadow-inner
        ${isDark
                                        ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-blue-900/20'
                                        : 'bg-blue-600 hover:bg-blue-700 text-white shadow-blue-200'}
    `}
                            >
                                {viewMode === 'structured' ? <Code2 size={14} /> : <LayoutDashboard size={14} />}
                                <span>{viewMode === 'structured' ? t('registry.switch_to_raw') : t('registry.switch_to_gui')}</span>
                            </button>
                        </div>

                        <div className="flex-1 overflow-y-auto no-scrollbar bg-white dark:bg-zinc-900">
                            {viewMode === 'structured' ? (
                                <AgentCard agent={agent._raw} isDark={isDark} />
                            ) : (
                                <CodeInspector
                                    data={agent._raw}
                                    fileName={`${agent.id} AgentCard`}
                                    isDark={isDark}
                                />
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
export default AgentRegistry;
