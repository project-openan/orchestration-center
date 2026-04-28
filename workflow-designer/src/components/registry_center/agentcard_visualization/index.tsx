import { useTranslation } from 'react-i18next';
import {
    Server,
    Globe,
    Activity,
    Box,
    Terminal,
    CheckCircle2,
    XCircle,
    Zap,
    Layers,
    Cpu,
    Fingerprint,
    Settings
} from 'lucide-react';

interface AgentCapability {
    extensions: any;
    pushNotifications: boolean;
    stateTransitionHistory: boolean;
    streaming: boolean;
}

interface AgentSkill {
    id: string;
    name: string;
    description: string;
    inputModes: string[] | null;
    outputModes: string[] | null;
}

interface SupportedInterface {
    protocol_binding: string;
    protocol_version: string;
    url: string;
}

interface AgentProvider {
    organization: string;
    url: string;
}

interface AgentData {
    name: string;
    version: string;
    description: string;
    protocolVersion: string;
    preferredTransport: string;
    provider: AgentProvider;
    url: string;
    capabilities: AgentCapability;
    defaultInputModes: string[];
    defaultOutputModes: string[];
    skills: AgentSkill[];
    supported_interfaces?: SupportedInterface[];
    documentationUrl?: string;
    [key: string]: any;
}

interface AgentProfileProps {
    agent: AgentData;
    isDark: boolean;
}

const getTheme = (isDark: boolean) => ({
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

const InfoCard = ({ title, icon: Icon, children, className = "", theme }: any) => (
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

const StatusRow = ({ label, value, theme, mono = false }: any) => (
    <div className="flex justify-between items-center py-2 border-b last:border-0 border-dashed border-opacity-50"
         style={{ borderColor: theme.border ? undefined : '#e5e7eb' }}>
        <span className={`text-sm ${theme.textSecondary}`}>{label}</span>
        <span className={`text-sm font-medium ${theme.textPrimary} ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
);

const CapabilityToggle = ({ label, active, icon: Icon, theme }: any) => {
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

const AgentDashboard: React.FC<AgentProfileProps> = ({ agent, isDark }) => {
    console.log('AgentDashboard', agent)
    const { t } = useTranslation();
    const theme = getTheme(isDark);

    const renderDescriptionList = (desc: string) => {
        return (
            <div className={`text-sm leading-relaxed whitespace-pre-wrap ${theme.textSecondary}`}>
                {desc}
            </div>
        );
    };

    return (
        <div className={`w-full min-h-screen ${isDark ? 'bg-zinc-950/50' : 'bg-zinc-50/50'} transition-colors duration-300 p-8`}>
            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                <div className="col-span-1 md:col-span-8 space-y-6">
                    <InfoCard
                        title={t('agent_profile.description')}
                        icon={Fingerprint}
                        theme={theme}
                    >
                        <ul className="space-y-1">
                            {renderDescriptionList(agent.description)}
                        </ul>
                    </InfoCard>

                    {agent.supported_interfaces && agent.supported_interfaces.length > 0 && (
                        <InfoCard
                            title={`${t('agent_profile.supported_interfaces')} (${agent.supported_interfaces.length})`}
                            icon={Server}
                            theme={theme}
                        >
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {agent.supported_interfaces.map((iface, index) => (
                                    <div
                                        key={`interface-${index}`}
                                        className={`p-4 rounded-lg border transition-all duration-200 ${theme.border} ${theme.skillCardHover}`}>
                                        <div className="flex justify-between items-start mb-2">
                                            <span className={`font-mono text-base font-semibold ${theme.textPrimary}`}>
                                                {iface.protocol_binding}
                                            </span>
                                            <span className={`text-[10px] px-1 border rounded ${theme.border} ${theme.textSecondary} opacity-60`}>
                                                v{iface.protocol_version}
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
                    <InfoCard
                        title={`${t('agent_profile.skills')} (${agent.skills.length})`}
                        icon={Terminal}
                        theme={theme}
                    >
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {agent.skills
                                .map((skill, index) => {
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
                                            <div className="absolute bottom-[calc(100%-10px)] left-1/2 -translate-x-1/2  invisible opacity-0 translate-y-1
      group-hover:visible group-hover:opacity-100 group-hover:translate-y-0 transition-all duration-200 ease-out z-30 w-full min-w-[200px] max-w-[280px]
      pointer-events-none
    ">
                                                <div className={`relative px-3 py-2 rounded-lg shadow-xl border text-sm leading-relaxed
        ${isDark ? 'bg-zinc-800 text-slate-200 border-zinc-700' : 'bg-white text-slate-700 border-slate-200'}
      `}>
                                                    {skill.description}

                                                    <div className={`
          absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 rotate-45 border-b border-r
          ${isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-slate-200'}
        `} />
                                                </div>
                                            </div>
                                            <div className="flex flex-wrap gap-2 mt-auto">
                                                {skill.inputModes?.map(m => (
                                                    <span key={m}
                                                          className={`text-[10px] opacity-60 px-1 border rounded ${theme.border} ${theme.textSecondary}`}>
                                                        IN: {m}
                                                    </span>
                                                ))}
                                            </div>
                                        </div>
                                    )
                                })}
                        </div>
                    </InfoCard>
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
                                    {agent.default_input_modes.map(m => (
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
                                    {agent.default_output_modes.map(m => (
                                        <span key={m}
                                              className={`px-2 py-1 text-xs rounded border ${theme.border} ${theme.textSecondary} bg-opacity-50`}>
                                            {m}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        </div>
                        {agent.documentation_url && (
                            <a
                                href={agent.documentation_url}
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
    );
};

export default AgentDashboard;