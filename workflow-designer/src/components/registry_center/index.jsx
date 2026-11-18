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
import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Search, Code2, LayoutDashboard,
    X, Layers, Server, Radio, Network, Globe, ChevronRight,
    Pencil, Trash2, CheckCircle2, AlertTriangle
} from 'lucide-react';
import { getAgentCards, updateAgentCard, deleteAgentCard } from "@/service/api.js";
import DeleteConfirm from "@/components/common/pop_confirm/index.jsx";
import CodeInspector from "./code_inspector/index.jsx";
import AgentCard from "./agentcard_visualization/index.jsx";

const THEMES = ['emerald', 'blue', 'indigo', 'rose', 'cyan', 'amber', 'violet'];

const NETWORK_LAYER_VENDORS = ['huawei', 'ericsson', 'zte', '华为', '爱立信', '中兴'];
const SERVICE_LAYER_VENDORS = ['直真', '新大陆', '福诺', '亿阳', '移动'];

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
    const org = (agent.provider?.organization || '').toLowerCase();
    const isNetworkVendor = NETWORK_LAYER_VENDORS.some(vendor => org.includes(vendor));
    const isServiceVendor = SERVICE_LAYER_VENDORS.some(vendor => org.includes(vendor));
    if (isNetworkVendor) return 'network';
    if (isServiceVendor) return 'service';
    return 'service';
};

const TABS = ['all', 'service', 'network', 'vendor'];

// Layer pill: both layers stay on the brand ramp, only the label differs.
const LAYER_PILL = 'bg-cm-tint text-[#255BCE] dark:bg-zinc-800 dark:text-blue-300';

