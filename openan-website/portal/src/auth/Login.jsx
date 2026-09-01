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

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from './AuthContext.jsx';
import { useTheme } from '../theme/ThemeContext.jsx';
import { Sun, Moon } from 'lucide-react';

export default function Login() {
    const { t } = useTranslation();
    const { login } = useAuth();
    const { isDark, toggle } = useTheme();

    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError('');
        try {
            await login(username || 'admin', password);
        } catch (err) {
            setError(err?.response?.data?.detail || t('login.error'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="h-screen flex items-center justify-center bg-zinc-50 dark:bg-[#09090B] font-sans">
            <button
                onClick={toggle}
                className="absolute top-6 right-6 p-2.5 rounded-full hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-all"
            >
                {isDark ? (
                    <Sun size={20} className="text-amber-400" />
                ) : (
                    <Moon size={20} className="text-zinc-500" />
                )}
            </button>
            <div className="w-full max-w-sm mx-6">
                <div className="text-center mb-8">
                    <div className="text-2xl font-bold tracking-tight text-zinc-900 dark:text-zinc-100 mb-1">
                        Open<span className="text-blue-500">AN</span>
                    </div>
                    <p className="text-xs tracking-widest uppercase text-zinc-400 dark:text-zinc-500">
                        {t('nav.subtitle')}
                    </p>
                </div>
                <form
                    onSubmit={handleSubmit}
                    className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 p-8 shadow-sm space-y-4"
                >
                    <h2 className="text-lg font-bold text-zinc-900 dark:text-zinc-100 text-center">
                        {t('login.title')}
                    </h2>
                    <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder={t('login.username_placeholder')}
                        className="w-full px-4 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder={t('login.placeholder')}
                        className="w-full px-4 py-3 rounded-xl bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    {error && (
                        <p className="text-sm text-red-500 text-center">{error}</p>
                    )}
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full py-3 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-bold transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {loading ? t('login.loading') : t('login.button')}
                    </button>
                </form>
            </div>
        </div>
    );
}
