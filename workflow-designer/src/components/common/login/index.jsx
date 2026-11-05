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
import {useState, useEffect} from "react";
import {useTranslation} from "react-i18next";
import {Lock, ArrowRight, AlertCircle, Loader2, Settings} from "lucide-react";
import {User} from "lucide-react";
import SettingsModal from "../setting/index.jsx";
import openanLogo from "../../../assets/openan-logo.png";
import {getBaseUrl, login, register} from "@/service/api.js";

const MAX_RECENT_USERNAMES = 5;

function readRecentUsernames(key) {
    try {
        const usernames = JSON.parse(localStorage.getItem(key));
        if (!Array.isArray(usernames)) return [];
        return [...new Set(usernames.filter(name => typeof name === 'string' && name.trim() && name.length <= 64))]
            .slice(0, MAX_RECENT_USERNAMES);
    } catch {
        return [];
    }
}

function writeRecentUsernames(key, usernames) {
    try {
        if (usernames.length) localStorage.setItem(key, JSON.stringify(usernames));
        else localStorage.removeItem(key);
    } catch {
        // Browser storage availability must not determine whether login succeeds.
    }
}

const Login = ({isDark, onLoginSuccess, onLoginWithUser, registrationEnabled, singleAccount}) => {
    const {t, i18n} = useTranslation();
    const historyKey = `openan.orchestration.recent-usernames:${getBaseUrl()}`;
    const [recentUsernames, setRecentUsernames] = useState(() => singleAccount ? [] : readRecentUsernames(historyKey));
    const [rememberUsername, setRememberUsername] = useState(recentUsernames.length > 0);
    const [username, setUsername] = useState(singleAccount ? 'admin' : '');
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [isSettingsOpen, setIsSettingsOpen] = useState(false);
    const [isRegisterMode, setIsRegisterMode] = useState(false);
    const [confirmPassword, setConfirmPassword] = useState("");

    useEffect(() => {
        let lang = 'en';
        try {
            lang = localStorage.getItem('lang') || 'en';
        } catch {
            // Login remains available when browser storage is blocked.
        }
        if (lang !== i18n.language) {
            i18n.changeLanguage(lang);
        }
    }, [i18n]);

    const finishLogin = (data) => {
        if (data?.auth_required) {
            if (!singleAccount && rememberUsername && data.username) {
                const names = readRecentUsernames(historyKey).filter(name => name !== data.username);
                writeRecentUsernames(historyKey, [data.username, ...names].slice(0, MAX_RECENT_USERNAMES));
            }
            onLoginWithUser ? onLoginWithUser(data.username, data.must_change_password) : onLoginSuccess();
        } else if (data?.auth_required === false) {
            onLoginSuccess();
        }
    };

    const clearRecentUsernames = () => {
        setRememberUsername(false);
        setRecentUsernames([]);
        writeRecentUsernames(historyKey, []);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (!username.trim() || !password.trim() || loading) return;
        setLoading(true);
        setError("");
        try {
            finishLogin(await login(username, password));
        } catch (err) {
            const msg = err?.response?.data?.message || err?.message || "";
            setError(msg || t('login.error'));
        } finally {
            setLoading(false);
        }
    };

   const handleRegister = async (e) => {
       e.preventDefault();
       if (!username.trim() || !password.trim() || loading) return;
       if (password.length < 8) {
           setError(t('login.password_too_short'));
           return;
       }
       if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/[0-9]/.test(password)) {
           setError(t('login.password_complexity'));
           return;
       }
       if (password !== confirmPassword) {
            setError(t('login.password_mismatch'));
            return;
        }
        setLoading(true);
        setError("");
        try {
            await register(username, password);
            finishLogin(await login(username, password));
       } catch (err) {
            const msg = err?.response?.data?.message || err?.message || "";
            setError(msg || t('login.error'));
        } finally {
            setLoading(false);
        }
    };

    const handleLangChange = (l) => {
        i18n.changeLanguage(l);
        try {
            localStorage.setItem('lang', l);
        } catch {
            // The selected language still applies for the current page.
        }
    };

    return (
        <div className="h-screen flex items-center justify-center bg-zinc-50 dark:bg-[#09090B] font-sans transition-colors duration-500">
            <div className="w-full max-w-md px-8">
                <div className="flex flex-col items-center mb-10">
                    <div className="w-16 h-16 rounded-xl bg-white p-1.5 flex items-center justify-center shadow-lg mb-4">
                        <img src={openanLogo} alt="OpenAN" className="w-full h-full object-contain"/>
                    </div>
                    <h1 className="text-3xl font-medium tracking-tight text-zinc-900 dark:text-zinc-100">
                        Open<span className="text-blue-500">AN</span>
                    </h1>
                    <p className="text-xs tracking-widest uppercase text-zinc-400 dark:text-zinc-500 mt-1">
                        Open Autonomous Networks
                    </p>
                </div>

                <form onSubmit={isRegisterMode ? handleRegister : handleSubmit}
                      className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-xl p-8 space-y-5">
                    <div className="flex items-center gap-2 text-zinc-700 dark:text-zinc-200">
                        <Lock size={18} className="text-blue-500"/>
                        <span className="text-sm font-medium">{isRegisterMode ? t('login.register_title') : t('login.title')}</span>
                   </div>

                    <div className="relative">
                        <input
                            type="text"
                            name="username"
                            autoComplete="username"
                            aria-label={t('login.username_placeholder')}
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            placeholder={t('login.username_placeholder')}
                            disabled={loading}
                            className="w-full pl-10 pr-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm"
                        />
                        <User size={16} className="absolute left-3.5 top-3.5 text-zinc-400"/>
                    </div>

                    {!singleAccount && !isRegisterMode && recentUsernames.length > 0 && (
                        <div className="flex items-center gap-3">
                            <select
                                aria-label={t('login.recent_usernames')}
                                value=""
                                disabled={loading}
                                onChange={(e) => {
                                    setUsername(e.target.value);
                                    setPassword('');
                                    setError('');
                                }}
                                className="min-w-0 flex-1 rounded-lg px-2 py-1.5 text-sm bg-zinc-50 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-700">
                                <option value="" disabled>{t('login.recent_usernames')}</option>
                                {recentUsernames.map(name => <option key={name} value={name}>{name}</option>)}
                            </select>
                            <button type="button" disabled={loading} onClick={clearRecentUsernames} className="text-sm text-blue-600 dark:text-blue-400 hover:underline">
                                {t('login.clear_recent_usernames')}
                            </button>
                        </div>
                    )}

                    <div>
                        <input
                            type="password"
                            name="password"
                            autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder={t('login.placeholder')}
                            disabled={loading}
                            className="w-full px-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm"
                        />
                    </div>

                    {isRegisterMode && (
                    <div className="relative">
                        <input
                            type="password"
                            name="confirmPassword"
                            autoComplete="new-password"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            placeholder={t('login.confirm_password')}
                            disabled={loading}
                            className="w-full pl-10 pr-4 py-3 rounded-xl bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all text-sm"
                        />
                        <Lock size={16} className="absolute left-3.5 top-3.5 text-zinc-400"/>
                    </div>
                    )}

                    {!singleAccount && (
                        <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
                            <input
                                type="checkbox"
                                checked={rememberUsername}
                                disabled={loading}
                                onChange={(e) => e.target.checked ? setRememberUsername(true) : clearRecentUsernames()}
                            />
                            {t('login.remember_username')}
                        </label>
                    )}

                    {error && (
                        <div className="flex items-center gap-2 text-sm text-red-500">
                            <AlertCircle size={16}/>
                            <span>{error}</span>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading || !username.trim() || !password.trim()}
                        className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-blue-500 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-medium text-sm transition-all">
                        {loading ? (
                            <>
                                <Loader2 size={18} className="animate-spin"/>
                                {t('login.loading')}
                            </>
                        ) : (
                            <>
                                {isRegisterMode ? t('login.register_button') : t('login.button')}
                                <ArrowRight size={18}/>
                            </>
                        )}
                    </button>

                    {registrationEnabled && (
                    <div className="text-center text-sm text-zinc-400">
                        {isRegisterMode ? (
                            <span>{t('login.have_account')} <button type="button" onClick={() => {setIsRegisterMode(false); setError("");}} className="text-blue-500 hover:underline font-medium">{t('login.button')}</button></span>
                        ) : (
                            <span>{t('login.no_account')} <button type="button" onClick={() => {setIsRegisterMode(true); setError("");}} className="text-blue-500 hover:underline font-medium">{t('login.register_button')}</button></span>
                        )}
                    </div>
                    )}
                </form>

                <div className="flex justify-center mt-6 gap-4 items-center">
                    <div className="flex bg-zinc-100 dark:bg-zinc-800 p-1 rounded-full border border-zinc-200 dark:border-zinc-700 shadow-inner">
                        <button onClick={() => handleLangChange('zh')}
                                className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${i18n.language === 'zh' ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm' : 'text-zinc-400'}`}>
                            中
                        </button>
                        <button onClick={() => handleLangChange('en')}
                                className={`px-4 py-1.5 rounded-full text-xs font-black transition-all ${i18n.language === 'en' ? 'bg-white dark:bg-zinc-600 text-blue-600 dark:text-white shadow-sm' : 'text-zinc-400'}`}>
                            EN
                        </button>
                    </div>
                    <button onClick={() => setIsSettingsOpen(true)}
                            className="p-2.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all">
                        <Settings size={20} className="text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300 transition-all"/>
                    </button>
                </div>
            </div>
            <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} t={t}/>
        </div>
    );
};

export default Login;
