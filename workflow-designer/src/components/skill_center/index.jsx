import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Package, Layers, Server, Wrench } from 'lucide-react';
import { mockSkills } from './mock_data';
import SkillDetail from './skill_detail';

const TABS = ['all', 'service', 'common'];

const SkillCenter = ({ isDark }) => {
    const { t } = useTranslation();
    const [keyword, setKeyword] = useState('');
    const [activeTab, setActiveTab] = useState('all');
    const [selectedSkill, setSelectedSkill] = useState(null);

    const filteredSkills = useMemo(() => {
        let result = mockSkills;
        if (keyword) {
            const term = keyword.toLowerCase();
            result = result.filter(s =>
                s.name.toLowerCase().includes(term) ||
                s.description.toLowerCase().includes(term) ||
                s.tags.some(tag => tag.toLowerCase().includes(term))
            );
        }
        if (activeTab === 'service') {
            result = result.filter(s => s.category === 'ServiceLayer');
        } else if (activeTab === 'common') {
            result = result.filter(s => s.category === 'Common');
        }
        return result;
    }, [keyword, activeTab]);

    const tabCounts = useMemo(() => ({
        all: mockSkills.length,
        service: mockSkills.filter(s => s.category === 'ServiceLayer').length,
        common: mockSkills.filter(s => s.category === 'Common').length,
    }), []);

    const themeColor = (domain) => {
        const map = {
            '网': 'bg-indigo-500',
            '云': 'bg-emerald-500',
            '维': 'bg-amber-500',
            '算': 'bg-violet-500',
            '营': 'bg-rose-500'
        };
        return map[domain] || 'bg-blue-600';
    };

    const themeBorder = (domain) => {
        const map = {
            '网': 'hover:border-indigo-300 dark:hover:border-indigo-700',
            '云': 'hover:border-emerald-300 dark:hover:border-emerald-700',
            '维': 'hover:border-amber-300 dark:hover:border-amber-700',
            '算': 'hover:border-violet-300 dark:hover:border-violet-700',
            '营': 'hover:border-rose-300 dark:hover:border-rose-700'
        };
        return map[domain] || 'hover:border-blue-300';
    };

    const renderCard = (skill) => {
        const activeVersions = skill.versions.filter(v => v.status === 'active').length;
        return (
            <div
                key={skill.id}
                onClick={() => setSelectedSkill(skill)}
                className={`group relative p-6 rounded-2xl border cursor-pointer transition-all duration-300
                    bg-white dark:bg-zinc-900 border-zinc-100 dark:border-zinc-800
                    ${themeBorder(skill.domain)}
                    hover:shadow-lg hover:-translate-y-1 animate-in fade-in duration-300`}
            >
                <div className="flex items-start justify-between mb-4">
                    <div className={`p-3 rounded-xl text-white shadow-lg ${themeColor(skill.domain)}`}>
                        <Package size={22} />
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_6px_#10b981]" />
                        <span className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase">
                            {activeVersions}/{skill.versions.length} {t('skills.ver')}
                        </span>
                    </div>
                </div>

                <h3 className="text-sm font-black text-zinc-900 dark:text-white mb-2 leading-tight truncate">
                    {skill.name}
                </h3>
                <p className="text-[11px] text-zinc-500 dark:text-zinc-400 line-clamp-2 mb-4 leading-relaxed min-h-[2.5em]">
                    {skill.description}
                </p>

                <div className="flex flex-wrap gap-1.5 mb-4">
                    {skill.tags.slice(0, 3).map(tag => (
                        <span key={tag}
                            className="px-2 py-0.5 rounded-md text-[9px] font-bold bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-700">
                            {tag}
                        </span>
                    ))}
                    {skill.tags.length > 3 && (
                        <span className="px-2 py-0.5 rounded-md text-[9px] font-bold text-zinc-400 dark:text-zinc-500">
                            +{skill.tags.length - 3}
                        </span>
                    )}
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-zinc-100 dark:border-zinc-800">
                    <span className="text-[10px] font-black text-zinc-400 dark:text-zinc-500 uppercase">
                        {skill.vendor.name}
                    </span>
                    <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500">
                        {skill.domain}
                    </span>
                </div>
            </div>
        );
    };

    return (
        <div className="h-full p-6 flex flex-col w-full transition-all animate-in fade-in duration-500 overflow-hidden font-sans">
            <div className="shrink-0 flex items-center justify-between mb-6 px-2">
                <div className="flex items-center gap-4">
                    <div className="p-2.5 bg-zinc-900 dark:bg-violet-600 rounded-xl text-white shadow-lg">
                        <Layers size={20} />
                    </div>
                    <div>
                        <h1 className="text-lg font-black text-zinc-900 dark:text-white uppercase leading-none">
                            {t('skills.title')}
                        </h1>
                        <span className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase">
                            {mockSkills.length} {t('skills.total_skills')}
                        </span>
                    </div>
                </div>
                <div className="relative w-72">
                    <input
                        type="text"
                        placeholder={t('skills.search_placeholder')}
                        className="w-full pl-10 pr-4 py-2.5 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-xl text-sm font-bold focus:ring-2 focus:ring-violet-500/20 focus:border-violet-400 outline-none transition-all dark:text-white"
                        onChange={(e) => setKeyword(e.target.value)}
                        value={keyword}
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
                        {tab === 'service' && <Server size={14} />}
                        {tab === 'common' && <Wrench size={14} />}
                        {t(`skills.tab_${tab}`)}
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
                {filteredSkills.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-zinc-400 gap-3">
                        <Package size={48} strokeWidth={1.5} />
                        <p className="text-sm font-bold uppercase tracking-wider">{t('skills.no_skills')}</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 pb-8">
                        {filteredSkills.map(renderCard)}
                    </div>
                )}
            </div>

            {selectedSkill && (
                <SkillDetail
                    skill={selectedSkill}
                    isDark={isDark}
                    onClose={() => setSelectedSkill(null)}
                />
            )}
        </div>
    );
};

export default SkillCenter;
