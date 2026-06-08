import {useTranslation} from "react-i18next";
import {useEffect, useState} from "react";
import Header from "@/components/common/header/index.jsx";
import AgentRegistry from "./components/registry_center/index.jsx";
import OrchestrationCenter from "@/components/orchestration_center/index.jsx";
import ExecutionCenter from "@/components/execution_center/index.jsx";
import SkillCenter from "@/components/skill_center/index.jsx";
import {ErrorBoundary} from "@/components/common/error_boundary/index.jsx";

const MainContainer = () => {
    const {t, i18n} = useTranslation();

    const [isDark, setIsDark] = useState(() => {
        const savedTheme = localStorage.getItem('theme');
        return (savedTheme || 'dark') === 'dark';
    });

    const [activeTab, setActiveTab] = useState(() => {
        return localStorage.getItem('activeTab') || 'orchestration'
    });

    const handleLangChange = (l) => {
        i18n.changeLanguage(l);
        localStorage.setItem('lang', l);
    }

    useEffect(() => {
        const root = window.document.documentElement;
        if (isDark) {
            root.classList.add('dark');
            root.style.colorScheme = 'dark';
            localStorage.setItem('theme', 'dark');
        } else {
            root.classList.remove('dark');
            root.style.colorScheme = 'light';
            localStorage.setItem('theme', 'light');
        }
    }, [isDark]);

    useEffect(() => {
        localStorage.setItem('activeTab', activeTab);
    }, [activeTab]);

    useEffect(() => {
        const lang = localStorage.getItem('lang') || 'en';
        if (lang !== i18n.language) {
            i18n.changeLanguage(lang);
        }
    }, []);

    return (
        <div className="h-screen flex flex-col bg-zinc-50 dark:bg-[#09090B] overflow-hidden font-sans text-lg transition-colors duration-500">
            <Header
                currentTab={activeTab}
                onTabChange={setActiveTab}
                isDark={isDark}
                setIsDark={setIsDark}
                lang={i18n.language}
                onLangChange={handleLangChange}
                t={t}
            />

            <main className="flex-1 min-h-0 relative overflow-hidden">
                <div className={`h-full w-full ${activeTab === 'agents' ? 'relative z-10 visible animate-in' : 'absolute invisible -left-[9999px] -top-[9999px]'}`}>
                    <ErrorBoundary><AgentRegistry isDark={isDark} t={t}/></ErrorBoundary>
                </div>

                <div className={`h-full w-full ${activeTab === 'orchestration' ? 'relative z-10 visible animate-in' : 'absolute invisible -left-[9999px] -top-[9999px]'}`}>
                    <ErrorBoundary><OrchestrationCenter isDark={isDark}/></ErrorBoundary>
                </div>

                <div className={`h-full w-full ${activeTab === 'execution' ? 'relative z-10 visible animate-in' : 'absolute invisible -left-[9999px] -top-[9999px]'}`}>
                    <ErrorBoundary><ExecutionCenter isDark={isDark}/></ErrorBoundary>
                </div>

                <div className={`h-full w-full ${activeTab === 'skills' ? 'relative z-10 visible animate-in' : 'absolute invisible -left-[9999px] -top-[9999px]'}`}>
                    <ErrorBoundary><SkillCenter isDark={isDark}/></ErrorBoundary>
                </div>
            </main>
        </div>
    )
}

export default MainContainer;