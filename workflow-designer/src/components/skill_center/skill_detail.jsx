import { X, Package, Calendar, Tag, User, Shield, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { domainColors } from './mock_data';

const SkillDetail = ({ skill, isDark, onClose }) => {
    const { t } = useTranslation();
    const [showVersions, setShowVersions] = useState(true);
    const domainStyle = domainColors[skill.domain] || domainColors['网'];

    const formatDate = (dateStr) => {
        const date = new Date(dateStr);
        return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
    };

    const statusColor = (status) => {
        switch (status) {
            case 'active': return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400';
            case 'deprecated': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400';
            case 'archived': return 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500 dark:text-zinc-400';
            default: return 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500';
        }
    };

    const riskColor = (level) => {
        switch (level) {
            case 'low': return 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400';
            case 'medium': return 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400';
            case 'high': return 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400';
            default: return 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500';
        }
    };

    const activeVersions = skill.versions.filter(v => v.status === 'active').length;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 bg-black/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white dark:bg-zinc-950 w-full max-w-3xl max-h-[85vh] rounded-[2rem] shadow-2xl border border-zinc-200 dark:border-zinc-800 flex flex-col overflow-hidden animate-in zoom-in-95 duration-300">
                <div className={`p-6 border-b border-zinc-100 dark:border-zinc-800 shrink-0`}>
                    <div className="flex items-start justify-between">
                        <div className="flex items-start gap-4">
                            <div className={`p-3 rounded-xl text-white shadow-lg ${domainStyle.bg}`}>
                                <Package size={24} />
                            </div>
                            <div>
                                <h2 className="text-lg font-black dark:text-white leading-tight">{skill.name}</h2>
                                <div className="flex items-center gap-2 mt-2">
                                    <span className={`px-2 py-0.5 rounded-md text-[10px] font-black ${domainStyle.light} ${domainStyle.text}`}>
                                        {skill.domain}
                                    </span>
                                    <span className="text-[10px] font-bold text-zinc-400 uppercase">{skill.category}</span>
                                    <span className="w-1 h-1 rounded-full bg-zinc-300" />
                                    <span className="text-[10px] font-bold text-zinc-400">{activeVersions}/{skill.versions.length} {t('skills.versions')}</span>
                                </div>
                            </div>
                        </div>
                        <button
                            onClick={onClose}
                            className="p-2 rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                        >
                            <X size={20} className="text-zinc-400" />
                        </button>
                    </div>
                </div>

                <div className="flex-1 overflow-y-auto no-scrollbar p-6 space-y-6">
                    <div>
                        <h3 className="text-xs font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-2">{t('skills.description')}</h3>
                        <p className="text-sm text-zinc-700 dark:text-zinc-300 leading-relaxed">{skill.description}</p>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="flex items-center gap-3 p-3 rounded-xl bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800">
                            <User size={16} className="text-zinc-400" />
                            <div>
                                <span className="text-[10px] font-bold text-zinc-400 uppercase">{t('skills.vendor')}</span>
                                <p className="text-sm font-bold dark:text-white">{skill.vendor.name}</p>
                            </div>
                        </div>
                        <div className="flex items-center gap-3 p-3 rounded-xl bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800">
                            <Shield size={16} className="text-zinc-400" />
                            <div>
                                <span className="text-[10px] font-bold text-zinc-400 uppercase">{t('skills.support_level')}</span>
                                <p className="text-sm font-bold dark:text-white">{skill.vendor.supportLevel}</p>
                            </div>
                        </div>
                    </div>

                    <div>
                        <h3 className="text-xs font-black text-zinc-400 dark:text-zinc-500 uppercase tracking-wider mb-3">{t('skills.tags')}</h3>
                        <div className="flex flex-wrap gap-2">
                            {skill.tags.map(tag => (
                                <span key={tag} className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-bold bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700">
                                    <Tag size={10} />
                                    {tag}
                                </span>
                            ))}
                        </div>
                    </div>

                    <div>
                        <button
                            onClick={() => setShowVersions(!showVersions)}
                            className="w-full flex items-center justify-between p-3 rounded-xl bg-zinc-50 dark:bg-zinc-900 border border-zinc-100 dark:border-zinc-800 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all"
                        >
                            <div className="flex items-center gap-2">
                                <Package size={16} className="text-blue-500" />
                                <span className="text-sm font-black uppercase tracking-wide dark:text-white">
                                    {t('skills.version_history')} ({skill.versions.length})
                                </span>
                            </div>
                            {showVersions
                                ? <ChevronDown size={16} className="text-zinc-400" />
                                : <ChevronRight size={16} className="text-zinc-400" />}
                        </button>
                        {showVersions && (
                            <div className="mt-3 space-y-2 animate-in slide-in-from-top duration-200">
                                {skill.versions.map((v, idx) => (
                                    <div key={idx} className="flex items-center justify-between p-3 rounded-lg border border-zinc-100 dark:border-zinc-800 bg-white dark:bg-zinc-900">
                                        <div className="flex items-center gap-3">
                                            <span className="text-sm font-mono font-bold dark:text-white">v{v.version}</span>
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${statusColor(v.status)}`}>
                                                {t(`skills.status_${v.status}`)}
                                            </span>
                                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${riskColor(v.riskLevel)}`}>
                                                {t(`skills.risk_${v.riskLevel}`)}
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-1 text-[11px] text-zinc-400">
                                            <Calendar size={12} />
                                            {formatDate(v.createdAt)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="flex items-center justify-between pt-4 border-t border-zinc-100 dark:border-zinc-800">
                        <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                            <span>{t('skills.created')}: {formatDate(skill.createdAt)}</span>
                            <span>{t('skills.updated')}: {formatDate(skill.updatedAt)}</span>
                        </div>
                        <span className="text-[10px] font-mono text-zinc-400">{skill.id}</span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SkillDetail;
