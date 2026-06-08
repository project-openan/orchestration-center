import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Search, Code2, LayoutDashboard,
    X, Layers, Server, Radio, Network, Globe
} from 'lucide-react';
import { getAgentCards } from "@/service/api.js";
import CodeInspector from "./code_inspector/index.jsx";
import AgentCard from "./agentcard_visualization/index.jsx";

const THEMES = ['emerald', 'blue', 'indigo', 'rose', 'cyan', 'amber', 'violet'];

const SERVICE_LAYER_TAGS = ['live', 'assurance', 'uncertainty', 'monitoring', 'negotiation', 'simulation'];
const NETWORK_LAYER_TAGS = ['ran', 'spn', 'dispatch', 'energy-saving', 'wireless', 'diagnosis', 'aggregate', 'analysis', 'plan', 'exec', 'strategy', 'recovery'];

const getAssetsBySeed = (seed, layer) => {
    const SERVICE_THEMES = ['blue', 'indigo', 'cyan'];
    const NETWORK_THEMES = ['emerald', 'amber', 'rose'];
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        hash = seed.charCodeAt(i) + ((hash << 5) - hash);
    }
    const themes = layer === 'network' ? NETWORK_THEMES : SERVICE_THEMES;
    return {
        theme: themes[Math.abs(hash) % themes.length],
        icon: layer === 'network' ? <Network size={22} /> : <Server size={22} />
    };
};

const getAgentLayer = (agent) => {
    const allTags = (agent.skills || []).flatMap(s => s.tags || []);
    const hasServiceTag = allTags.some(tag => SERVICE_LAYER_TAGS.includes(tag));
    const hasNetworkTag = allTags.some(tag => NETWORK_LAYER_TAGS.includes(tag));
    if (hasServiceTag && !hasNetworkTag) return 'service';
    if (hasNetworkTag) return 'network';
    return 'service';
};

const TABS = ['all', 'service', 'network', 'vendor'];

