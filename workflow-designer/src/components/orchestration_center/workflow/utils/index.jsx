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
import dagre from 'dagre';

/**
 * Backend standard state enumeration
 */
export const BACKEND_STATUS = {
    PENDING: 'pending',
    RUNNING: 'running',
    SUCCESS: 'success',
    FAILED: 'failed'
};

export const normalizeStatus = (status) => {
    const s = String(status || '').toLowerCase().trim();
    if (s.includes('run') || s === 'executing' || s === 'active' || s === 'processing' || s === 'started' || s === 'running') return BACKEND_STATUS.RUNNING;
    if (s.includes('success') || s === 'completed' || s === 'executed' || s === 'finished') return BACKEND_STATUS.SUCCESS;
    if (s.includes('fail') || s === 'error' || s === 'stopped') return BACKEND_STATUS.FAILED;
    return BACKEND_STATUS.PENDING;
};


/**
 * 2. Dagre Automatic typesetting logic
 */
export const getLayoutedElements = (nodes, edges, direction = 'LR') => {
    const dagreGraph = new dagre.graphlib.Graph();
    dagreGraph.setDefaultEdgeLabel(() => ({}));
    dagreGraph.setGraph({ rankdir: direction, ranksep: 180, nodesep: 100 });

    nodes.forEach((node) => {
        dagreGraph.setNode(node.id, { width: node.width, height: node.height });
    });

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    let lastY = nodes.length > 0 ? (dagreGraph.node(nodes[0].id).y || 0) : 0;

    const layoutedNodes = nodes.map((node, index) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        
        let finalY = nodeWithPosition.y;
        if (direction === 'LR' && index > 0) {
            // Calculate deterministic random displacement (120 - 180px)
            let hash = 0;
            const seed = String(node.id) + index;
            for (let i = 0; i < seed.length; i++) {
                hash = seed.charCodeAt(i) + ((hash << 5) - hash);
            }
            const magnitude = (Math.abs(hash) % 60) + 120;
            const sign = (Math.abs(hash) >> 4) % 2 === 0 ? 1 : -1;
            
            // Offset based on the final Y coordinate of the previous node
            finalY = lastY + (sign * magnitude);
            
            // Security restrictions: prevent deviation from the center of the canvas too far (assuming the center is around 300)
            // If the calculated position is too far fetched, pull it back towards the center
            const centerDistance = finalY - nodeWithPosition.y;
            if (Math.abs(centerDistance) > 400) {
                finalY = nodeWithPosition.y + (centerDistance > 0 ? 200 : -200);
            }
        } else if (index === 0) {
            // The first node is also given an initial random displacement to avoid always being at the center
            finalY = nodeWithPosition.y + 40;
        }

        lastY = finalY;

        return {
            ...node,
            position: {
                x: nodeWithPosition.x - (node.width || 200) / 2,
                y: finalY - (node.height || 100) / 2,
            },
        };
    });

    return { nodes: layoutedNodes, edges };
};

/**
 * 3. Dynamically calculate the optimal Handle connection point
 */
export const getBestHandles = (sourceNode, targetNode) => {
    const sPos = sourceNode.position;
    const tPos = targetNode.position;

    const sCenter = { x: sPos.x + (sourceNode.width || 200) / 2, y: sPos.y + (sourceNode.height || 100) / 2 };
    const tCenter = { x: tPos.x + (targetNode.width || 200) / 2, y: tPos.y + (targetNode.height || 100) / 2 };

    // Unified change to: right-hand exit, left-hand entry
    return { sourceHandle: 's-right', targetHandle: 't-left' };
};

/**
 * 4. Import Conversion: PSOP JSON -> React Flow Nodes/Edges
 */
