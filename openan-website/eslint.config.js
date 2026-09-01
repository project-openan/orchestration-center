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

import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';

export default [
    { ignores: ['**/node_modules/**', '**/dist/**', '**/coverage/**'] },
    js.configs.recommended,
    {
        files: ['**/*.{js,jsx}'],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: 'module',
            parserOptions: { ecmaFeatures: { jsx: true } },
            globals: { ...globals.browser },
        },
        plugins: {
            'react-hooks': reactHooks,
            'react-refresh': reactRefresh,
        },
        rules: {
            ...reactHooks.configs.recommended.rules,
            'react-refresh/only-export-components': [
                'warn',
                { allowConstantExport: true },
            ],
            'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
            // Initial auth/theme checks legitimately call setState in an effect.
            // This rule is overly cautious for that common pattern.
            'react-hooks/set-state-in-effect': 'off',
        },
    },
    {
        // Node.js config files & scripts — allow process, __dirname, require
        files: ['**/vite.config.js', '**/tailwind.config.js', '**/postcss.config.js', '**/eslint.config.js', 'scripts/**/*.js'],
        languageOptions: {
            globals: { ...globals.node, ...globals.browser },
        },
        rules: {
            'no-undef': 'off',
        },
    },
];
