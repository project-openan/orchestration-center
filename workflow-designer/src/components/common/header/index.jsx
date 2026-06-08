import {Bot, Sun, Moon, LayoutDashboard, Share2, PlayCircle, Sparkles} from "lucide-react";

const Header = ({currentTab, onTabChange, isDark, setIsDark, lang, onLangChange, t}) => {
    return (
        <nav
            className="h-16 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800 px-8 flex justify-between items-center shrink-0 z-20 transition-all">
            <div className="flex items-center gap-4">
                <div className="bg-zinc-900 dark:bg-blue-600 p-2 rounded-xl text-white shadow-lg transition-all">
                    <Bot size={22}/>
                </div>
                <h1 className="text-lg font-black tracking-tighter antialiased text-zinc-900 dark:text-zinc-100">
                    {t('nav.title')}
                </h1>
            </div>
            <div
                className="flex items-center bg-zinc-100 dark:bg-zinc-800 p-1.5 rounded-2xl border border-zinc-200 dark:border-zinc-700 shadow-inner">
                <button onClick={() => onTabChange('agents')}
                        className={`flex items-center gap-3 px-6 py-2 rounded-xl text-sm font-black transition-all duration-300 ${
                            currentTab === 'agents'
                                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-md scale-[1.02]'
                                : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}>
                    <LayoutDashboard size={16}/>
                    {t('nav.tabs.agents')}
                </button>
                <button onClick={() => onTabChange('orchestration')}
                        className={`flex items-center gap-3 px-6 py-2 rounded-xl text-sm font-black transition-all duration-300 ${
                            currentTab === 'orchestration'
                                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-md scale-[1.02]'
                                : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}>
                    <Share2 size={16}/>
                    {t('nav.tabs.orchestration')}
                </button>
                <button onClick={() => onTabChange('execution')}
                        className={`flex items-center gap-3 px-6 py-2 rounded-xl text-sm font-black transition-all duration-300 ${
                            currentTab === 'execution'
                                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-md scale-[1.02]'
                                : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}>
                    <PlayCircle size={16}/>
                    {t('nav.tabs.execution')}
                </button>
                <button onClick={() => onTabChange('skills')}
                        className={`flex items-center gap-3 px-6 py-2 rounded-xl text-sm font-black transition-all duration-300 ${
                            currentTab === 'skills'
                                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-md scale-[1.02]'
                                : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}>
                    <Sparkles size={16}/>
                    {t('nav.tabs.skills')}
                </button>
            </div>
            <div className="flex items-center gap-6">
                <button onClick={() => setIsDark(!isDark)}
                        className="p-2.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all">
                    {isDark ? <Sun size={20} className="text-amber-400"/> :
                        <Moon size={20} className="text-zinc-500"/>}
                </button>
                <div
                    className="flex bg-zinc-100 dark:bg-zinc-800 p-1 rounded-full border border-zinc-200 dark:border-zinc-700 shadow-inner ">
                    <button onClick={() => onLangChange('zh')}
                            className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${lang === 'zh' ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm' : 'text-zinc-400'}`}>
                        中
                    </button>
                    <button onClick={() => onLangChange('en')}
                            className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${lang === 'en' ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm' : 'text-zinc-400'}`}>
                        EN
                    </button>
                </div>
            </div>
        </nav>
    )
}

export default Header;