export const transformWorkflowToReactFlow = (rawInput) => {
    // Compatible with the {data: {steps: []}} structure returned by the API
    const data = rawInput?.data ? rawInput.data : rawInput;

    if (!data || (!data.steps && !Array.isArray(data))) {
        return { nodes: [], edges: [] };
    }

    const steps = Array.isArray(data) ? data : (data.steps || []);
    const nodes = [];
    const edges = [];
    const targetStepNames = new Set();

    steps.forEach((step, index) => {
        let nextSteps = [];
        if (step.next && Array.isArray(step.next) && step.next.length > 0) {
            nextSteps = step.next;
        } else if (index < steps.length - 1) {
            nextSteps = [{ step: steps[index + 1].name, condition: '' }];
        }
        nextSteps.forEach(link => {
            const targetId = link.step || link.target || 'END';
            if (!['END', 'end', 'END_OF_WORKFLOW', 'endNode'].includes(targetId)) targetStepNames.add(targetId);
        });
        step._normalizedNext = nextSteps;
    });

    // Generate nodes
    steps.forEach((step) => {
        const nodeId = step.name;
        // Ensure that subtasks exist
        const subtasks = step.subtasks || [
            {
                agent: step.agent || 'System',
                skill: step.skill || 'None',
                status: step.status || 'pending',
                description: step.description || ''
            }
        ];

        const agents = subtasks.map(t => t.agent).join(', ');
        const skills = subtasks.map(t => t.skill).join(', ');
        const nodeStatus = subtasks.some(t => normalizeStatus(t.status) === BACKEND_STATUS.RUNNING)
            ? BACKEND_STATUS.RUNNING
            : (subtasks.every(t => normalizeStatus(t.status) === BACKEND_STATUS.SUCCESS) ? BACKEND_STATUS.SUCCESS : BACKEND_STATUS.PENDING);


        nodes.push({
            id: nodeId,
            type: 'agentNode',
            position: { x: 0, y: 0 },
            width: 200,
            height: 100 + Math.max(subtasks.length, 1) * 60,
            data: {
                ...step,
                label: step.name,
                description: subtasks[0]?.description || '',
                agent: agents,
                skill: skills,
                status: nodeStatus,
                subtasks: subtasks,
                layer: step.layer ?? 0,
                context_from: step.context_from || null
            }
        });

        step._normalizedNext?.forEach((link, idx) => {
            const rawTarget = link.step || link.target;
            const targetId = ['end', 'END', 'endNode'].includes(rawTarget) ? 'END_OF_WORKFLOW' : rawTarget;
            edges.push({
                id: `e-${nodeId}-${targetId}-${idx}`,
                source: nodeId,
                target: targetId,
                label: link.condition || '',
                data: { condition: link.condition || '' },
                animated: nodeStatus === 'running',
                style: { stroke: '#94a3b8', strokeWidth: 2 }
            });
        });
    });

    const startNodes = steps.filter(s => !targetStepNames.has(s.name));
    if (startNodes.length > 0) {
        nodes.unshift({ id: 'START_NODE', type: 'startNode', position: { x: 0, y: 0 }, width: 120, height: 50, data: { label: 'START', status: 'completed' } });
        startNodes.forEach(sn => edges.unshift({ id: `e-start-${sn.name}`, source: 'START_NODE', target: sn.name, style: { stroke: '#94a3b8', strokeDasharray: '5,5' } }));
    }

    const terminalNodes = steps.filter(s => !s._normalizedNext || s._normalizedNext.length === 0);
    if (edges.some(e => e.target === 'END_OF_WORKFLOW') || terminalNodes.length > 0) {
        const allAgentNodesSuccess = nodes.length > 0 && nodes.every(n => n.type === 'endNode' || n.type === 'startNode' || n.data?.status === BACKEND_STATUS.SUCCESS);
        const endStatus = allAgentNodesSuccess ? BACKEND_STATUS.SUCCESS : 'pending';
        if (!nodes.find(n => n.id === 'END_OF_WORKFLOW')) {
            nodes.push({ id: 'END_OF_WORKFLOW', type: 'endNode', position: { x: 0, y: 0 }, width: 120, height: 50, data: { label: 'END', status: endStatus } });
        } else {
            const endNode = nodes.find(n => n.id === 'END_OF_WORKFLOW');
            if (endNode) endNode.data.status = endStatus;
        }
        terminalNodes.forEach(tn => edges.push({ id: `e-${tn.name}-implicit-end`, source: tn.name, target: 'END_OF_WORKFLOW', style: { stroke: '#94a3b8', strokeWidth: 2 } }));
    }

    steps.forEach(s => delete s._normalizedNext);
    const layouted = getLayoutedElements(nodes, edges, 'LR');
    const finalEdges = layouted.edges.map(edge => {
        const sourceNode = layouted.nodes.find(n => n.id === edge.source);
        const targetNode = layouted.nodes.find(n => n.id === edge.target);
        if (sourceNode && targetNode) {
            const { sourceHandle, targetHandle } = getBestHandles(sourceNode, targetNode);
            return { ...edge, sourceHandle, targetHandle };
        }
        return edge;
    });

    return { nodes: layouted.nodes, edges: finalEdges };
};

/**
 * 5. Export Conversion: React Flow Nodes/Edges -> PSOP JSON
 */
export const transformReactFlowToPSOP = (nodes, edges, metadata = {}) => {
    const psopData = {
        name: metadata.name || metadata.description || "",
        description: metadata.description || "",
        steps: [],
        tags: metadata.tags || []
    };

    if (metadata.id) {
        psopData.id = metadata.id;
    }

    const stepsMap = {};

    nodes.forEach((node) => {
        const { id, type, data } = node;
        if (['START_NODE', 'END_OF_WORKFLOW', 'startNode', 'endNode'].includes(type) ||
            ['START_NODE', 'END_OF_WORKFLOW'].includes(id)) return;

        if (type === 'agentNode') {
            let subtasks = [];
            if (data.subtasks && Array.isArray(data.subtasks)) {
                subtasks = data.subtasks.map(t => ({
                    ...t,
                    status: normalizeStatus(t.status)
                }));
            } else {
                subtasks = [{
                    description: data.description || data.label || id,
                    agent: data.agent || 'System',
                    skill: data.skill || 'None',
                    status: normalizeStatus(data.status)
                }];
            }

            stepsMap[id] = {
                name: id,
                type: data.type || "AllSuccess",
                subtasks: subtasks,
                next: [],
                layer: typeof data.layer === 'number' ? (data.layer > 1 ? 1 : data.layer) : 0,
                context_from: data.context_from && data.context_from.length > 0 ? data.context_from : null
            };
        }
    });

    edges.forEach((edge) => {
        const { source, target, label, data: edgeData } = edge;
        if (source === 'START_NODE' || !stepsMap[source]) return;

        const targetId = (target === 'END_OF_WORKFLOW') ? 'end' : target;
        stepsMap[source].next.push({
            step: targetId,
            condition: label || edgeData?.condition || ""
        });
    });

    psopData.steps = Object.values(stepsMap).map(step => {
        if (step.next.length === 0) {
            const { next, ...rest } = step;
            return rest;
        }
        return step;
    });

    return psopData;
};