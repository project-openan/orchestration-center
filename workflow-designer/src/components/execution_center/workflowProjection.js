// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { hasRoleTasks } from '../orchestration_center/workflow/rolePolicy.js';

/** Keep role graph/identity intact; only original task IDs can receive status. */
export const projectRoleExecution = (template, runtime) => {
    if (!hasRoleTasks(template)) return runtime || template;
    const tasks = new Map((runtime?.steps || []).flatMap(step => step.subtasks || [])
        .filter(task => typeof task.task_id === 'string').map(task => [task.task_id, task]));
    return { ...template, steps: template.steps.map(step => ({ ...step,
        subtasks: step.subtasks.map(task => {
            const actual = tasks.get(task.task_id);
            return { ...task,
                status: actual?.status ?? task.status,
                ...(task.binding === 'role' && actual?.binding === 'instance'
                    ? { runtimeInstance: actual.agent, runtimeSkill: actual.skill } : {}),
            };
        }),
    })) };
};

export const roleTemplateFromEvents = (events = []) => {
    for (const event of events || []) {
        const template = event.type === 'resolution' ? event.data?.resolution_snapshot?.template
            : event.type === 'psop_update' ? event.data?.psop : null;
        try {
            const parsed = typeof template === 'string' ? JSON.parse(template) : template;
            if (hasRoleTasks(parsed)) return parsed;
        } catch {
            // A malformed history event is not a source of template identity.
        }
    }
    return null;
};
