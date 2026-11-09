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
import React, { useState, useEffect } from 'react';
import { getAgentCards } from '@/service/api.js';
import { useTranslation } from 'react-i18next';
import TemplatePalette from './TemplatePalette.jsx';

export default function Sidebar({ isDark }) {
    const { t } = useTranslation();
    const [agentGroups, setAgentGroups] = useState([]);
    const [loading, setLoading] = useState(true);
    useEffect(() => {
        let cancelled = false;
        getAgentCards().then(response => {
            if (!cancelled) setAgentGroups(response.data || []);
        }).catch(error => console.error('Failed to fetch agents:', error))
            .finally(() => { if (!cancelled) setLoading(false); });
        return () => { cancelled = true; };
    }, []);
    if (loading) return <div className={`p-4 text-xs ${isDark ? 'text-zinc-500' : 'text-zinc-400'}`}>{t('common.loading')}</div>;
    const items = agentGroups.map(info => {
        const key = info.name || info.id;
        const defaultTask = t('workflow.sidebar.defaultTask', { name: info.name || key });
        return { id: key, label: info.displayName || key, description: info.description,
            template: { agent: key, skill: info.skills?.[0]?.name || '', skillsList: info.skills || [],
                inputs: {}, outputs: {}, description: defaultTask, defaultTask } };
    });
    return <TemplatePalette title={t('workflow.sidebar.title')} items={items} isDark={isDark} />;
}
