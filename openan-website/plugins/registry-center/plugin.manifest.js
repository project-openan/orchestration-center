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

import { LayoutDashboard } from 'lucide-react';

export default {
    id: 'registry-center',
    name: 'Registry Center',
    version: '0.1.0',
    backend: {
        gateway: '/api/registry',
    },
    menu: [{
        id: 'agents',
        labelKey: 'registry-center:registry.title',
        icon: LayoutDashboard,
        order: 1,
        route: '/registry',
    }],
    routes: [{
        path: '/registry',
        component: () => import('./src/index.jsx'),
        menuId: 'agents',
    }],
    i18n: {
        namespace: 'registry-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },
};
