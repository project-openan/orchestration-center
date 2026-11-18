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
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
    Server,
    Globe,
    Activity,
    Terminal,
    CheckCircle2,
    XCircle,
    Zap,
    Layers,
    Cpu,
    Fingerprint,
    Settings,
    Shield,
    Puzzle,
    ChevronDown,
    ChevronRight
} from 'lucide-react';

const getTheme = (isDark) => ({
    bg: isDark ? 'bg-cm-night/40' : 'bg-cm-canvas',
    cardBg: isDark ? 'bg-zinc-900' : 'bg-white',
    border: isDark ? 'border-zinc-800' : 'border-cm-line',
    divider: isDark ? 'border-zinc-800' : 'border-cm-line-soft',
    textPrimary: isDark ? 'text-zinc-100' : 'text-cm-ink',
    textSecondary: isDark ? 'text-zinc-400' : 'text-cm-secondary',
    accent: isDark ? 'text-blue-400' : 'text-cm-primary',
    accentBg: isDark ? 'bg-zinc-800' : 'bg-cm-primary-faint',
    chipBg: isDark ? 'bg-zinc-800' : 'bg-cm-tint',
    chipText: isDark ? 'text-blue-300' : 'text-[#255BCE]',
    success: isDark ? 'text-emerald-400' : 'text-emerald-600',
    skillCardHover: isDark ? 'hover:bg-zinc-800/50' : 'hover:bg-cm-primary-soft',
    label: isDark ? 'text-zinc-500' : 'text-cm-faint',
    cardBorder: isDark ? 'border-zinc-700/50' : 'border-cm-line'
});

const InfoCard = ({ title, icon: Icon, children, className = "", theme }) => (
    <div className={`p-4 rounded-cm border shadow-card flex flex-col ${theme.cardBg} ${theme.border} ${className}`}>
        <div className={`flex items-center gap-2 mb-3 pb-2.5 border-b ${theme.divider}`}>
            {Icon && <Icon className={`w-4 h-4 ${theme.accent}`} />}
            <h3 className={`text-[13px] font-bold ${theme.textPrimary}`}>{title}</h3>
        </div>
        <div className="flex-1">
            {children}
        </div>
    </div>
);

