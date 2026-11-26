// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

export const formatWorkflowError = (detail) => {
    if (typeof detail === 'string') return detail;
    const message = typeof detail?.error === 'string' ? detail.error
        : typeof detail?.message === 'string' ? detail.message : 'Execution failed';
    const evidence = ['code', 'reason', 'instance_id', 'binding_group']
        .filter(key => typeof detail?.[key] === 'string').map(key => `${key}: ${detail[key]}`);
    for (const key of ['task_ids', 'role_ids']) {
        const values = Array.isArray(detail?.[key]) ? detail[key].filter(value => typeof value === 'string') : [];
        if (values.length) evidence.push(`${key}: ${values.join(', ')}`);
    }
    return [message, ...evidence].join(' · ');
};

/** Only exact original IDs identify tasks; SDK IDs/names never imply a match. */
export const annotateWorkflowErrors = (nodes, detail) => {
    const taskIds = new Set(Array.isArray(detail?.task_ids) ? detail.task_ids : []);
    return nodes.map(node => ({ ...node, data: {
        ...node.data,
        executionError: (node.data?.subtasks || []).some(task => taskIds.has(task.task_id))
            ? formatWorkflowError(detail) : null,
    } }));
};

export const formatRoleResolution = (detail) => {
    const fields = (value, keys) => keys.filter(key => typeof value?.[key] === 'string')
        .map(key => `${key}: ${value[key]}`).join(' · ');
    return [fields(detail, ['execution_id', 'catalog_version', 'execution_scope']),
        ...(Array.isArray(detail?.bindings) ? detail.bindings : []).map(binding => fields(binding,
            ['task_id', 'role_id', 'role_version', 'role_skill_id', 'instance_id', 'execution_skill', 'binding_group', 'selection_reason']))]
        .filter(Boolean).join('\n');
};

export const errorStepNames = (workflow, detail) => {
    const taskIds = new Set(Array.isArray(detail?.task_ids) ? detail.task_ids : []);
    return (workflow?.steps || []).filter(step => step.subtasks?.some(task => taskIds.has(task.task_id)))
        .map(step => step.name);
};
