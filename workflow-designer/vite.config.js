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
import {defineConfig} from 'vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'
import path from 'path';
import fs from 'node:fs';
import https from 'node:https';
import {visualizer} from 'rollup-plugin-visualizer';

// https://vite.dev/config/
export default ({ mode }) => defineConfig({
    base: '/',
    server: {
        port: 3003,
        // Only reached by a client defaulted (or explicitly set) to gateway
        // mode -- e.g. `npm run dev -- --host` on a LAN, where the page
        // isn't loaded from localhost (see getBaseUrl()/shouldDefaultToGateway
        // in src/service/api.js). Mirrors nginx.conf.template's
        // /api/orchestrate/ location: strip the prefix, forward to the
        // backend root. BACKEND_URL/BACKEND_INSECURE let this point at a
        // remote or HTTPS (self-signed) backend without editing this file.
        proxy: (() => {
            const proxyTarget = process.env.BACKEND_URL ||
                `${mode === 'https' ? 'https' : 'http'}://127.0.0.1:5001`;
            const proxyOptions = {
                target: proxyTarget,
                changeOrigin: true,
                secure: false,
                rewrite: (path) => path.replace(/^\/api\/orchestrate/, ''),
            };

            // mTLS is enabled by the backend's secure default. The dev proxy
            // presents a local client certificate when the operator generated
            // one; absence keeps HTTP/non-mTLS development working unchanged.
            const proxyKey = process.env.PROXY_TLS_KEY || path.resolve(__dirname, '../etc/ssl/dev-proxy-client.key');
            const proxyCert = process.env.PROXY_TLS_CERT || path.resolve(__dirname, '../etc/ssl/dev-proxy-client.cer');
            if (fs.existsSync(proxyKey) && fs.existsSync(proxyCert)) {
                proxyOptions.agent = new https.Agent({
                    key: fs.readFileSync(proxyKey),
                    cert: fs.readFileSync(proxyCert),
                    rejectUnauthorized: false,
                });
            }

            return {
                '/api/orchestrate': proxyOptions,
            };
        })(),
    },
    plugins: [
        react(),
        ...(mode === 'https' ? [basicSsl()] : []),
        visualizer({
        open: false,
        filename: 'stats.html',
        gzipSize: true,
        brotliSize: true,
        }),
    ],
    resolve: {
        alias: {
            '@': path.resolve(__dirname, 'src'),
        },
    },
    assetsInclude: ["**/*.PNG"],
    test: {
        environment: 'jsdom',
    },
    build: {
        minify: 'esbuild',
        rollupOptions: {
            output: {
                manualChunks: (id) => {
                    if (id.includes('node_modules')) {
                        return 'vendor';
                    }
                }
            }
        }
    }
})