const AgentRegistry = ({ isDark, t, isAdmin = false }) => {
    const [searchTerm, setSearchTerm] = useState('');
    const [agents, setAgents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [activeTab, setActiveTab] = useState('all');
    const [selectedAgent, setSelectedAgent] = useState(null);
    const [viewMode, setViewMode] = useState('structured');
    const [editState, setEditState] = useState(null);
    const [toast, setToast] = useState({ show: false, msg: '', type: 'success' });

    const showToast = (msg, type = 'success') => setToast({ show: true, msg, type });

    useEffect(() => {
        if (!toast.show) return undefined;
        const timer = setTimeout(() => setToast(prev => ({ ...prev, show: false })), 3000);
        return () => clearTimeout(timer);
    }, [toast]);

    const enhanceAgents = (rawList) => rawList.map((val) => {
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

    const fetchAgents = async () => {
        try {
            setLoading(true);
            const response = await getAgentCards();
            const rawList = response?.data || [];
            setAgents(enhanceAgents(rawList));
        } catch (err) {
            console.error("Fetch Error:", err);
            setAgents([]);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchAgents();
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

    // The list item carries UI-only decorations (id/displayName/theme/icon/
    // layer/_raw) that must never be sent back to the registry.
    const toCardPayload = (agent) => {
        const { id, displayName, theme, icon, layer, _raw, ...card } = agent;
        return card;
    };

    const openEdit = (agent) => {
        const card = toCardPayload(agent);
        setEditState({
            agent,
            mode: 'form',
            saving: false,
            form: {
                description: card.description || '',
                version: card.version || '',
                providerUrl: card.provider?.url || '',
                documentationUrl: card.documentationUrl || '',
                iconUrl: card.iconUrl || '',
            },
            jsonText: JSON.stringify(card, null, 2),
        });
        setSelectedAgent(null);
    };

    const handleDeleteAgent = async (agent) => {
        try {
            await deleteAgentCard(agent.id, agent.provider?.organization || '');
            showToast(t('registry.delete_success'));
            if (selectedAgent?.id === agent.id) setSelectedAgent(null);
            await fetchAgents();
        } catch (err) {
            console.error("Delete Error:", err);
            showToast(`${t('registry.delete_failed')}${err.response?.data?.message || err.message}`, 'error');
        }
    };

    const buildUpdatePayload = () => {
        const card = toCardPayload(editState.agent);
        if (editState.mode === 'json') {
            let parsed;
            try {
                parsed = JSON.parse(editState.jsonText);
            } catch (e) {
                showToast(`${t('registry.json_invalid')}${e.message}`, 'error');
                return null;
            }
            if (parsed?.name !== editState.agent.id ||
                parsed?.provider?.organization !== editState.agent.provider?.organization) {
                showToast(t('registry.json_identity_mismatch'), 'error');
                return null;
            }
            return parsed;
        }
        const f = editState.form;
        return {
            ...card,
            description: f.description,
            version: f.version,
            provider: { ...(card.provider || {}), url: f.providerUrl },
            ...(f.documentationUrl ? { documentationUrl: f.documentationUrl } : {}),
            ...(f.iconUrl ? { iconUrl: f.iconUrl } : {}),
        };
    };

    const handleSaveEdit = async () => {
        const payload = buildUpdatePayload();
        if (!payload) return;
        setEditState(prev => ({ ...prev, saving: true }));
        try {
            await updateAgentCard(editState.agent.id, editState.agent.provider?.organization || '', payload);
            showToast(t('registry.update_success'));
            setEditState(null);
            await fetchAgents();
        } catch (err) {
            console.error("Update Error:", err);
            showToast(`${t('registry.update_failed')}${err.response?.data?.message || err.message}`, 'error');
            setEditState(prev => ({ ...prev, saving: false }));
        }
    };

    const renderCard = (agent) => (
        <div
            key={agent.id}
            onClick={() => { setSelectedAgent(agent); setViewMode('structured'); }}
            className="group relative flex flex-col p-[17px_16px_14px] cursor-pointer cm-card cm-card-hover
                dark:bg-zinc-900 dark:border-zinc-800 dark:hover:border-blue-700
                animate-in fade-in duration-300"
        >
            <div className="flex items-start gap-3">
                <div className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                    {React.cloneElement(agent.icon, { size: 18 })}
                </div>
                <div className="min-w-0 flex-1">
                    <h3 className="cm-entity-title dark:text-zinc-100" title={agent.id}>
                        {agent.id}
                    </h3>
                    <p className="cm-entity-meta dark:text-zinc-500">
                        {agent.provider?.organization} · V{agent.version}
                    </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 dark:bg-emerald-400" />
                    {isAdmin && (
                        <DeleteConfirm
                            title={t('registry.delete_agent_confirm')}
                            onConfirm={() => handleDeleteAgent(agent)}
                            isDark={isDark}
                        >
                            <button
                                className="cm-icon-btn opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity
                                    hover:bg-rose-50 hover:text-rose-600
                                    dark:hover:bg-rose-500/10 dark:hover:text-rose-400"
                                title={t('registry.delete_agent')}
                            >
                                <Trash2 size={14} />
                            </button>
                        </DeleteConfirm>
                    )}
                </div>
            </div>

            <p className="mt-3 text-[12px] leading-[1.6] text-cm-secondary dark:text-zinc-400 line-clamp-2 min-h-[38px]">
                {agent.description}
            </p>

            <div className="flex flex-wrap gap-1.5 mt-3">
                {(agent.skills || []).slice(0, 3).map(skill => (
                    <span key={skill.id} className="cm-chip dark:bg-zinc-800 dark:text-blue-300">
                        {skill.name}
                    </span>
                ))}
                {(agent.skills || []).length > 3 && (
                    <span className="cm-chip-neutral dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-400">
                        +{agent.skills.length - 3}
                    </span>
                )}
            </div>

            <div className="mt-auto pt-3 flex items-center justify-between border-t border-cm-line-soft dark:border-zinc-800">
                <span className="text-[11px] text-cm-faint dark:text-zinc-500">
                    {agent.skills?.length || 0} {t('registry.skills_count')}
                </span>
                <span className={`text-[11px] font-semibold px-2 py-[3px] rounded-[5px] whitespace-nowrap ${LAYER_PILL}`}>
                    {agent.layer === 'network' ? 'Network' : 'Service'}
                </span>
            </div>
        </div>
    );

    return (
        <div className="h-full p-6 flex flex-col w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans bg-cm-canvas dark:bg-cm-night">
            <div className="shrink-0 flex items-start justify-between gap-4 mb-5">
                <div className="min-w-0">
                    <h1 className="cm-section-title dark:text-zinc-100">
                        {t('registry.title')}
                    </h1>
                    <p className="mt-1 text-[12px] text-cm-muted dark:text-zinc-400">
                        {agents.length} {t('registry.units')} · {t('registry.online')}
                    </p>
                </div>
                <div className="cm-search shrink-0 w-[300px] dark:bg-zinc-900 dark:border-zinc-700">
                    <Search size={15} className="shrink-0 text-cm-faint dark:text-zinc-500" />
                    <input
                        type="text"
                        placeholder={t('registry.search_placeholder')}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        value={searchTerm}
                        className="dark:text-zinc-100 dark:placeholder:text-zinc-500"
                    />
                </div>
            </div>

            <div className="shrink-0 flex items-center gap-1.5 mb-5">
                {TABS.map(tab => (
                    <button
                        key={tab}
                        onClick={() => setActiveTab(tab)}
                        className={`flex items-center gap-1.5 h-8 px-3 rounded-cm-sm text-[12px] transition-colors duration-150
                            ${activeTab === tab
                                ? 'bg-cm-tint dark:bg-zinc-800 text-[#255BCE] dark:text-blue-300 font-bold'
                                : 'text-cm-muted dark:text-zinc-400 font-medium hover:bg-cm-tint/70 dark:hover:bg-zinc-800 hover:text-[#255BCE] dark:hover:text-zinc-200'}`}
                    >
                        {tab === 'all' && <Layers size={14} />}
                        {tab === 'service' && <Radio size={14} />}
                        {tab === 'network' && <Network size={14} />}
                        {tab === 'vendor' && <Globe size={14} />}
                        {t(`registry.tab_${tab}`)}
                        <span className={`px-1.5 py-[1px] rounded-[5px] text-[10px] font-semibold
                            ${activeTab === tab
                                ? 'bg-white text-[#255BCE] dark:bg-zinc-900 dark:text-blue-300'
                                : 'bg-cm-canvas text-cm-faint dark:bg-zinc-800 dark:text-zinc-500'}`}>
                            {tabCounts[tab]}
                        </span>
                    </button>
                ))}
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar min-h-0">
                {loading ? (
                    <div className="h-full flex items-center justify-center">
                        <div className="flex flex-col items-center gap-3">
                            <div className="w-7 h-7 border-2 border-cm-line dark:border-zinc-700 border-t-cm-primary dark:border-t-blue-400 rounded-full animate-spin" />
                            <span className="text-[12px] font-medium tracking-wide text-cm-muted dark:text-zinc-400">{t('registry.synchronizing')}</span>
                        </div>
                    </div>
                ) : activeTab === 'vendor' ? (
                    <div className="space-y-7 pb-8">
                        {Object.entries(vendorGroups).map(([org, orgAgents]) => (
                            <div key={org}>
                                <div className="flex items-center gap-2.5 mb-3">
                                    <div className="cm-entity-icon-square h-7 w-7 min-w-[28px] dark:bg-zinc-800 dark:text-blue-400">
                                        <Globe size={14} />
                                    </div>
                                    <h2 className="text-[13px] font-bold text-cm-heading dark:text-zinc-100">
                                        {org}
                                    </h2>
                                    <span className="cm-chip-neutral dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-400">
                                        {orgAgents.length} {t('registry.units')}
                                    </span>
                                </div>
                                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-[17px]">
                                    {orgAgents.map(renderCard)}
                                </div>
                            </div>
                        ))}
                        {Object.keys(vendorGroups).length === 0 && (
                            <div className="h-64 flex items-center justify-center text-[13px] text-cm-faint dark:text-zinc-500">
                                {t('registry.no_agents')}
                            </div>
                        )}
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-[17px] pb-8">
                        {filteredAgents.map(renderCard)}
                        {filteredAgents.length === 0 && (
                            <div className="col-span-full h-64 flex items-center justify-center text-[13px] text-cm-faint dark:text-zinc-500">
                                {t('registry.no_agents')}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {selectedAgent && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-cm-ink-strong/40 dark:bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-zinc-900 w-full max-w-5xl h-[85vh] rounded-3xl shadow-modal border border-cm-line dark:border-zinc-800 flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
                        <div className="px-5 py-4 border-b border-cm-line dark:border-zinc-800 flex justify-between items-center shrink-0">
                            <div className="flex items-center gap-3 min-w-0">
                                <div className="cm-entity-icon-square shrink-0 dark:bg-zinc-800 dark:text-blue-400">
                                    {React.cloneElement(selectedAgent.icon, { size: 18 })}
                                </div>
                                <div className="min-w-0">
                                    <h2 className="text-[15px] font-bold text-cm-heading dark:text-zinc-100 leading-tight truncate">{selectedAgent.id}</h2>
                                    <div className="flex items-center gap-2 mt-1 text-[11px] text-cm-faint dark:text-zinc-500">
                                        <span className="truncate">{selectedAgent.provider?.organization}</span>
                                        <span className="w-[3px] h-[3px] rounded-full bg-cm-line-strong dark:bg-zinc-600 shrink-0" />
                                        <span className="shrink-0">V{selectedAgent.version}</span>
                                        <span className="w-[3px] h-[3px] rounded-full bg-cm-line-strong dark:bg-zinc-600 shrink-0" />
                                        <span className="shrink-0">{selectedAgent.skills?.length} {t('registry.skills_count')}</span>
                                    </div>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                {isAdmin && (
                                    <button
                                        onClick={() => openEdit(selectedAgent)}
                                        className="cm-btn-primary"
                                    >
                                        <Pencil size={13} />
                                        {t('registry.edit_agent')}
                                    </button>
                                )}
                                <button
                                    onClick={() => setViewMode(viewMode === 'structured' ? 'raw' : 'structured')}
                                    className="cm-btn dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-700 dark:hover:text-white"
                                >
                                    {viewMode === 'structured' ? <Code2 size={13} /> : <LayoutDashboard size={13} />}
                                    {viewMode === 'structured' ? t('registry.switch_to_raw') : t('registry.switch_to_gui')}
                                </button>
                                <button
                                    onClick={() => setSelectedAgent(null)}
                                    className="cm-icon-btn dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                                >
                                    <X size={18} className="text-cm-faint dark:text-zinc-500" />
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

            {editState && (
                <div className="fixed inset-0 z-[110] flex items-center justify-center p-6 bg-cm-ink-strong/40 dark:bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
                    <div className="bg-white dark:bg-zinc-900 w-full max-w-2xl max-h-[85vh] rounded-3xl shadow-modal border border-cm-line dark:border-zinc-800 flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
                        <div className="px-5 py-4 border-b border-cm-line dark:border-zinc-800 flex justify-between items-center shrink-0">
                            <div className="min-w-0">
                                <h2 className="text-[15px] font-bold text-cm-heading dark:text-zinc-100 leading-tight">{t('registry.edit_agent_title')}</h2>
                                <div className="flex items-center gap-2 mt-1 text-[11px] text-cm-faint dark:text-zinc-500">
                                    <span className="truncate">{editState.agent.id}</span>
                                    <span className="w-[3px] h-[3px] rounded-full bg-cm-line-strong dark:bg-zinc-600 shrink-0" />
                                    <span className="truncate">{editState.agent.provider?.organization}</span>
                                </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                                <button
                                    onClick={() => setEditState(prev => ({ ...prev, mode: 'form' }))}
                                    className={editState.mode === 'form'
                                        ? 'cm-btn-soft dark:bg-zinc-800 dark:border-zinc-700 dark:text-blue-300 font-semibold'
                                        : 'cm-btn dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800'}
                                >
                                    {t('registry.edit_mode_form')}
                                </button>
                                <button
                                    onClick={() => setEditState(prev => ({ ...prev, mode: 'json' }))}
                                    className={editState.mode === 'json'
                                        ? 'cm-btn-soft dark:bg-zinc-800 dark:border-zinc-700 dark:text-blue-300 font-semibold'
                                        : 'cm-btn dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800'}
                                >
                                    {t('registry.edit_mode_json')}
                                </button>
                                <button
                                    onClick={() => setEditState(null)}
                                    className="cm-icon-btn dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
                                >
                                    <X size={18} className="text-cm-faint dark:text-zinc-500" />
                                </button>
                            </div>
                        </div>
                        <div className="flex-1 overflow-y-auto custom-scrollbar p-5 space-y-4">
                            {editState.mode === 'form' ? (
                                <>
                                    <p className="text-[11px] leading-relaxed text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/20 rounded-cm px-3 py-2">
                                        {t('registry.edit_identity_hint')}
                                    </p>
                                    <EditField
                                        label={t('registry.field_description')}
                                        value={editState.form.description}
                                        isTextArea
                                        onChange={(v) => setEditState(prev => ({ ...prev, form: { ...prev.form, description: v } }))}
                                    />
                                    <div className="grid grid-cols-2 gap-4">
                                        <EditField
                                            label={t('registry.field_version')}
                                            value={editState.form.version}
                                            onChange={(v) => setEditState(prev => ({ ...prev, form: { ...prev.form, version: v } }))}
                                        />
                                        <EditField
                                            label={t('registry.field_provider_url')}
                                            value={editState.form.providerUrl}
                                            onChange={(v) => setEditState(prev => ({ ...prev, form: { ...prev.form, providerUrl: v } }))}
                                        />
                                        <EditField
                                            label={t('registry.field_documentation_url')}
                                            value={editState.form.documentationUrl}
                                            onChange={(v) => setEditState(prev => ({ ...prev, form: { ...prev.form, documentationUrl: v } }))}
                                        />
                                        <EditField
                                            label={t('registry.field_icon_url')}
                                            value={editState.form.iconUrl}
                                            onChange={(v) => setEditState(prev => ({ ...prev, form: { ...prev.form, iconUrl: v } }))}
                                        />
                                    </div>
                                    <p className="text-[11px] text-cm-faint dark:text-zinc-500">
                                        {t('registry.edit_form_hint')}
                                    </p>
                                </>
                            ) : (
                                <textarea
                                    value={editState.jsonText}
                                    onChange={(e) => setEditState(prev => ({ ...prev, jsonText: e.target.value }))}
                                    spellCheck={false}
                                    className="w-full h-full min-h-[320px] font-mono text-[12px] leading-relaxed p-4 rounded-cm bg-cm-canvas dark:bg-zinc-950 border border-cm-line dark:border-zinc-700 text-cm-ink dark:text-zinc-200 outline-none focus:border-cm-primary resize-none"
                                />
                            )}
                        </div>
                        <div className="px-5 py-3.5 border-t border-cm-line dark:border-zinc-800 flex justify-end gap-2 shrink-0">
                            <button
                                onClick={() => setEditState(null)}
                                className="cm-btn dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
                            >
                                {t('common.cancel')}
                            </button>
                            <button
                                onClick={handleSaveEdit}
                                disabled={editState.saving}
                                className="cm-btn-primary"
                            >
                                {editState.saving ? t('registry.saving') : t('registry.save_agent')}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {toast.show && (
                <div className={`fixed top-10 left-1/2 -translate-x-1/2 z-[10000] flex items-center gap-2 px-4 py-2 rounded-cm shadow-modal text-[12px] font-semibold animate-in slide-in-from-top-4 fade-in duration-300
                    ${toast.type === 'success' ? 'bg-emerald-500 text-white' : 'bg-rose-500 text-white'}`}>
                    {toast.type === 'success' ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}
                    {toast.msg}
                </div>
            )}
        </div>
    );
};

const EditField = ({ label, value, onChange, isTextArea }) => (
    <div className="space-y-1.5">
        <label className="text-[11px] font-medium text-cm-muted dark:text-zinc-400">{label}</label>
        {isTextArea ? (
            <textarea
                rows={3}
                value={value || ''}
                onChange={(e) => onChange(e.target.value)}
                className="cm-input h-auto py-2 leading-relaxed resize-none dark:bg-zinc-950 dark:border-zinc-700 dark:text-zinc-200"
            />
        ) : (
            <input
                value={value || ''}
                onChange={(e) => onChange(e.target.value)}
                className="cm-input dark:bg-zinc-950 dark:border-zinc-700 dark:text-zinc-200"
            />
        )}
    </div>
);

export default AgentRegistry;