const AgentRegistry = ({ isDark, t }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [agents, setAgents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('all');
    const [selectedAgent, setSelectedAgent] = useState(null);
    const [viewMode, setViewMode] = useState('structured');

    useEffect(() => {
        const fetchData = async () => {
            try {
                setLoading(true);
                const response = await getAgentCards();
                const rawList = response?.data || [];

                const enhancedData = rawList.map((val) => {
                    const key = val.name;
                    const syncedRaw = { ...val, provider: val.provider };
                    const modifiedSkills = (syncedRaw.skills || []).map(skill => {
                        const { inputs, outputs, ...rest } = skill;
                        return rest;
                    });
                    const layer = getAgentLayer(syncedRaw);
                    const ui = getAssetsBySeed(key, layer);
                    return {
                        ...syncedRaw,
                        id: key,
                        displayName: key.toUpperCase(),
                        ...ui,
                        layer: layer,
                        _raw: { ...syncedRaw, skills: modifiedSkills },
                    };
                });

                setAgents(enhancedData);
            } catch (err) {
                console.error("Fetch Error:", err);
                setAgents([]);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []);

    const filteredAgents = useMemo(() => {
        let result = agents;
        if (searchTerm) {
            const term = searchTerm.toLowerCase();
            result = result.filter(a =>
                a.id.toLowerCase().includes(term) ||
                a.description?.toLowerCase().includes(term) ||
                (a.skills || []).some(s => s.name?.toLowerCase().includes(term))
            );
        }
        if (activeTab === 'service') {
            result = result.filter(a => a.layer === 'service');
        } else if (activeTab === 'network') {
            result = result.filter(a => a.layer === 'network');
        }
        result = [...result].sort((a, b) => {
            const order = { service: 0, network: 1 };
            return (order[a.layer] ?? 2) - (order[b.layer] ?? 2);
        });
        return result;
    }, [agents, searchTerm, activeTab]);

    const vendorGroups = useMemo(() => {
        const groups = {};
        const source = searchTerm
            ? agents.filter(a => {
                const term = searchTerm.toLowerCase();
                return a.id.toLowerCase().includes(term) || a.description?.toLowerCase().includes(term);
            })
            : agents;
        source.forEach(a => {
            const org = a.provider?.organization || 'Unknown';
            if (!groups[org]) groups[org] = [];
            groups[org].push(a);
        });
        Object.values(groups).forEach(arr => arr.sort((a, b) => {
            const order = { service: 0, network: 1 };
            return (order[a.layer] ?? 2) - (order[b.layer] ?? 2);
        }));
        return groups;
    }, [agents, searchTerm]);

    const tabCounts = useMemo(() => ({
        all: agents.length,
        service: agents.filter(a => a.layer === 'service').length,
        network: agents.filter(a => a.layer === 'network').length,
        vendor: Object.keys(vendorGroups).length,
    }), [agents, vendorGroups]);

    const themeColor = (theme) => {
        const map = {
            emerald: 'bg-emerald-500', blue: 'bg-blue-600', indigo: 'bg-indigo-500',
            rose: 'bg-rose-500', cyan: 'bg-cyan-500', amber: 'bg-amber-500', violet: 'bg-violet-500'
        };
        return map[theme] || 'bg-blue-600';
    };

    const themeBorder = (theme) => {
        const map = {
            emerald: 'hover:border-emerald-300 dark:hover:border-emerald-700',
            blue: 'hover:border-blue-300 dark:hover:border-blue-700',
            indigo: 'hover:border-indigo-300 dark:hover:border-indigo-700',
            rose: 'hover:border-rose-300 dark:hover:border-rose-700',
            cyan: 'hover:border-cyan-300 dark:hover:border-cyan-700',
            amber: 'hover:border-amber-300 dark:hover:border-amber-700',
            violet: 'hover:border-violet-300 dark:hover:border-violet-700'
        };
        return map[theme] || 'hover:border-blue-300';
    };

    const layerBadge = (layer) => {
        if (layer === 'network') {
            return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800';
        }
        return 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border-blue-200 dark:border-blue-800';
    };

    const layerBg = () => {
        return 'bg-white dark:bg-zinc-900';
    };

    const renderCard = (agent) => (
        <div
            key={agent.id}
            onClick={() => { setSelectedAgent(agent); setViewMode('structured'); }}
            className={`group relative p-6 rounded-2xl border cursor-pointer transition-all duration-300
                ${layerBg()} border-zinc-100 dark:border-zinc-800
                ${themeBorder(agent.theme)}
                hover:shadow-lg hover:-translate-y-1 animate-in fade-in duration-300`}
        >
            <div className="flex items-start justify-between mb-4">
                <div className={`p-3 rounded-xl text-white shadow-lg ${agent.layer === 'network' ? 'bg-emerald-500' : themeColor(agent.theme)}`}>
                    {React.cloneElement(agent.icon, { size: 22 })}
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_#10b981]" />
                    <span className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase">
                        V{agent.version}
                    </span>
                </div>
            </div>

            <h3 className="text-sm font-black text-zinc-900 dark:text-white mb-2 leading-tight truncate">
                {agent.id}
            </h3>
            <p className="text-[11px] text-zinc-500 dark:text-zinc-400 line-clamp-2 mb-4 leading-relaxed min-h-[2.5em]">
                {agent.description}
            </p>

            <div className="flex flex-wrap gap-1.5 mb-4">
                {(agent.skills || []).slice(0, 3).map(skill => (
                    <span key={skill.id}
                        className="px-2 py-0.5 rounded-md text-[9px] font-bold bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700">
                        {skill.name}
                    </span>
                ))}
                {(agent.skills || []).length > 3 && (
                    <span className="px-2 py-0.5 rounded-md text-[9px] font-bold text-zinc-400 dark:text-zinc-500">
                        +{agent.skills.length - 3}
                    </span>
                )}
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-zinc-100 dark:border-zinc-800">
                <span className={`text-xs font-black px-4 py-1 rounded-lg border uppercase ${layerBadge(agent.layer)}`}>
                    {agent.layer === 'network' ? 'Network' : 'Service'}
                </span>
                <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500">
                    {agent.skills?.length || 0} {t('registry.skills_count')}
                </span>
            </div>
        </div>
    );

    return (
        <div className="h-full p-6 flex flex-col w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans">
            <div className="shrink-0 flex items-center justify-between mb-6 px-2">
                <div className="flex items-center gap-4">
                    <div className="p-2.5 bg-zinc-900 dark:bg-blue-600 rounded-xl text-white shadow-lg">
                        <Server size={20} />
                    </div>
                    <div>
                        <h1 className="text-lg font-black text-zinc-900 dark:text-white uppercase leading-none">
                            {t('registry.title')}
                        </h1>
                        <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase">
                            {agents.length} {t('registry.units')} · {t('registry.online')}
                        </span>
                    </div>
                </div>
                <div className="relative w-72">
                    <input
                        type="text"
                        placeholder={t('registry.search_placeholder')}
                        className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-blue-500/20 focus:border-blue-400 outline-none transition-all dark:text-white"
                        onChange={(e) => setSearchTerm(e.target.value)}
                        value={searchTerm}
                    />
                    <Search className="absolute left-3.5 top-3 text-zinc-400" size={14} />
                </div>
            </div>

            <div className="shrink-0 flex items-center gap-1 mb-6 px-2">
                {TABS.map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-black uppercase tracking-wide transition-all duration-300
                            ${activeTab === tab
                                ? 'bg-zinc-900 dark:bg-white text-white dark:text-zinc-900 shadow-md'
                                : 'text-zinc-400 dark:text-zinc-500 hover:text-zinc-600 dark:hover:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800'}`}
                    >
                        {tab === 'all' && <Layers size={14} />}
                        {tab === 'service' && <Radio size={14} />}
                        {tab === 'network' && <Network size={14} />}
                        {tab === 'vendor' && <Globe size={14} />}
                        {t(`registry.tab_${tab}`)}
                        <span className={`px-1.5 py-0.5 rounded-md text-[9px] font-black
                            ${activeTab === tab
                                ? 'bg-white/20 dark:bg-zinc-900/20'
                                : 'bg-zinc-100 dark:bg-zinc-800'}`}>
                            {tabCounts[tab]}
                        </span>
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0 px-2">
                {loading ? (
                    <div className="h-full flex items-center justify-center">
                        <div className="flex flex-col items-center gap-3 text-zinc-400">
                            <div className="w-8 h-8 border-2 border-zinc-300 dark:border-zinc-600 border-t-blue-500 rounded-full animate-spin" />
                            <span className="text-sm font-bold uppercase tracking-wider">{t('registry.synchronizing')}</span>
                        </div>
                    </div>
                ) : activeTab === 'vendor' ? (
                    <div className="space-y-8 pb-8">
                        {Object.entries(vendorGroups).map(([org, orgAgents]) => (
                            <div key={org}>
                                <div className="flex items-center gap-3 mb-4">
                                    <div className="p-2 rounded-lg bg-zinc-100 dark:bg-zinc-800">
                                        <Globe size={16} className="text-zinc-500" />
                                    </div>
                                    <h2 className="text-sm font-black text-zinc-700 dark:text-zinc-300 uppercase">
                                        {org}
                                    </h2>
                                    <span className="text-[10px] font-bold text-zinc-400 bg-zinc-100 dark:bg-zinc-800 px-2 py-0.5 rounded-full">
                                        {orgAgents.length} {t('registry.units')}
                                    </span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                                    {orgAgents.map(renderCard)}
                                </div>
                            </div>
                        ))}
                        {Object.keys(vendorGroups).length === 0 && (
                            <div className="h-64 flex items-center justify-center text-zinc-400 text-sm font-bold">
                                {t('registry.no_agents')}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-8">
                        {filteredAgents.map(renderCard)}
                        {filteredAgents.length === 0 && (
                            <div className="col-span-full h-64 flex items-center justify-center text-zinc-400 text-sm font-bold">
                                {t('registry.no_agents')}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {selectedAgent && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-zinc-950 w-full max-w-5xl h-[85vh] rounded-[2rem] shadow-2xl border border-zinc-200 dark:border-zinc-800 flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
                        <div className="p-5 border-b border-zinc-100 dark:border-zinc-800 flex justify-between items-center bg-zinc-50/50 dark:bg-zinc-900/50 shrink-0">
                            <div className="flex items-center gap-4">
                                <div className={`p-3 rounded-xl text-white shadow-lg ${selectedAgent.layer === 'network' ? 'bg-emerald-500' : themeColor(selectedAgent.theme)}`}>
                                    {React.cloneElement(selectedAgent.icon, { size: 24 })}
                                </div>
                                <div>
                                    <h2 className="text-lg font-black dark:text-white leading-none">{selectedAgent.id}</h2>
                                    <div className="flex items-center gap-2 mt-1">
                                        <span className="text-[10px] font-bold text-zinc-400 uppercase">{selectedAgent.provider?.organization}</span>
                                        <span className="w-1 h-1 rounded-full bg-zinc-300" />
                                        <span className="text-[10px] font-bold text-zinc-400">V{selectedAgent.version}</span>
                                        <span className="w-1 h-1 rounded-full bg-zinc-300" />
                                        <span className="text-[10px] font-bold text-zinc-400">{selectedAgent.skills?.length} {t('registry.skills_count')}</span>
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-3">
                                <button
                                    onClick={() => setViewMode(viewMode === 'structured' ? 'raw' : 'structured')}
                                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg transition-all text-[11px] font-black uppercase shadow-sm
                                        ${isDark
                                            ? 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300'
                                            : 'bg-zinc-100 hover:bg-zinc-200 text-zinc-600'}`}
                                >
                                    {viewMode === 'structured' ? <Code2 size={14} /> : <LayoutDashboard size={14} />}
                                    {viewMode === 'structured' ? t('registry.switch_to_raw') : t('registry.switch_to_gui')}
                                </button>
                                <button
                                    onClick={() => setSelectedAgent(null)}
                                    className="p-2 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                                >
                                    <X size={20} className="text-zinc-400" />
                                </button>
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto no-scrollbar">
                            {viewMode === 'structured' ? (
                                <AgentCard agent={selectedAgent._raw} isDark={isDark} />
                            ) : (
                                <CodeInspector
                                    data={selectedAgent._raw}
                                    fileName={`${selectedAgent.id} AgentCard`}
                                    isDark={isDark}
                                />
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};
export default AgentRegistry;
