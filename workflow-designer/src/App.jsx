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
import {useTranslation} from "react-i18next";
import {useCallback, useEffect, useState} from "react";
import {ServerOff} from "lucide-react";
import Header from "@/components/common/header/index.jsx";
import Login from "@/components/common/login/index.jsx";
import PasswordChangeModal from "@/components/common/password_change/index.jsx";
import {authCheck, logout} from "@/service/api.js";
import AgentRegistry from "./components/registry_center/index.jsx";
import OrchestrationCenter from "@/components/orchestration_center/index.jsx";
import ExecutionCenter from "@/components/execution_center/index.jsx";
import SkillCenter from "@/components/skill_center/index.jsx";
import {ErrorBoundary} from "@/components/common/error_boundary/index.jsx";

const MainContainer = () => {
    const {t, i18n} = useTranslation();

   const [authState, setAuthState] = useState('checking');
   const [authRequired, setAuthRequired] = useState(false);
   const [registrationEnabled, setRegistrationEnabled] = useState(false);
   const [singleAccount, setSingleAccount] = useState(false);
   const [currentUser, setCurrentUser] = useState(null);
   const [mustChangePassword, setMustChangePassword] = useState(false);
   // Gates admin-only UI (AgentCard edit/delete). When auth is disabled the
   // backend skips role checks entirely, so treat that mode as admin too.
   const [isAdmin, setIsAdmin] = useState(false);

   const applyAuthData = (data) => {
       setAuthRequired(data.auth_required !== false);
       setRegistrationEnabled(data.registration_enabled || false);
       setSingleAccount(data.single_account === true);
       setCurrentUser(data.username || null);
       setMustChangePassword(!!data.must_change_password);
       setIsAdmin(data.auth_required === false || data.role === 'admin');
       setAuthState('authenticated');
   };

   const [isDark, setIsDark] = useState(() => {
        const savedTheme = localStorage.getItem('theme');
        return (savedTheme || 'dark') === 'dark';
    });

    const runAuthCheck = useCallback(() => {
        authCheck()
            .then((data) => {
               if (data.auth_required === false || data.authenticated === true) {
                   applyAuthData(data);
               } else {
                   setAuthRequired(true);
                   setRegistrationEnabled(data.registration_enabled || false);
                   setSingleAccount(data.single_account === true);
                   setIsAdmin(false);
                   setAuthState('unauthenticated');
               }
            })
            .catch(() => setAuthState('unreachable'));
    }, []);

    useEffect(() => {
        runAuthCheck();
    }, [runAuthCheck]);

    useEffect(() => {
        const handleAuthExpired = () => setAuthState('unauthenticated');
        window.addEventListener('auth-expired', handleAuthExpired);
        return () => window.removeEventListener('auth-expired', handleAuthExpired);
    }, []);

   const handleLoginSuccess = () => {
       setAuthState('authenticated');
       // The session cookie is now set; re-check to pick up the role flag
       // that gates admin-only UI (AgentCard edit/delete).
       authCheck().then(applyAuthData).catch(() => {});
   };

   const handleLogout = async () => {
       // The session cookie is httpOnly -- only the server can clear it, so
       // this has to hit /auth/logout rather than just resetting local state.
       try {
           await logout();
       } finally {
           setAuthState('unauthenticated');
           setCurrentUser(null);
           setMustChangePassword(false);
           setIsAdmin(false);
       }
   };

   const [activeTab, setActiveTab] = useState(() => {
       return localStorage.getItem('activeTab') || 'agents'
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
        <>
        {authState === 'checking' ? (
            <div className="h-screen flex items-center justify-center bg-zinc-50 dark:bg-[#09090B]">
                <div className="text-zinc-400 text-sm animate-pulse">Loading...</div>
            </div>
        ) : authState === 'unreachable' ? (
            // The backend did not answer at all (connection refused/reset, TLS
            // mismatch, ...). This must NOT look like a login prompt: the user
            // would start guessing credentials for a service that is simply
            // down (see the login fast-path that accepts any password when
            // authentication is disabled).
            <div data-testid="backend-unreachable" className="h-screen flex flex-col items-center justify-center gap-4 bg-zinc-50 dark:bg-[#09090B]">
                <ServerOff size={40} className="text-zinc-400"/>
                <div className="text-zinc-500 dark:text-zinc-400 text-sm text-center max-w-md px-6">
                    {t('login.backend_unreachable')}
                </div>
                <button
                    type="button"
                    data-testid="retry-backend-connection"
                    onClick={() => {
                        setAuthState('checking');
                        runAuthCheck();
                    }}
                    className="px-4 py-2 rounded-lg text-sm font-medium bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-all"
                >
                    {t('login.retry')}
                </button>
            </div>
        ) : authState !== 'authenticated' ? (
           <Login
               isDark={isDark}
               onLoginSuccess={handleLoginSuccess}
               onLoginWithUser={(user, mustChange) => {
                   setCurrentUser(user);
                   setMustChangePassword(!!mustChange);
                   handleLoginSuccess();
               }}
               registrationEnabled={registrationEnabled}
               singleAccount={singleAccount}
           />
        ) : (
        <div className="h-screen flex flex-col bg-zinc-50 dark:bg-[#09090B] overflow-hidden font-sans text-lg transition-colors duration-500">
           {mustChangePassword && (
               <PasswordChangeModal
                   isOpen={true}
                   forced={true}
                   onClose={() => {}}
                   t={t}
               />
           )}
           <Header
               currentTab={activeTab}
               onTabChange={setActiveTab}
               isDark={isDark}
               setIsDark={setIsDark}
               lang={i18n.language}
               onLangChange={handleLangChange}
               t={t}
               onLogout={authRequired ? handleLogout : null}
               currentUser={currentUser}
           />

            <main className="flex-1 min-h-0 relative overflow-hidden">
                <div className={`h-full w-full ${activeTab === 'agents' ? 'relative z-10 visible animate-in' : 'absolute invisible -left-[9999px] -top-[9999px]'}`}>
                    <ErrorBoundary><AgentRegistry isDark={isDark} t={t} isAdmin={isAdmin}/></ErrorBoundary>
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
        )}
        </>
    )
}

export default MainContainer;
