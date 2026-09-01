// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';
import path from 'path';

const root = import.meta.dirname;

export default defineConfig({
    server: {
        port: 5101,
        cors: true,
    },
    plugins: [
        react(),
        federation({
            dts: false,
            name: 'orchestration_center',
            filename: 'remoteEntry.js',
            exposes: {
                './plugin.manifest': './plugin.manifest.js',
                './src/index': './src/index.jsx',
            },
            shared: {
                react: { singleton: true, requiredVersion: '^18.0.0' },
                'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
                'react-router-dom': { singleton: true },
                'react-i18next': { singleton: true },
                i18next: { singleton: true },
                'lucide-react': { singleton: true },
                axios: { singleton: true },
                'js-yaml': { singleton: true },
                '@openan/portal-sdk': { singleton: true },
            },
        }),
    ],
    resolve: {
        alias: {
            '@openan/portal-sdk': path.resolve(root, '../../packages/portal-sdk/src/index.js'),
            '@openan/shared-workflow': path.resolve(root, '../../packages/shared-workflow/src/index.js'),
            '@': path.resolve(root, '../../portal/src'),
        },
    },
    optimizeDeps: {
        exclude: ['@openan/portal-sdk', '@openan/shared-workflow'],
    },
    build: {
        target: 'esnext',
        minify: true,
        outDir: 'dist',
    },
});

