// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

const root = import.meta.dirname;
const workspaceRoot = path.resolve(root, '..');

/**
 * openan-plugin-discovery — convention-based plugin auto-discovery.
 *
 * Scans plugins/<name>/plugin.manifest.js under the workspace root at
 * server start / build time and exposes the registry as a virtual module:
 *
 *     import pluginRegistry from 'virtual:openan-plugins';
 *
 * Adding a plugin = drop a folder under plugins/. No Portal code changes,
 * no config edits. Per-delivery overrides live in plugins/plugin-overrides.json
 * (plain JSON readable by ops); disabled plugins are omitted from the
 * generated module entirely, so their code is fully tree-shaken from
 * production builds.
 *
 * Note: import.meta.glob cannot be used here because plugins/ lives outside
 * the Vite root (portal/) and Vite globs do not support ../ patterns.
 */
function openanPluginDiscovery() {
    const virtualModuleId = 'virtual:openan-plugins';
    const resolvedVirtualId = '\0' + virtualModuleId;
    const pluginsDir = path.resolve(workspaceRoot, 'plugins');

    function buildModuleCode() {
        const overridesPath = path.join(pluginsDir, 'plugin-overrides.json');
        let overrides = {};
        if (fs.existsSync(overridesPath)) {
            overrides = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'));
        }

        const names = fs.readdirSync(pluginsDir, { withFileTypes: true })
            .filter((d) => d.isDirectory())
            .map((d) => d.name)
            .filter((name) =>
                fs.existsSync(path.join(pluginsDir, name, 'plugin.manifest.js'))
            )
            .filter((name) => overrides[name]?.enabled !== false);

        const entries = names.map((name) => {
            const manifestPath = path
                .join(pluginsDir, name, 'plugin.manifest.js')
                .split(path.sep)
                .join('/');
            return `    { id: ${JSON.stringify(name)}, enabled: true, manifest: () => import(${JSON.stringify(manifestPath)}) },`;
        });

        return `export default {\n    plugins: [\n${entries.join('\n')}\n    ],\n};\n`;
    }

    return {
        name: 'openan-plugin-discovery',
        resolveId(id) {
            if (id === virtualModuleId) return resolvedVirtualId;
            return null;
        },
        load(id) {
            if (id === resolvedVirtualId) return buildModuleCode();
            return null;
        },
        handleHotUpdate({ file, server }) {
            // Re-scan when a manifest or overrides file changes (e.g. a new
            // plugin folder is dropped in while the dev server is running).
            if (file.startsWith(pluginsDir)) {
                const mod = server.moduleGraph.getModuleById(resolvedVirtualId);
                if (mod) server.moduleGraph.invalidateModule(mod);
                server.ws.send({ type: 'full-reload' });
                return [];
            }
            return undefined;
        },
    };
}

export default defineConfig({
    base: '/',
    server: {
        port: 3003,
        fs: { allow: [workspaceRoot] },
        proxy: {
            '/api/orchestrate': {
                target: process.env.BACKEND_URL || 'http://127.0.0.1:5001',
                changeOrigin: true, secure: false,
                rewrite: (p) => p.replace(/^\/api\/orchestrate/, ''),
            },
            '/api/registry': {
                target: process.env.REGISTRY_URL || 'http://127.0.0.1:5000',
                changeOrigin: true, secure: false,
                rewrite: (p) => p.replace(/^\/api\/registry/, ''),
            },
        },
    },
    plugins: [
        react(),
        openanPluginDiscovery(),
    ],
    resolve: {
        alias: {
            '@': path.resolve(root, 'src'),
            '@openan/portal-sdk': path.resolve(workspaceRoot, 'packages/portal-sdk/src/index.js'),
        },
    },
    optimizeDeps: {
        include: [
            'react', 'react-dom', 'react-dom/client', 'react/jsx-dev-runtime',
            'react-router-dom', 'react-i18next', 'i18next', 'i18next-browser-languagedetector',
            'axios', 'lucide-react', 'framer-motion', 'js-yaml',
            'react-markdown', 'remark-gfm',
            '@xyflow/react', 'dagre', '@tisoap/react-flow-smart-edge',
            'recharts', 'libgif', 'mobile-drag-drop',
        ],
    },
    test: { environment: 'jsdom' },
});
