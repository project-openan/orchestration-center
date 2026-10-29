// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

/** Accept either a design PSOP or canvas nodes; never infer roles from names. */
export const hasRoleTasks = (workflowOrNodes) => {
    const steps = Array.isArray(workflowOrNodes) ? workflowOrNodes : workflowOrNodes?.steps || [];
    return steps.some(step => (step.subtasks || step.data?.subtasks || []).some(task => task.binding === 'role'));
};

/**
 * One entry is acceptable when it is explicitly approved or carries no
 * review_status at all: the /role-catalog endpoint serves an approved-only
 * projection whose entries have no review_status field, while a raw catalog
 * release marks drafts explicitly. Drafts never authorize. The backend
 * CatalogGate stays the final authority.
 */
export const isApprovedEntry = (entry) => (
    entry.review_status === undefined || entry.review_status === 'approved'
);

/**
 * Approved (role_id@role_version#skill_id) triples of one exact catalog
 * release. Drafts never authorize. Returns null when the catalog release is
 * unavailable, in which case the frontend cannot pre-check and the backend
 * CatalogGate stays the only authority.
 */
export const approvedRoleSkills = (catalog) => {
    if (!catalog) return null;
    const approved = new Set();
    for (const role of catalog.roles || []) {
        if (!isApprovedEntry(role)) continue;
        for (const skill of role.skills || []) {
            if (isApprovedEntry(skill)) {
                approved.add(`${role.role_id}@${role.role_version}#${skill.skill_id}`);
            }
        }
    }
    return approved;
};

export const isApprovedRoleSkill = (catalog, agent, roleVersion, skill) => {
    const approved = approvedRoleSkills(catalog);
    return approved !== null && approved.has(`${agent}@${roleVersion}#${skill}`);
};

/**
 * Advisory pre-save check mirroring the backend CatalogGate. Returns one
 * issue per role task whose (role, version, skill) is not approved in the
 * exact release; an unavailable catalog yields no frontend verdict.
 */
export const findInvalidRoleReferences = (nodes, catalog) => {
    const approved = approvedRoleSkills(catalog);
    if (!approved) return [];
    const issues = [];
    for (const node of nodes) {
        for (const task of node.data?.subtasks || []) {
            if (task.binding !== 'role') continue;
            if (!approved.has(`${task.agent}@${task.role_version}#${task.skill}`)) {
                issues.push({
                    node_id: node.id,
                    node_label: node.data?.label || node.id,
                    task_id: task.task_id,
                    agent: task.agent,
                    role_version: task.role_version,
                    skill: task.skill,
                });
            }
        }
    }
    return issues;
};

/** Role tasks sharing one binding group, in canvas order. */
export const groupRoleTasks = (nodes, bindingGroup) => {
    if (!bindingGroup) return [];
    const members = [];
    for (const node of nodes) {
        for (const task of node.data?.subtasks || []) {
            if (task.binding === 'role' && task.binding_group === bindingGroup) {
                members.push({ node_id: node.id, node_label: node.data?.label || node.id, task });
            }
        }
    }
    return members;
};

export const filterNodeChanges = (changes, nodes, protectedWorkflow) => changes.filter(change => {
    if (protectedWorkflow) return ['position', 'dimensions', 'select'].includes(change.type);
    if (change.type !== 'remove') return true;
    const node = nodes.find(item => item.id === change.id);
    return node?.type !== 'startNode' && node?.type !== 'endNode';
});

export const filterEdgeChanges = (changes, protectedWorkflow) => (
    protectedWorkflow ? changes.filter(change => change.type === 'select') : changes
);
