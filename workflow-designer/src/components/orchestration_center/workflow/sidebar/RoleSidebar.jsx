// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import React from 'react';
import { useTranslation } from 'react-i18next';
import { isApprovedEntry } from '../rolePolicy.js';
import TemplatePalette from './TemplatePalette.jsx';

export default function RoleSidebar({ catalog, disabled, isDark }) {
    const { t } = useTranslation();
    const items = (catalog?.roles || []).filter(isApprovedEntry).map(role => ({
        id: `${role.role_id}@${role.role_version}`, label: role.name || role.role_id,
        version: role.role_version, description: role.description,
        skills: (role.skills || []).filter(isApprovedEntry).map(skill => ({
            id: skill.skill_id, label: skill.name || skill.skill_id, description: skill.description,
            template: { binding: 'role', agent: role.role_id, role_version: role.role_version,
                skill: skill.skill_id, description: skill.description || skill.name || skill.skill_id },
        })),
    })).filter(role => role.skills.length);
    return <TemplatePalette title={t('workflow.roleCanvas.roles')} items={items} isDark={isDark} disabled={disabled} />;
}
