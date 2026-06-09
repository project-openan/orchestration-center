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
    ChevronDown,
    ChevronRight
} from 'lucide-react';

const getTheme = (isDark) => ({
    bg: isDark ? 'bg-zinc-950' : 'bg-transparent',
    cardBg: isDark ? 'bg-zinc-900' : 'bg-white',
    border: isDark ? 'border-zinc-800' : 'border-gray-200',
    textPrimary: isDark ? 'text-zinc-100' : 'text-slate-900',
    textSecondary: isDark ? 'text-zinc-400' : 'text-slate-500',
    accent: isDark ? 'text-zinc-200' : 'text-blue-600',
    accentBg: isDark ? 'bg-zinc-800' : 'bg-blue-50',
    success: isDark ? 'text-emerald-500' : 'text-emerald-600',
    skillCardHover: isDark ? 'hover:bg-zinc-800/50' : 'hover:bg-slate-50',
    label: isDark ? 'text-zinc-500' : 'text-slate-400',
    cardBorder: isDark ? 'border-zinc-700/50' : 'border-slate-200/60'
});

const InfoCard = ({ title, icon: Icon, children, className = "", theme }) => (
    <div className={`p-5 rounded-xl border shadow-sm flex flex-col ${theme.cardBg} ${theme.border} ${className}`}>
        <div className="flex items-center gap-2 mb-4 pb-2 border-b border-dashed border-opacity-50"
             style={{ borderColor: theme.border ? undefined : '#e5e7eb' }}>
            {Icon && <Icon className={`w-5 h-5 ${theme.accent}`} />}
            <h3 className={`font-semibold text-xxxl ${theme.textPrimary}`}>{title}</h3>
        </div>
        <div className="flex-1">
            {children}
        </div>
    </div>
);

