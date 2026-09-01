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

import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './base-en.json';
import zh from './base-zh.json';

i18n.use(LanguageDetector).use(initReactI18next).init({
    resources: {
        en: { translation: en },
        zh: { translation: zh },
    },
    fallbackLng: 'en',
    detection: {
        order: ['localStorage', 'querystring', 'cookie'],
        caches: ['localStorage'],
    },
    interpolation: { escapeValue: false },
});

/**
 * Register a plugin's i18n namespace at runtime.
 * Called by the plugin registry after manifests are loaded.
 *
 * @param {string} namespace
 * @param {Object<string, Object>} resources — { en: {...}, zh: {...} }
 */
export function registerPluginI18n(namespace, resources) {
    for (const [lng, data] of Object.entries(resources)) {
        if (!i18n.hasResourceBundle(lng, namespace)) {
            i18n.addResourceBundle(lng, namespace, data, true, true);
        }
    }
}

/**
 * Load a plugin's i18n resources from its manifest declaration and register
 * them.  Returns a promise that resolves when all locales are loaded.
 *
 * @param {{ namespace: string, resources: Object<string, () => Promise<Object>> }} i18nConfig
 */
export async function loadPluginI18n(i18nConfig) {
    if (!i18nConfig || !i18nConfig.namespace) return;

    const entries = Object.entries(i18nConfig.resources || {});
    const loaded = await Promise.all(
        entries.map(async ([lng, loader]) => {
            const mod = await loader();
            return [lng, mod.default || mod];
        })
    );

    const resources = Object.fromEntries(loaded);
    registerPluginI18n(i18nConfig.namespace, resources);
}

export default i18n;
