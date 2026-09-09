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
import {useState} from "react";
import {Sun, Moon, LayoutDashboard, Share2, PlayCircle, Sparkles, Settings} from "lucide-react";
import SettingsModal from "../setting/index.jsx";
import openanLogo from "../../../assets/openan-logo.png";

const Header = ({currentTab, onTabChange, isDark, setIsDark, lang, onLangChange, t}) => {
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    return (
        <>
        <nav
            className="h-16 bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md border-b border-zinc-200 dark:border-zinc-800 px-8 flex justify-between items-center shrink-0 z-20 transition-all">
            <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-lg bg-white p-1 flex items-center justify-center shrink-0">
                    <img src={openanLogo} alt="OpenAN" className="w-full h-full object-contain"/>
                </div>
                <div className="flex flex-col">
                    <span className="text-xl font-medium tracking-tight text-zinc-900 dark:text-zinc-100 leading-tight">
                        Open<span className="text-blue-500">AN</span>
                    </span>
                    <span className="text-xs tracking-widest uppercase text-zinc-400 dark:text-zinc-500 leading-tight">
                        Open Autonomous Networks
                    </span>
                </div>
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
                <Settings size={20} onClick={() => setIsSettingsOpen(true)}
                          className={"text-zinc-400 cursor-pointer hover:rotate-90 transition-all duration-500"}/>
            </div>
        </nav>
        <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} t={t}/>
        </>
    )
}

export default Header;