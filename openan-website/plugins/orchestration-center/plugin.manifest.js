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

import { Share2 } from 'lucide-react';

export default {
    id: 'orchestration-center',
    name: 'Orchestration Center',
    version: '0.1.0',
    menu: [{
        id: 'orchestration',
        labelKey: 'orchestration-center:orchestration.title',
        icon: Share2,
        order: 2,
        route: '/orchestration',
    }],
    routes: [{
        path: '/orchestration',
        component: () => import('./src/index.jsx'),
        menuId: 'orchestration',
    }],
    i18n: {
        namespace: 'orchestration-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },
};
