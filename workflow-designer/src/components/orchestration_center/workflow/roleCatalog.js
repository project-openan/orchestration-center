// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useState } from 'react';
import { getRoleCatalog } from '@/service/api.js';
import { isApprovedRoleSkill } from './rolePolicy.js';

/** Saved designs require an exact release. Only a new canvas may request the current release. */
export const useRoleCatalog = (version, enabled, { allowLatest = false } = {}) => {
    const [result, setResult] = useState(null);
    const request = version || (allowLatest ? '__current__' : null);
    useEffect(() => {
        if (!enabled || !request) return;
        let cancelled = false;
        getRoleCatalog(version || undefined).then(catalog => {
            if (!cancelled) setResult({ request, catalog: catalog?.catalog_version && (!version || catalog.catalog_version === version) ? catalog : null });
        }).catch(() => {
            if (!cancelled) setResult({ request, catalog: null });
        });
        return () => { cancelled = true; };
    }, [version, enabled, request]);
    const current = result?.request === request ? result : null;
    return { catalog: enabled ? current?.catalog || null : null,
        loading: enabled && Boolean(request) && current === null,
        unavailable: enabled && (!request || (current !== null && !current.catalog)) };
};

export const decorateRoleNodes = (nodes, catalog) => nodes.map(node => ({ ...node, data: {
    ...node.data,
    ...(node.data?.subtasks ? { subtasks: node.data.subtasks.map(task => {
        const { roleName: _roleName, skillName: _skillName, ...identity } = task;
        if (task.binding !== 'role') return identity;
        const role = catalog?.roles?.find(role => role.role_id === task.agent && role.role_version === task.role_version);
        const skill = role?.skills?.find(skill => skill.skill_id === task.skill);
        return skill ? { ...identity, roleName: role.name, skillName: skill.name } : identity;
    }) } : {}),
    roleReferenceInvalid: Boolean(catalog) && (node.data?.subtasks || []).some(task => task.binding === 'role'
        && !isApprovedRoleSkill(catalog, task.agent, task.role_version, task.skill)),
} }));
