// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

// A host is any registered agent; the centre derives the actual host from the
// PSOP (workflow_host / the SelfLoop task agent). Card skills are not markers.
export function listWorkflowHosts(cards) {
    const names = new Map();
    for (const card of cards) {
        names.set(card.name, (names.get(card.name) || 0) + 1);
    }
    return cards.filter(card => names.get(card.name) === 1);
}

export function declaredWorkflowHost(workflow) {
    const names = new Set([
        workflow.workflow_host,
        ...(workflow.steps || []).flatMap(step => step.type === 'SelfLoop'
            ? (step.subtasks || []).map(task => task.agent)
            : []),
    ].filter(value => typeof value === 'string' && value.trim()).map(value => value.trim()));
    return { name: names.values().next().value, conflicting: names.size > 1 };
}

