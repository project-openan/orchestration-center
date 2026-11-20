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
import {useState, useEffect, useId, useRef} from "react";
import {useTranslation} from "react-i18next";
import {Lock, ArrowRight, AlertCircle, Loader2, Settings, Workflow, Boxes, Activity} from "lucide-react";
import {User} from "lucide-react";
import SettingsModal from "../setting/index.jsx";
import {BrandMark} from "../brand/index.jsx";
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
    const [historyOpen, setHistoryOpen] = useState(false);
    const [activeUsername, setActiveUsername] = useState(-1);
    const historyId = useId();
    const usernameRef = useRef(null);
    const passwordRef = useRef(null);
    const matchingUsernames = recentUsernames.filter(name => name.toLowerCase().startsWith(username.toLowerCase()));
    const historyVisible = historyOpen && !singleAccount && !isRegisterMode && !loading && matchingUsernames.length > 0;

    const selectUsername = (name) => {
        setUsername(name);
        setPassword('');
        setError('');
        setHistoryOpen(false);
        setActiveUsername(-1);
    };

    const handleUsernameKeyDown = (event) => {
        if (singleAccount || isRegisterMode || !matchingUsernames.length) return;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setHistoryOpen(true);
            const direction = event.key === 'ArrowDown' ? 1 : -1;
            setActiveUsername(historyVisible && activeUsername >= 0
                ? (activeUsername + direction + matchingUsernames.length) % matchingUsernames.length
                : direction === 1 ? 0 : matchingUsernames.length - 1);
        } else if (event.key === 'Enter' && historyVisible && activeUsername >= 0) {
            event.preventDefault();
            selectUsername(matchingUsernames[activeUsername]);
        } else if (event.key === 'Escape') {
            setHistoryOpen(false);
            setActiveUsername(-1);
        }
    };

    useEffect(() => {
        let lang = 'zh';
        try {
            lang = localStorage.getItem('lang') || 'zh';
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
        setHistoryOpen(false);
        setActiveUsername(-1);
        writeRecentUsernames(historyKey, []);
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        if (loading) return;
        if (!username.trim()) {
            setError(t('login.username_required'));
            usernameRef.current?.focus();
            return;
        }
        if (!password.trim()) {
            setError(t('login.password_required'));
            passwordRef.current?.focus();
            return;
        }
        setLoading(true);
        setError("");
        try {
            finishLogin(await login(username, password));
        } catch (err) {
            // The backend reports a failed credential check in English; the
            // localized wording is clearer on this screen.
            const msg = err?.response?.status === 401
                ? t('login.error')
                : (err?.response?.data?.message || err?.message || "");
            setError(msg || t('login.error'));
        } finally {
            setLoading(false);
        }
    };

   const handleRegister = async (e) => {
       e.preventDefault();
       if (loading) return;
       if (!username.trim()) {
           setError(t('login.username_required'));
           usernameRef.current?.focus();
           return;
       }
       if (!password.trim()) {
           setError(t('login.password_required'));
           passwordRef.current?.focus();
           return;
       }
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
            const msg = err?.response?.status === 401
                ? t('login.error')
                : (err?.response?.data?.message || err?.message || "");
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

    const features = [
        {icon: Workflow, label: t('login.feature_orchestration')},
        {icon: Boxes, label: t('login.feature_agents')},
        {icon: Activity, label: t('login.feature_observability')},
    ];

    return (
        <div className="min-h-screen flex bg-cm-canvas dark:bg-cm-night font-sans transition-colors duration-300">
            {/* Brand panel -- hidden on small screens. */}
            <aside className="hidden lg:flex relative w-[42%] xl:w-[40%] flex-col justify-between overflow-hidden px-12 xl:px-16 py-12 text-white bg-brand-gradient">
                <div className="absolute -top-24 -left-24 h-96 w-96 rounded-full bg-white/10 blur-2xl"/>
                <div className="absolute -bottom-28 -right-20 h-[26rem] w-[26rem] rounded-full bg-white/10 blur-3xl"/>
                <div
                    className="absolute inset-0 opacity-[0.14]"
                    style={{
                        backgroundImage:
                            'linear-gradient(rgba(255,255,255,.4) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.4) 1px, transparent 1px)',
                        backgroundSize: '42px 42px',
                    }}
                />
                <div className="relative z-10 flex items-center gap-2.5">
                    <span className="h-8 w-8 grid place-items-center rounded-[8px] bg-white p-1">
                        <BrandMark className="w-full h-full"/>
                    </span>
                    <span className="text-[17px] font-bold tracking-[-0.4px]">{t('brand.company')}</span>
                </div>

                <div className="relative z-10 max-w-md">
                    <h2 className="text-[30px] leading-snug font-bold tracking-[-0.5px]">{t('brand.product')}</h2>
                    <p className="mt-4 text-[13px] leading-relaxed text-white/80">{t('brand.slogan')}</p>
                    <ul className="mt-9 space-y-3.5">
                        {features.map(({icon: Icon, label}) => (
                            <li key={label} className="flex items-center gap-3 text-[13px] text-white/90">
                                <span className="h-8 w-8 grid place-items-center rounded-[7px] bg-white/15 border border-white/25">
                                    <Icon size={15}/>
                                </span>
                                {label}
                            </li>
                        ))}
                    </ul>
                </div>

                <div className="relative z-10 text-[11px] text-white/60">{t('brand.copyright')}</div>
            </aside>

            <main className="flex-1 flex items-center justify-center px-5 py-10">
                <div className="w-full max-w-[400px]">
                    <div className="lg:hidden flex items-center justify-center gap-2.5 mb-8">
                        <span className="h-8 w-8 grid place-items-center rounded-[8px] bg-white border border-cm-line p-1 shadow-card">
                            <BrandMark className="w-full h-full"/>
                        </span>
                        <span className="text-[16px] font-bold text-[#142843] dark:text-zinc-100">{t('brand.company')}</span>
                    </div>

                    <form onSubmit={isRegisterMode ? handleRegister : handleSubmit}
                          className="bg-white dark:bg-zinc-900 rounded-2xl border border-cm-line dark:border-zinc-800 shadow-card p-7 space-y-4">
                        <div className="mb-1">
                            <h1 className="text-[19px] font-bold text-cm-heading dark:text-zinc-100 tracking-[-0.3px]">
                                {isRegisterMode ? t('login.register_title') : t('login.title')}
                            </h1>
                            <p className="mt-1.5 text-[12px] text-cm-muted dark:text-zinc-400">
                                {t('login.welcome_subtitle')}
                            </p>
                        </div>

                    <div className="relative"
                         onMouseEnter={() => setHistoryOpen(true)}
                         onMouseLeave={(event) => {
                             if (!event.currentTarget.contains(document.activeElement)) setHistoryOpen(false);
                         }}
                         onBlur={(event) => {
                             if (!event.currentTarget.contains(event.relatedTarget)) {
                                 setHistoryOpen(false);
                                 setActiveUsername(-1);
                             }
                         }}>
                        <input
                            type="text"
                            name="username"
                            ref={usernameRef}
                            autoComplete="username"
                            aria-label={t('login.username_placeholder')}
                            role={!singleAccount && !isRegisterMode ? 'combobox' : undefined}
                            aria-autocomplete={!singleAccount && !isRegisterMode ? 'list' : undefined}
                            aria-expanded={!singleAccount && !isRegisterMode ? historyVisible : undefined}
                            aria-controls={historyVisible ? historyId : undefined}
                            aria-activedescendant={historyVisible && activeUsername >= 0 ? `${historyId}-${activeUsername}` : undefined}
                            value={username}
                            onChange={(e) => {
                                setUsername(e.target.value);
                                setActiveUsername(-1);
                                setHistoryOpen(true);
                            }}
                            onFocus={() => {setHistoryOpen(true); setActiveUsername(-1);}}
                            onClick={() => setHistoryOpen(true)}
                            onKeyDown={handleUsernameKeyDown}
                            placeholder={t('login.username_placeholder')}
                            disabled={loading}
                            className="cm-input pl-10 pr-3"
                        />
                        <User size={16} className="absolute left-3 top-[11px] text-cm-faint"/>
                        {historyVisible && (
                            <div className="absolute top-full left-0 right-0 z-20 mt-1 overflow-hidden rounded-[10px] border border-cm-line bg-white dark:border-zinc-700 dark:bg-zinc-800 shadow-panel"
                                 onMouseDown={(event) => event.preventDefault()}>
                                <ul id={historyId} role="listbox" aria-label={t('login.recent_usernames')}>
                                    {matchingUsernames.map((name, index) => (
                                        <li key={name} role="presentation">
                                            <button type="button" role="option" id={`${historyId}-${index}`}
                                                    tabIndex={-1} aria-selected={index === activeUsername}
                                                    onMouseEnter={() => setActiveUsername(index)}
                                                    onClick={() => selectUsername(name)}
                                                    className={`w-full truncate px-4 py-2 text-left text-sm text-zinc-900 dark:text-zinc-100 ${index === activeUsername ? 'bg-cm-primary-soft dark:bg-zinc-700' : 'hover:bg-zinc-50 dark:hover:bg-zinc-700'}`}>
                                                {name}
                                            </button>
                                        </li>
                                    ))}
                                </ul>
                                <button type="button" onClick={clearRecentUsernames}
                                        className="w-full border-t border-cm-line-soft dark:border-zinc-700 px-4 py-2 text-left text-[11px] text-cm-muted hover:text-cm-primary">
                                    {t('login.clear_recent_usernames')}
                                </button>
                            </div>
                        )}
                    </div>

                    <div>
                        <input
                            type="password"
                            name="password"
                            ref={passwordRef}
                            autoComplete={isRegisterMode ? 'new-password' : 'current-password'}
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder={t('login.placeholder')}
                            disabled={loading}
                            className="cm-input pl-10 pr-3"
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
                            className="cm-input pl-10 pr-3"
                        />
                        <Lock size={16} className="absolute left-3 top-[11px] text-cm-faint"/>
                    </div>
                    )}

                    {!singleAccount && (
                        <label className="flex items-center gap-2 text-[12px] text-cm-secondary dark:text-zinc-300">
                            <input
                                type="checkbox"
                                className="accent-cm-primary"
                                checked={rememberUsername}
                                disabled={loading}
                                onChange={(e) => e.target.checked ? setRememberUsername(true) : clearRecentUsernames()}
                            />
                            {t('login.remember_username')}
                        </label>
                    )}

                    {error && (
                        <div
                            className="flex items-start gap-2 rounded-[7px] border border-rose-200 bg-rose-50 px-3 py-2 text-[12px] text-rose-600 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-400">
                            <AlertCircle size={14} className="mt-0.5 shrink-0"/>
                            <span className="leading-relaxed">{error}</span>
                        </div>
                    )}

                    <button
                        type="submit"
                        disabled={loading || !password.trim()}
                        className="cm-btn-primary w-full min-h-[39px] gap-2">
                        {loading ? (
                            <>
                                <Loader2 size={16} className="animate-spin"/>
                                {t('login.loading')}
                            </>
                        ) : (
                            <>
                                {isRegisterMode ? t('login.register_button') : t('login.button')}
                                <ArrowRight size={16}/>
                            </>
                        )}
                    </button>

                    {registrationEnabled && (
                    <div className="text-center text-[12px] text-cm-muted">
                        {isRegisterMode ? (
                            <span>{t('login.have_account')} <button type="button" onClick={() => {setIsRegisterMode(false); setError("");}} className="text-cm-primary hover:underline font-medium">{t('login.button')}</button></span>
                        ) : (
                            <span>{t('login.no_account')} <button type="button" onClick={() => {setIsRegisterMode(true); setError("");}} className="text-cm-primary hover:underline font-medium">{t('login.register_button')}</button></span>
                        )}
                    </div>
                    )}
                </form>

                <div className="flex justify-center mt-5 items-center gap-3">
                    <div className="flex items-center gap-0.5 rounded-[7px] border border-cm-line bg-white dark:bg-zinc-900 dark:border-zinc-700 p-0.5 shadow-sm">
                        {['zh', 'en'].map((code) => (
                            <button key={code} onClick={() => handleLangChange(code)}
                                    className={`px-3 py-1 rounded-[5px] text-[11px] transition-colors ${i18n.language === code ? 'bg-cm-primary-faint text-cm-primary font-semibold' : 'text-cm-faint hover:text-cm-primary'}`}>
                                {code === 'zh' ? '中' : 'EN'}
                            </button>
                        ))}
                    </div>
                    <button onClick={() => setIsSettingsOpen(true)}
                            aria-label={t('settings.title')}
                            className="cm-icon-btn">
                        <Settings size={16}/>
                    </button>
                </div>

                <p className="mt-6 text-center text-[11px] text-cm-faint dark:text-zinc-500 lg:hidden">
                    {t('brand.copyright')}
                </p>
                </div>
            </main>
            <SettingsModal isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} t={t}/>
        </div>
    );
};

export default Login;
