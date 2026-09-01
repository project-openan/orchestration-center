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

import { lazy, Suspense, useState, useEffect, useMemo, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { PortalProvider, loadEnabledPlugins } from '@openan/portal-sdk';
import { loadPluginI18n } from './i18n/index.js';
import { AuthProvider, useAuth } from './auth/AuthContext.jsx';
import { ThemeProvider, useTheme } from './theme/ThemeContext.jsx';
import { PluginRegistryProvider } from './plugin/registry.jsx';
import Header from './components/header/index.jsx';
import { ErrorBoundary } from './components/error_boundary/index.jsx';
import Loading from './components/loading.jsx';
import Login from './auth/Login.jsx';
import PluginManager from './components/plugin_manager/index.jsx';
import api, { createApi } from './service/api.js';

import './i18n';

const DISABLED_KEY = 'openan-disabled-plugins';

export function PortalApp({ pluginsConfig }) {
    return (
        <BrowserRouter>
            <ThemeProvider>
                <AuthProvider>
                    <PortalShell pluginsConfig={pluginsConfig} />
                </AuthProvider>
            </ThemeProvider>
        </BrowserRouter>
    );
}

function PortalShell({ pluginsConfig }) {
    const { t, i18n } = useTranslation();
    const auth = useAuth();
    const theme = useTheme();
    const location = useLocation();
    const navigate = useNavigate();

    const [plugins, setPlugins] = useState(null);
    const [showPluginManager, setShowPluginManager] = useState(false);
    const [disabledIds, setDisabledIds] = useState(() => {
        try {
            const saved = localStorage.getItem(DISABLED_KEY);
            return new Set(saved ? JSON.parse(saved) : []);
        } catch {
            return new Set();
        }
    });

    useEffect(() => {
        async function loadAllPlugins() {
            const localEntries = pluginsConfig.plugins.filter((p) => p.manifest && !p.remote);
            const remoteEntries = pluginsConfig.plugins.filter((p) => p.remote && !p.manifest);

            // Load all plugins (build-time integration)
            const manifests = await loadEnabledPlugins(pluginsConfig);
            await Promise.all(
                manifests.filter((p) => p.i18n).map((p) => loadPluginI18n(p.i18n))
            );
            setPlugins(manifests);
        }

        loadAllPlugins().catch((err) => {
            console.error('[Portal] Failed to load plugins:', err);
            setPlugins([]);
        });
    }, [pluginsConfig]);

    const togglePlugin = useCallback((id) => {
        setDisabledIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) next.delete(id);
            else next.add(id);
            localStorage.setItem(DISABLED_KEY, JSON.stringify([...next]));
            return next;
        });
    }, []);

    // Plugins visible in nav + routes (excluding runtime-disabled)
    const visiblePlugins = useMemo(() => {
        if (!plugins) return null;
        return plugins.filter((p) => !disabledIds.has(p.id));
    }, [plugins, disabledIds]);

    const routes = useMemo(() => {
        if (!visiblePlugins) return [];
        return visiblePlugins.flatMap((p) =>
            p.routes.map((r) => ({
                ...r,
                pluginId: p.id,
                Component: lazy(r.component),
            }))
        );
    }, [visiblePlugins]);

    const portalCtx = useMemo(() => ({
        auth: {
            user: auth.currentUser,
            role: auth.authRequired ? 'user' : null,
            isAuthenticated: auth.isAuthenticated,
            login: auth.login,
            logout: auth.logout,
        },
        theme: {
            isDark: theme.isDark,
            toggle: theme.toggle,
            setDark: theme.setDark,
        },
        i18n,
        navigate,
        router: { location, navigate },
        registerMenu: () => {},
        registerRoute: () => {},
    }), [auth, theme, i18n, navigate, location]);

    // Set global context for Module Federation bridge — remote plugins
    // load their own copy of @openan/portal-sdk, which has a different
    // React Context instance. Setting window.__OPENAN_PORTAL_CONTEXT__
    // here (before render) ensures remote plugins can always read it.
    if (typeof window !== 'undefined') {
        window.__OPENAN_PORTAL_CONTEXT__ = portalCtx;
    }

    // Cache per-plugin API instances (keyed by gateway path)
    const pluginApiCache = useMemo(() => new Map(), []);
    const getPluginApi = useCallback((plugin) => {
        const gateway = plugin.backend?.gateway;
        if (!gateway) return api;
        if (!pluginApiCache.has(gateway)) {
            pluginApiCache.set(gateway, createApi(gateway));
        }
        return pluginApiCache.get(gateway);
    }, [pluginApiCache]);

    if (auth.isChecking || !plugins) {
        return <Loading />;
    }

    if (!auth.isAuthenticated) {
        return <Login />;
    }

    if (routes.length === 0) {
        return (
            <div className="h-screen flex items-center justify-center bg-zinc-50 dark:bg-[#09090B]">
                <div className="text-center">
                    <p className="text-zinc-400 text-sm mb-4">{t('portal.no_plugins')}</p>
                    <button
                        onClick={() => setShowPluginManager(true)}
                        className="px-4 py-2 rounded-xl bg-blue-500 text-white text-sm font-bold hover:bg-blue-600 transition-all"
                    >
                        {t('plugin_manager.title')}
                    </button>
                </div>
            </div>
        );
    }

    // If current route is disabled, redirect to first visible route
    const currentRouteValid = routes.some((r) =>
        location.pathname === r.path || location.pathname.startsWith(r.path + '/')
    );

    return (
        <PluginRegistryProvider plugins={visiblePlugins}>
                <div className="h-screen flex flex-col bg-zinc-50 dark:bg-[#09090B] overflow-hidden font-sans transition-colors duration-500">
                    <Header
                        plugins={plugins}
                        disabledIds={disabledIds}
                        onManagePlugins={() => setShowPluginManager(true)}
                    />
                    <main className="flex-1 min-h-0 relative overflow-hidden">
                        <Routes>
                            {routes.map((r) => {
                                const plugin = visiblePlugins.find((p) => p.id === r.pluginId);
                                const pluginApi = getPluginApi(plugin);
                                return (
                                    <Route
                                        key={r.path}
                                        path={r.path}
                                        element={
                                            <PortalProvider value={{ ...portalCtx, api: pluginApi }}>
                                                <ErrorBoundary>
                                                    <Suspense
                                                        fallback={
                                                            <div className="h-full flex items-center justify-center text-zinc-400 text-sm animate-pulse">
                                                                Loading...
                                                            </div>
                                                        }
                                                    >
                                                        <r.Component />
                                                    </Suspense>
                                                </ErrorBoundary>
                                            </PortalProvider>
                                        }
                                    />
                                );
                            })}
                            <Route
                                path="*"
                                element={
                                    currentRouteValid ? null : <Navigate to={routes[0].path} />
                                }
                            />
                        </Routes>
                    </main>
                </div>
                {showPluginManager && (
                    <PluginManager
                        plugins={plugins}
                        disabledIds={disabledIds}
                        onToggle={togglePlugin}
                        onClose={() => setShowPluginManager(false)}
                    />
                )}
        </PluginRegistryProvider>
    );
}