const StatusRow = ({ label, value, theme, mono = false }) => (
    <div className="flex justify-between items-center py-2 border-b last:border-0 border-dashed border-opacity-50"
         style={{ borderColor: theme.border ? undefined : '#e5e7eb' }}>
        <span className={`text-sm ${theme.textSecondary}`}>{label}</span>
        <span className={`text-sm font-medium ${theme.textPrimary} ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
);

const CapabilityToggle = ({ label, active, icon: Icon, theme }) => {
    const activeBg = active
        ? (theme.cardBg.includes('zinc') ? 'bg-zinc-800/50' : 'bg-blue-50/50')
        : 'opacity-60';

    return (
        <div
            className={`flex items-center justify-between p-3 rounded-lg border transition-all ${theme.border} ${activeBg}`}>
            <div className="flex items-center gap-3">
                <div className={`p-1.5 rounded-md ${active ? theme.accentBg : 'bg-zinc-200 dark:bg-zinc-800'}`}>
                    <Icon className={`w-4 h-4 ${active ? theme.accent : 'text-zinc-500'}`} />
                </div>
                <span className={`text-sm font-medium ${theme.textPrimary}`}>{label}</span>
            </div>
            {active ? (
                <CheckCircle2 className={`w-5 h-5 ${theme.success}`} />
            ) : (
                <XCircle className="w-5 h-5 text-zinc-500 opacity-40" />
            )}
        </div>
    );
};

const SectionHeader = ({ title, icon: Icon, expanded, onToggle, count, isDark }) => (
    <button
        onClick={onToggle}
        className={`w-full flex items-center justify-between px-5 py-3.5 rounded-xl border transition-all duration-200
            ${isDark
                ? 'bg-zinc-900/80 border-zinc-800 hover:bg-zinc-800/80'
                : 'bg-zinc-50 border-zinc-200 hover:bg-zinc-100'}`}
    >
        <div className="flex items-center gap-3">
            <Icon size={18} className={isDark ? 'text-blue-400' : 'text-blue-600'} />
            <span className={`text-sm font-black uppercase tracking-wide ${isDark ? 'text-zinc-200' : 'text-zinc-700'}`}>
                {title}
            </span>
            {count !== undefined && (
                <span className={`px-2 py-0.5 rounded-md text-[10px] font-black
                    ${isDark ? 'bg-zinc-800 text-zinc-400' : 'bg-zinc-200 text-zinc-500'}`}>
                    {count}
                </span>
            )}
        </div>
        {expanded
            ? <ChevronDown size={16} className={isDark ? 'text-zinc-500' : 'text-zinc-400'} />
            : <ChevronRight size={16} className={isDark ? 'text-zinc-500' : 'text-zinc-400'} />}
    </button>
);

const AgentDashboard = ({ agent, isDark }) => {
    const { t } = useTranslation();
    const theme = getTheme(isDark);
    const [basicExpanded, setBasicExpanded] = useState(true);
    const [advancedExpanded, setAdvancedExpanded] = useState(false);

    const renderDescriptionList = (desc) => {
        return (
            <div className={`text-sm leading-relaxed whitespace-pre-wrap ${theme.textSecondary}`}>
                {desc}
            </div>
        );
    };

    return (
        <div className={`w-full ${isDark ? 'bg-zinc-950/50' : 'bg-zinc-50/50'} transition-colors duration-300 p-8`}>
            <div className="space-y-4">
                <SectionHeader
                    title={t('agent_profile.basic')}
                    icon={Fingerprint}
                    expanded={basicExpanded}
                    onToggle={() => setBasicExpanded(!basicExpanded)}
                    count={3}
                    isDark={isDark}
                />

                {basicExpanded && (
                    <div className="space-y-6 animate-in fade-in duration-300 pl-1">
                        <InfoCard
                            title={t('agent_profile.organization')}
                            icon={Globe}
                            theme={theme}
                        >
                            <div className={`text-sm font-semibold ${theme.textPrimary}`}>
                                {agent.provider?.organization || '-'}
                            </div>
                            {agent.provider?.url && (
                                <a
                                    href={agent.provider.url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className={`text-xs mt-1 inline-block ${theme.accent} hover:underline`}
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
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {agent.skills.map((skill, index) => {
                                    const uniqueKey = `skill-${skill.id || 'no-id'}-${skill.name}-${index}`;
                                    return (
                                        <div
                                            key={uniqueKey}
                                            className={`group relative p-4 rounded-lg border transition-all duration-200 ${theme.border} ${theme.skillCardHover}`}>
                                            <div className="flex justify-between items-start mb-2">
                                                <span className={`font-mono text-base font-semibold ${theme.textPrimary}`}>
                                                    {skill.name}
                                                </span>
                                            </div>
                                            <p className={`text-base ${theme.textSecondary} line-clamp-2 mb-3`}>
                                                {skill.description}
                                            </p>
                                            <div className="absolute bottom-[calc(100%-10px)] left-1/2 -translate-x-1/2 invisible opacity-0 translate-y-1
                                                group-hover:visible group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-200 ease-out z-30 w-full min-w-[200px] max-w-[280px]
                                                pointer-events-none">
                                                <div className={`relative px-3 py-2 rounded-lg shadow-xl border text-sm leading-relaxed
                                                    ${isDark ? 'bg-zinc-800 text-slate-200 border-zinc-700' : 'bg-white text-slate-700 border-slate-200'}`}>
                                                    {skill.description}
                                                    <div className={`absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rotate-45 border-b border-r
                                                        ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-slate-200'}`} />
                                                </div>
                                            </div>
                                            <div className="flex flex-wrap gap-2 mt-auto">
                                                {(skill.tags || []).map(tag => (
                                                    <span key={tag}
                                                        className={`text-[10px] px-1.5 py-0.5 rounded border ${theme.border} ${theme.textSecondary}`}>
                                                        {tag}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </InfoCard>
                    </div>
                )}

                <div className="pt-2">
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
                    <div className="animate-in fade-in duration-300 pl-1">
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                            <div className="col-span-1 md:col-span-8 space-y-6">
                                {agent.supportedInterfaces && agent.supportedInterfaces.length > 0 && (
                                    <InfoCard
                                        title={`${t('agent_profile.supported_interfaces')} (${agent.supportedInterfaces.length})`}
                                        icon={Server}
                                        theme={theme}
                                    >
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            {agent.supportedInterfaces.map((iface, index) => (
                                                <div
                                                    key={`interface-${index}`}
                                                    className={`p-4 rounded-lg border transition-all duration-200 ${theme.border} ${theme.skillCardHover}`}>
                                                    <div className="flex justify-between items-start mb-2">
                                                        <span className={`font-mono text-base font-semibold ${theme.textPrimary}`}>
                                                            {iface.protocolBinding}
                                                        </span>
                                                        <span className={`text-[10px] px-1 border rounded ${theme.border} ${theme.textSecondary} opacity-60`}>
                                                            v{iface.protocolVersion}
                                                        </span>
                                                    </div>
                                                    <div className={`text-sm ${theme.textSecondary} truncate font-mono`} title={iface.url}>
                                                        {iface.url}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </InfoCard>
                                )}
                            </div>
                            <div className="col-span-1 md:col-span-4 space-y-6">
                                <InfoCard
                                    title={t('agent_profile.capabilities')}
                                    icon={Cpu}
                                    theme={theme}
                                >
                                    <div className="grid grid-cols-1 gap-3">
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
                                        <div className="pt-4">
                                            <span className={`text-xs uppercase font-semibold tracking-wider ${theme.label}`}>
                                                {t('agent_profile.defaultInputModes')}
                                            </span>
                                            <div className="flex flex-wrap gap-2 mt-2 mb-4">
                                                {agent.defaultInputModes.map(m => (
                                                    <span key={m}
                                                          className={`px-2 py-1 text-xs rounded border ${theme.border} ${theme.textSecondary} bg-opacity-50`}>
                                                        {m}
                                                    </span>
                                                ))}
                                            </div>

                                            <span className={`text-xs uppercase font-semibold tracking-wider ${theme.label}`}>
                                                {t('agent_profile.defaultOutputModes')}
                                            </span>
                                            <div className="flex flex-wrap gap-2 mt-2">
                                                {agent.defaultOutputModes.map(m => (
                                                    <span key={m}
                                                          className={`px-2 py-1 text-xs rounded border ${theme.border} ${theme.textSecondary} bg-opacity-50`}>
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
                                            className={`mt-6 flex items-center justify-center gap-2 w-full py-2 rounded-lg text-sm font-medium transition-colors ${isDark
                                                ? 'bg-blue-600/20 hover:bg-blue-600/30 text-blue-400'
                                                : 'bg-blue-50 hover:bg-blue-100 text-blue-700'
                                            }`}
                                        >
                                            <Globe className="w-4 h-4" />
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
