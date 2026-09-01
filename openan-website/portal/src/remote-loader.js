// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Remote plugin loader — loads a plugin's UMD/IIFE bundle via dynamic
 * <script> tag and reads the global variable it exports.
 *
 * This is simpler and more reliable than Module Federation in Vite dev mode.
 * Each plugin is built as a standalone UMD bundle that sets a global variable.
 */

const loadedScripts = new Map();

function loadScript(url) {
    if (loadedScripts.has(url)) return loadedScripts.get(url);
    const promise = new Promise((resolve, reject) => {
        const script = document.createElement('script');
        script.src = url;
        script.crossOrigin = 'anonymous';
        script.onload = () => resolve();
        script.onerror = (e) => reject(new Error(`Failed to load script: ${url}`));
        document.head.appendChild(script);
    });
    loadedScripts.set(url, promise);
    return promise;
}

/**
 * Load a remote plugin by fetching its manifest and component.
 * Each plugin dev server serves a global var (e.g. window.__OPENAN_PLUGIN_registry_center)
 * that contains { manifest, component }.
 */
export async function loadRemotePlugin(entry) {
    const portMap = { 'registry-center': 5100, 'orchestration-center': 5101, 'execution-center': 5102 };
    const port = portMap[entry.id] || 5100;
    const baseUrl = `http://localhost:${port}`;

    // In Vite dev mode, we fetch the plugin's source module directly
    // and evaluate it. The plugin exports its component as default.
    // We use a dynamic import with the full URL.
    try {
        const manifestMod = await import(/* @vite-ignore */ `${baseUrl}/plugin.manifest.js`);
        const manifest = manifestMod.default || manifestMod;
        const componentMod = await import(/* @vite-ignore */ `${baseUrl}/src/index.jsx`);
        const Component = componentMod.default || componentMod;

        manifest.routes = manifest.routes.map((r) => ({
            ...r,
            component: () => Promise.resolve({ default: Component }),
        }));
        return manifest;
    } catch (err) {
        throw new Error(`Failed to load remote plugin "${entry.id}" from ${baseUrl}: ${err.message}`);
    }
}
