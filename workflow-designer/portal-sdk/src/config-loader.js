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

import { validateManifest } from './plugin-manifest.js';

/**
 * Load and validate all enabled plugins from a portal configuration object.
 *
 * The config shape (from portal/plugins.config.js):
 * {
 *   plugins: [
 *     { id: 'orchestration-center', enabled: true, manifest: () => import('...') },
 *     { id: 'skill-center',         enabled: false, manifest: () => import('...') },
 *   ]
 * }
 *
 * Disabled plugins are never imported (tree-shaken in production builds).
 *
 * @param {{ plugins: Array<{ id: string, enabled: boolean, manifest: () => Promise<{ default: import('./plugin-manifest.js').PluginManifest }> }}> }} config
 * @returns {Promise<import('./plugin-manifest.js').PluginManifest[]>} — validated manifests, sorted by first menu item order
 */
export async function loadEnabledPlugins(config) {
    if (!config || !Array.isArray(config.plugins)) {
        return [];
    }

    const enabled = config.plugins.filter((p) => p.enabled);
    if (enabled.length === 0) {
        return [];
    }

    const modules = await Promise.all(
        enabled.map(async (p) => {
            if (typeof p.manifest !== 'function') {
                throw new Error(
                    `Plugin "${p.id}" has no manifest loader. ` +
                    'Expected: { manifest: () => import("...") }'
                );
            }
            const mod = await p.manifest();
            return mod.default || mod;
        })
    );

    const manifests = modules.map(validateManifest);

    // Sort by the first menu item's order for stable navigation layout
    manifests.sort((a, b) => {
        const ao = a.menu?.[0]?.order ?? 999;
        const bo = b.menu?.[0]?.order ?? 999;
        return ao - bo;
    });

    return manifests;
}
