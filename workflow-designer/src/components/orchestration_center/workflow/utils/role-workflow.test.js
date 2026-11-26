// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, expect, it } from 'vitest';
import { transformWorkflowToReactFlow, transformReactFlowToPSOP } from './index.jsx';

const roleTemplate = () => ({
    id: 'role-template', name: 'Role design', description: 'Original intent',
    catalog_version: 'catalog-1', related_preflow: 'pre-1', user_intent: 'Optimize',
    source: 'solution_package', created_at: '2026-10-23T00:00:00Z', tags: ['test'],
    steps: [
        { name: 'first', type: 'AllSuccess', layer: 0, context_from: null, next: null,
            subtasks: [{ task_id: 'original-1', binding: 'role', agent: 'optimizer',
                role_version: '1', skill: 'explore', binding_group: 'session',
                description: 'Explore', status: 'pending' }] },
        { name: 'parallel', type: 'SelfLoop', layer: 2, context_from: ['first'], next: [],
            subtasks: [{ task_id: 'local', binding: 'instance', agent: 'Host',
                skill: 'merge', description: 'Merge', status: 'pending' }] },
    ],
});

function freeze(value) {
    if (value && typeof value === 'object') {
        Object.values(value).forEach(freeze);
        Object.freeze(value);
    }
    return value;
}

describe('role design serialization', () => {
    it('imports a deeply frozen template without mutating it or adding serial dependencies', () => {
        const template = freeze(roleTemplate());
        const { edges } = transformWorkflowToReactFlow(template);
        expect(edges.some(edge => edge.source === 'first' && edge.target === 'parallel')).toBe(false);
    });

    it('preserves mixed workflow semantics and every defined design field', () => {
        const template = roleTemplate();
        const graph = transformWorkflowToReactFlow(template);
        expect(transformReactFlowToPSOP(graph.nodes, graph.edges, template)).toEqual(template);
    });

    it('keeps design identity when runtime nodes contain instance names and statuses', () => {
        const template = roleTemplate();
        const graph = transformWorkflowToReactFlow(template);
        graph.nodes[1].data.subtasks[0].agent = 'runtime-instance';
        graph.nodes[1].data.subtasks[0].binding = 'instance';
        graph.nodes[1].data.subtasks[0].status = 'success';
        const exported = transformReactFlowToPSOP(graph.nodes, graph.edges, {
            ...template, name: 'Renamed', description: 'Updated', tags: ['updated'],
        });
        expect(exported.steps).toEqual(template.steps);
        expect(exported.name).toBe('Renamed');
        expect(exported.tags).toEqual(['updated']);
        expect(template.steps[0].subtasks[0].agent).toBe('optimizer');
        exported.steps[0].subtasks[0].agent = 'changed-export';
        expect(template.steps[0].subtasks[0].agent).toBe('optimizer');
        exported.tags.push('another');
        expect(template.tags).toEqual(['test']);
    });

    it('preserves explicit null metadata and can export a detached imported graph', () => {
        const template = { ...roleTemplate(), description: null, tags: null };
        const graph = transformWorkflowToReactFlow(template);
        expect(transformReactFlowToPSOP(graph.nodes, graph.edges, template)).toEqual(template);
        const { steps, ...metadata } = template;
        expect(transformReactFlowToPSOP(graph.nodes, graph.edges, metadata).steps).toEqual(steps);
    });

    it('fails closed when a role graph lacks its design snapshot', () => {
        const nodes = [{ type: 'agentNode', data: { subtasks: roleTemplate().steps[0].subtasks } }];
        expect(() => transformReactFlowToPSOP(nodes, [], {})).toThrow('design snapshot');
    });

    it('does not serialize UI fields even for instance tasks', () => {
        const template = roleTemplate();
        delete template.catalog_version;
        template.steps = [template.steps[1]];
        template.steps[0].subtasks[0].skillsList = [{ name: 'merge' }];
        template.steps[0].subtasks[0].editable = true;
        const graph = transformWorkflowToReactFlow(template);
        const exported = transformReactFlowToPSOP(graph.nodes, graph.edges, template);
        expect(exported.steps[0].subtasks[0]).not.toHaveProperty('skillsList');
        expect(exported.steps[0].subtasks[0]).not.toHaveProperty('editable');
        expect(exported.steps[0].subtasks[0].task_id).toBe('local');
    });
});
