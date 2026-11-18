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
//    distributed under the License is distributed on an "AS IS" BASIS,
//    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//    See the License for the specific language governing permissions and
//    limitations under the License.
import {useState} from "react";
import {Sun, Moon, LayoutDashboard, Share2, PlayCircle, Sparkles, Settings, LogOut, KeyRound} from "lucide-react";
import PasswordChangeModal from "../password_change/index.jsx";
import SettingsModal from "../setting/index.jsx";
import {BrandLockup} from "../brand/index.jsx";

const TABS = [
    {key: 'agents', icon: LayoutDashboard, label: 'nav.tabs.agents'},
    {key: 'orchestration', icon: Share2, label: 'nav.tabs.orchestration'},
    {key: 'execution', icon: PlayCircle, label: 'nav.tabs.execution'},
    {key: 'skills', icon: Sparkles, label: 'nav.tabs.skills'},
];

const Header = ({currentTab, onTabChange, isDark, setIsDark, lang, onLangChange, t, onLogout, currentUser}) => {
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [isPasswordChangeOpen, setIsPasswordChangeOpen] = useState(false);

    const displayName = currentUser || 'admin';
    const initial = displayName.trim().charAt(0).toUpperCase() || 'A';

    return (
        <>
            <nav
                className="h-[65px] min-h-[65px] bg-cm-topbar bg-topbar-sheen dark:bg-zinc-900 dark:bg-none border-b border-cm-topbar-line dark:border-zinc-800 px-3.5 lg:px-[18px] flex items-center gap-3 lg:gap-6 shrink-0 z-20 transition-colors">
                <div className="shrink-0">
                    <BrandLockup/>
                </div>

                <div className="flex-1 min-w-0 flex items-center gap-0.5 overflow-x-auto no-scrollbar">
                    {TABS.map(({key, icon: Icon, label}) => {
                        const active = currentTab === key;
                        return (
                            <button
                                key={key}
                                onClick={() => onTabChange(key)}
                                className={`flex items-center gap-2 px-2.5 lg:px-[13px] py-[11px] rounded-lg text-[13px] whitespace-nowrap transition-all duration-150 ${
                                    active
                                        ? 'bg-[#DBEAFF] text-[#1E58CD] font-bold dark:bg-cm-primary/20 dark:text-blue-200'
                                        : 'text-[#627E9E] hover:text-cm-primary hover:bg-[#E0EDFF] dark:text-zinc-400 dark:hover:text-white dark:hover:bg-zinc-800'
                                }`}
                            >
                                <Icon size={15} strokeWidth={active ? 2.1 : 1.8}/>
                                {t(label)}
                            </button>
                        );
                    })}
                </div>

                <div className="flex items-center gap-3 lg:gap-[19px] text-[12px] text-[#617B9A] dark:text-zinc-400 shrink-0">
                    {onLogout && (
                        <>
                            <span className="hidden xl:inline text-[#617B9A] dark:text-zinc-400 max-w-[9rem] truncate">{displayName}</span>
                            <button
                                type="button"
                                aria-label={t('login.change_password')}
                                title={t('login.change_password')}
                                onClick={() => setIsPasswordChangeOpen(true)}
                                className="cm-icon-btn"
                            >
                                <KeyRound size={15}/>
                            </button>
                            <button
                                type="button"
                                onClick={onLogout}
                                className="text-[12px] text-[#617B9A] dark:text-zinc-400 hover:text-cm-primary dark:hover:text-white transition-colors flex items-center gap-1"
                            >
                                <LogOut size={13}/>
                                {t('login.logout')}
                            </button>
                        </>
                    )}

                    <button
                        type="button"
                        aria-label={t('nav.toggle_theme')}
                        onClick={() => setIsDark(!isDark)}
                        className="cm-icon-btn"
                    >
                        {isDark ? <Sun size={16} className="text-amber-400"/> : <Moon size={16}/>}
                    </button>

                    <div className="flex items-center gap-0.5">
                        {['zh', 'en'].map((code) => (
                            <button
                                key={code}
                                onClick={() => onLangChange(code)}
                                className={`px-1.5 py-0.5 rounded-[5px] text-[12px] transition-colors ${
                                    lang === code
                                        ? 'text-[#1E58CD] font-bold bg-[#DBEAFF] dark:bg-cm-primary/20 dark:text-blue-200'
                                        : 'text-[#8098B8] dark:text-zinc-500 hover:text-cm-primary dark:hover:text-zinc-200'
                                }`}
                            >
                                {code === 'zh' ? '中' : 'EN'}
                            </button>
                        ))}
                    </div>

                    <button
                        type="button"
                        aria-label={t('settings.title')}
                        title={t('settings.title')}
                        onClick={() => setIsSettingsOpen(true)}
                        className="cm-icon-btn"
                    >
                        <Settings size={16} className="hover:rotate-90 transition-transform duration-500"/>
                    </button>

                    <span
                        aria-hidden="true"
                        className="h-[29px] w-[29px] rounded-full bg-avatar-gradient text-white text-[11px] font-bold grid place-items-center border-2 border-white shadow-sm"
                    >
                        {initial}
                    </span>
                </div>
            </nav>
            <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} t={t}/>
            <PasswordChangeModal isOpen={isPasswordChangeOpen} onClose={() => setIsPasswordChangeOpen(false)} t={t}/>
        </>
    )
}

export default Header;