const StatusRow = ({ label, value, theme, mono = false }) => (
    <div className={`flex justify-between items-center py-2 border-b last:border-0 ${theme.divider}`}>
        <span className={`text-[13px] ${theme.textSecondary}`}>{label}</span>
        <span className={`text-[13px] font-medium ${theme.textPrimary} ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
);

const CapabilityToggle = ({ label, active, icon: Icon, theme }) => {
    const activeBg = active
        ? 'bg-cm-primary-soft border-cm-primary-faint dark:bg-zinc-800/60 dark:border-zinc-700'
        : `opacity-60 ${theme.border}`;

    return (
        <div
            className={`flex items-center justify-between p-2.5 rounded-cm-sm border transition-colors ${activeBg}`}>
            <div className="flex items-center gap-2.5">
                <div className={`grid place-items-center w-[26px] h-[26px] rounded-cm-sm ${active ? theme.accentBg : 'bg-cm-canvas dark:bg-zinc-800'}`}>
                    <Icon className={`w-3.5 h-3.5 ${active ? theme.accent : 'text-cm-faint dark:text-zinc-500'}`} />
                </div>
                <span className={`text-[13px] font-medium ${theme.textPrimary}`}>{label}</span>
            </div>
            {active ? (
                <CheckCircle2 className={`w-4 h-4 ${theme.success}`} />
            ) : (
                <XCircle className="w-4 h-4 text-cm-faint dark:text-zinc-600" />
            )}
        </div>
    );
};

const SectionHeader = ({ title, icon: Icon, expanded, onToggle, count, isDark }) => (
    <button
        onClick={onToggle}
        className={`w-full flex items-center justify-between px-4 py-3 rounded-cm border transition-colors duration-150
            ${isDark
                ? 'bg-zinc-900 border-zinc-800 hover:border-zinc-700'
                : 'bg-white border-cm-line hover:border-[#B8CFFC]'}`}
    >
        <div className="flex items-center gap-2.5">
            <Icon size={16} className={isDark ? 'text-blue-400' : 'text-cm-primary'} />
            <span className={`text-[13px] font-bold ${isDark ? 'text-zinc-200' : 'text-cm-heading'}`}>
                {title}
            </span>
            {count !== undefined && (
                <span className={`px-1.5 py-[1px] rounded-[5px] text-[10px] font-semibold
                    ${isDark ? 'bg-zinc-800 text-zinc-400' : 'bg-cm-tint text-[#255BCE]'}`}>
                    {count}
                </span>
            )}
        </div>
        {expanded
            ? <ChevronDown size={15} className={isDark ? 'text-zinc-500' : 'text-cm-faint'} />
            : <ChevronRight size={15} className={isDark ? 'text-zinc-500' : 'text-cm-faint'} />}
    </button>
);

const AgentDashboard = ({ agent, isDark }) => {
    const { t } = useTranslation();
    const theme = getTheme(isDark);
    const [basicExpanded, setBasicExpanded] = useState(true);
    const [advancedExpanded, setAdvancedExpanded] = useState(false);

    const renderDescriptionList = (desc) => {
        return (
            <div className={`text-[13px] leading-[1.7] whitespace-pre-wrap ${theme.textSecondary}`}>
                {desc}
            </div>
        );
    };

    return (
        <div className={`w-full ${theme.bg} transition-colors duration-300 p-6`}>
            <div className="space-y-3">
                <SectionHeader
                    title={t('agent_profile.basic')}
                    icon={Fingerprint}
                    expanded={basicExpanded}
                    onToggle={() => setBasicExpanded(!basicExpanded)}
                    count={3}
                    isDark={isDark}
                />

                {basicExpanded && (
                    <div className="space-y-3 animate-in fade-in duration-300">
                        <InfoCard
                            title={t('agent_profile.organization')}
                            icon={Globe}
                            theme={theme}
                        >
                            <div className={`text-[13px] font-semibold ${theme.textPrimary}`}>
                                {agent.provider?.organization || '-'}
                            </div>
                            {agent.provider?.url && (
                                <a
                                    href={agent.provider.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className={`text-[11px] mt-1 inline-block truncate max-w-full ${theme.accent} hover:underline`}
                                >
                                    {agent.provider.url}
                                </a>
                            )}
                        </InfoCard>

                        <InfoCard
                            title={t('agent_profile.description')}
                            icon={Fingerprint}
                            theme={theme}
                        >
                            {renderDescriptionList(agent.description)}
                        </InfoCard>

                        <InfoCard
                            title={`${t('agent_profile.skills')} (${agent.skills.length})`}
                            icon={Terminal}
                            theme={theme}
                        >
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                {agent.skills.map((skill, index) => {
                                    const uniqueKey = `skill-${skill.id || 'no-id'}-${skill.name}-${index}`;
                                    return (
                                        <div
                                            key={uniqueKey}
                                            className={`group relative p-3.5 rounded-cm border transition-colors duration-200 ${theme.border} ${theme.skillCardHover}`}>
                                            <div className="flex justify-between items-start mb-1.5">
                                                <span className={`font-mono text-[13px] font-semibold truncate ${theme.textPrimary}`}>
                                                    {skill.name}
                                                </span>
                                            </div>
                                            <p className={`text-[12px] leading-[1.6] ${theme.textSecondary} line-clamp-2 mb-2.5`}>
                                                {skill.description}
                                            </p>
                                            <div className="absolute bottom-[calc(100%-10px)] left-1/2 -translate-x-1/2 invisible opacity-0 translate-y-1
                                                group-hover:visible group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-200 ease-out z-30 w-full min-w-[200px] max-w-[280px]
                                                pointer-events-none">
                                                <div className={`relative px-3 py-2 rounded-cm shadow-panel border text-[12px] leading-relaxed
                                                    ${isDark ? 'bg-zinc-800 text-zinc-200 border-zinc-700' : 'bg-white text-cm-ink border-cm-line'}`}>
                                                    {skill.description}
                                                    <div className={`absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rotate-45 border-b border-r
                                                        ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-cm-line'}`} />
                                                </div>
                                            </div>
                                            <div className="flex flex-wrap gap-1.5 mt-auto">
                                                {(skill.tags || []).map(tag => (
                                                    <span key={tag}
                                                        className={`text-[10px] px-1.5 py-0.5 rounded-[5px] ${theme.chipBg} ${theme.chipText}`}>
                                                        {tag}
                                                    </span>
                                                ))}
                                            </div>
                                            {(skill.examples || []).length > 0 && (
                                                <details className="mt-2.5">
                                                    <summary className={`text-[11px] cursor-pointer ${theme.textSecondary} hover:text-cm-primary dark:hover:text-blue-400`}>
                                                        {`示例 (${skill.examples.length})`}
                                                    </summary>
                                                    <div className={`mt-2 space-y-2 max-h-60 overflow-y-auto custom-scrollbar text-[11px] leading-relaxed font-mono whitespace-pre-wrap p-2 rounded-cm-sm border
                                                        ${isDark ? 'bg-zinc-950 border-zinc-800 text-zinc-300' : 'bg-cm-canvas border-cm-line-soft text-cm-secondary'}`}>
                                                        {skill.examples.map((example, i) => (
                                                            <div key={i} className={`pb-2 border-b last:border-b-0 last:pb-0 ${isDark ? 'border-zinc-800' : 'border-cm-line-soft'}`}>
                                                                {example}
                                                            </div>
                                                        ))}
                                                    </div>
                                                </details>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                        </InfoCard>
                    </div>
                )}

                <div className="pt-1">
                    <SectionHeader
                        title={t('agent_profile.advanced')}
                        icon={Settings}
                        expanded={advancedExpanded}
                        onToggle={() => setAdvancedExpanded(!advancedExpanded)}
                        count={3}
                        isDark={isDark}
                    />
                </div>

                {advancedExpanded && (
                    <div className="animate-in fade-in duration-300">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-3">
                            <div className="col-span-1 md:col-span-8 space-y-3">
                                {agent.supportedInterfaces && agent.supportedInterfaces.length > 0 && (
                                    <InfoCard
                                        title={`${t('agent_profile.supported_interfaces')} (${agent.supportedInterfaces.length})`}
                                        icon={Server}
                                        theme={theme}
                                    >
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                            {agent.supportedInterfaces.map((iface, index) => (
                                                <div
                                                    key={`interface-${index}`}
                                                    className={`p-3.5 rounded-cm border transition-colors duration-200 ${theme.border} ${theme.skillCardHover}`}>
                                                    <div className="flex justify-between items-start mb-1.5 gap-2">
                                                        <span className={`font-mono text-[13px] font-semibold truncate ${theme.textPrimary}`}>
                                                            {iface.protocolBinding}
                                                        </span>
                                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-[5px] shrink-0 ${theme.chipBg} ${theme.chipText}`}>
                                                            v{iface.protocolVersion}
                                                        </span>
                                                    </div>
                                                    <div className={`text-[11px] font-mono truncate ${theme.textSecondary}`} title={iface.url}>
                                                        {iface.url}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </InfoCard>
                                )}
                            </div>
                            <div className="col-span-1 md:col-span-4 space-y-3">
                                <InfoCard
                                    title={t('agent_profile.capabilities')}
                                    icon={Cpu}
                                    theme={theme}
                                >
                                    <div className="grid grid-cols-1 gap-2">
                                        <CapabilityToggle
                                            label={t('agent_profile.streaming')}
                                            active={agent.capabilities.streaming}
                                            icon={Activity}
                                            theme={theme}
                                        />
                                        <CapabilityToggle
                                            label={t('agent_profile.stateTransitionHistory')}
                                            active={agent.capabilities.stateTransitionHistory}
                                            icon={Layers}
                                            theme={theme}
                                        />
                                        <CapabilityToggle
                                            label={t('agent_profile.pushNotifications')}
                                            active={agent.capabilities.pushNotifications}
                                            icon={Zap}
                                            theme={theme}
                                        />
                                    </div>
                                </InfoCard>
                                {agent.securitySchemes && Object.keys(agent.securitySchemes).length > 0 && (
                                    <InfoCard
                                        title={t('agent_profile.security')}
                                        icon={Shield}
                                        theme={theme}
                                    >
                                        <div className="space-y-2">
                                            {Object.entries(agent.securitySchemes).map(([name, scheme]) => (
                                                <div key={name}
                                                    className={`flex items-center justify-between gap-2 p-2 rounded-cm-sm border ${theme.border}`}>
                                                    <div className="flex items-center gap-2 min-w-0">
                                                        <Shield className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                                                        <span className={`text-[13px] font-mono font-medium truncate ${theme.textPrimary}`}>{name}</span>
                                                    </div>
                                                    <span className={`text-[10px] px-1.5 py-0.5 rounded-[5px] shrink-0 ${theme.chipBg} ${theme.chipText}`}>
                                                        {scheme.httpAuthSecurityScheme?.scheme || scheme.scheme || 'N/A'}
                                                    </span>
                                                </div>
                                            ))}
                                        </div>
                                    </InfoCard>
                                )}
                                {agent.capabilities?.extensions && agent.capabilities.extensions.length > 0 && (
                                    <InfoCard
                                        title={t('agent_profile.extensions')}
                                        icon={Puzzle}
                                        theme={theme}
                                    >
                                        <div className="space-y-2">
                                            {agent.capabilities.extensions.map((ext, idx) => (
                                                <div key={idx}
                                                    className={`p-2 rounded-cm-sm border ${theme.border}`}>
                                                    <div className={`text-[11px] font-mono truncate ${theme.textSecondary}`}
                                                        title={ext.uri}>
                                                        {ext.uri}
                                                    </div>
                                                    {ext.required !== undefined && (
                                                        <span className={`text-[10px] ${ext.required ? 'text-amber-600 dark:text-amber-400' : 'text-cm-faint dark:text-zinc-500'}`}>
                                                            {ext.required ? 'required' : 'optional'}
                                                        </span>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </InfoCard>
                                )}
                                <InfoCard
                                    title={t('agent_profile.configuration')}
                                    icon={Settings}
                                    theme={theme}
                                >
                                    <div className="space-y-1">
                                        <StatusRow
                                            label={t('agent_profile.protocolVersion')}
                                            value={`v${agent.version}`}
                                            theme={theme}
                                        />
                                        <div className="pt-3">
                                            <span className={`text-[10px] uppercase font-semibold tracking-wider ${theme.label}`}>
                                                {t('agent_profile.defaultInputModes')}
                                            </span>
                                            <div className="flex flex-wrap gap-1.5 mt-2 mb-3">
                                                {agent.defaultInputModes.map(m => (
                                                    <span key={m}
                                                          className={`px-1.5 py-0.5 text-[10px] rounded-[5px] ${theme.chipBg} ${theme.chipText}`}>
                                                        {m}
                                                    </span>
                                                ))}
                                            </div>

                                            <span className={`text-[10px] uppercase font-semibold tracking-wider ${theme.label}`}>
                                                {t('agent_profile.defaultOutputModes')}
                                            </span>
                                            <div className="flex flex-wrap gap-1.5 mt-2">
                                                {agent.defaultOutputModes.map(m => (
                                                    <span key={m}
                                                          className={`px-1.5 py-0.5 text-[10px] rounded-[5px] ${theme.chipBg} ${theme.chipText}`}>
                                                        {m}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    </div>
                                    {agent.documentationUrl && (
                                        <a
                                            href={agent.documentationUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            className={`mt-4 flex items-center justify-center gap-2 w-full py-2 rounded-cm-sm text-[12px] font-semibold transition-colors ${isDark
                                                ? 'bg-zinc-800 hover:bg-zinc-700 text-blue-300'
                                                : 'bg-cm-primary-faint hover:bg-[#E0ECFF] text-[#245FCA]'
                                            }`}
                                        >
                                            <Globe className="w-3.5 h-3.5" />
                                            {t('agent_profile.documentationUrl')}
                                        </a>
                                    )}
                                </InfoCard>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default AgentDashboard;
