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
import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import {
    ReactFlow,
    ReactFlowProvider,
    Controls,
    Background,
    MarkerType,
    useReactFlow,
    useNodesState,
    useEdgesState,
    useUpdateNodeInternals,
    addEdge
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CustomEdge from './CustomEdge';
import { Layers, X } from 'lucide-react';
import { useTranslation } from "react-i18next";

import AgentNode from './CustomNodes/AgentNode/index.jsx';
import { EndNode, StartNode } from "./CustomNodes/CircleNode/index.jsx";
import { SmartStepEdge } from '@tisoap/react-flow-smart-edge';
import FloatingEdge from "./CustomEdges/FloatingEdge/index.jsx";
import Toolbar from "./toolbar/index.jsx";
import ToolbarLite from "./toolbar_lite/index.jsx";
import WorkflowLoader from "./loading/index.jsx";
import PropertyPanel from "./property_panel/index.jsx";
import Sidebar from "./sidebar/index.jsx";
import { normalizeStatus, BACKEND_STATUS } from './utils/index.jsx';


const nodeTypes = {
    agentNode: AgentNode,
    startNode: StartNode,
    endNode: EndNode,
};

const edgeTypes = {
    smart: SmartStepEdge,
    floating: FloatingEdge,
    custom: CustomEdge,
};

const DetailRow = ({ label, children, isDark }) => (
    <div className={`py-3 border-b ${isDark ? 'border-zinc-800/60' : 'border-slate-100'}`}>
        <div className={`text-[11px] font-bold uppercase tracking-wide mb-1 ${isDark ? 'text-zinc-500' : 'text-slate-500'}`}>
            {label}
        </div>
        <div className={`text-sm font-medium leading-relaxed break-words ${isDark ? 'text-zinc-200' : 'text-slate-800'}`}>
            {children || '-'}
        </div>
    </div>
);

const DetailBlock = ({ title, value, emptyText, isDark }) => {
    if (!value) return null;
    return (
        <div className="space-y-2">
            <div className={`text-[11px] font-bold uppercase tracking-wide ${isDark ? 'text-zinc-500' : 'text-slate-500'}`}>
                {title}
            </div>
            <pre className={`max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg p-3 text-xs leading-relaxed ${isDark ? 'bg-zinc-900 text-zinc-300 border border-zinc-800' : 'bg-slate-50 text-slate-700 border border-slate-100'}`}>
                {typeof value === 'object' ? JSON.stringify(value, null, 2) : (value || emptyText)}
            </pre>
        </div>
    );
};

const WorkflowViewDetails = ({ selected, isDark, onClose }) => {
    const { t } = useTranslation();
    const node = selected?.node;
    if (!node) return null;

    const data = node.data || {};
    const subtasks = data.subtasks || [];
    const selectedIndex = selected.subtaskIndex;
    const selectedTask = Number.isInteger(selectedIndex) ? subtasks[selectedIndex] : null;
    const title = selectedTask?.skill || data.label || node.id;
    const panelTitle = selectedTask ? t('workflow.panel.executeSkill') : t('workflow.panel.nodeConfig');
    const selectedSkillMeta = selectedTask?.skillsList?.find(s => s.name === selectedTask.skill)
        || data.skillsList?.find(s => s.name === selectedTask?.skill);

    return (
        <div className={`flex flex-col h-full w-full transition-colors ${isDark ? 'bg-zinc-950 text-zinc-300' : 'bg-white text-slate-800'}`}>
            <div className={`flex items-center justify-between gap-3 p-4 border-b ${isDark ? 'bg-zinc-900/60 border-zinc-800' : 'bg-slate-50/80 border-slate-200/70'}`}>
                <div className="min-w-0">
                    <div className={`text-[11px] font-bold uppercase tracking-wide ${isDark ? 'text-zinc-500' : 'text-slate-500'}`}>
                        {panelTitle}
                    </div>
                    <h3 className="text-sm font-bold truncate">{title}</h3>
                </div>
                <button
                    type="button"
                    onClick={onClose}
                    className={`shrink-0 p-2 rounded-lg transition-colors ${isDark ? 'hover:bg-zinc-800 text-zinc-400' : 'hover:bg-slate-100 text-slate-500'}`}
                    title={t('common.close')}
                >
                    <X size={16} />
                </button>
            </div>

            <div className="p-4 space-y-5 flex-1 overflow-y-auto custom-scrollbar">
                <section>
                    <DetailRow label={t('workflow.panel.stepName')} isDark={isDark}>{data.label || data.name || node.id}</DetailRow>
                    <DetailRow label={t('workflow.panel.status')} isDark={isDark}>{data.status || '-'}</DetailRow>
                    {!selectedTask && data.description && (
                        <DetailRow label={t('workflow.panel.taskDesc')} isDark={isDark}>{data.description}</DetailRow>
                    )}
                </section>

                {selectedTask ? (
                    <section className="space-y-4">
                        <DetailRow label={t('workflow.panel.agentName')} isDark={isDark}>{selectedTask.agent}</DetailRow>
                        <DetailRow label={t('workflow.panel.executeSkill')} isDark={isDark}>{selectedTask.skill}</DetailRow>
                        <DetailRow label={t('workflow.panel.status')} isDark={isDark}>{selectedTask.status || '-'}</DetailRow>
                        <DetailRow label={t('workflow.panel.taskDesc')} isDark={isDark}>
                            {selectedTask.description || selectedSkillMeta?.description}
                        </DetailRow>
                        <DetailBlock title={t('workflow.panel.inputDefine')} value={selectedTask.inputs || selectedSkillMeta?.inputs} isDark={isDark} />
                        <DetailBlock title={t('workflow.panel.outputDefine')} value={selectedTask.outputs || selectedSkillMeta?.outputs} isDark={isDark} />
                    </section>
                ) : (
                    <section className="space-y-3">
                        <div className={`text-[11px] font-bold uppercase tracking-wide ${isDark ? 'text-zinc-500' : 'text-slate-500'}`}>
                            {t('workflow.panel.subtasks')} ({subtasks.length})
                        </div>
                        <div className="flex flex-col gap-2">
                            {subtasks.map((task, idx) => (
                                <button
                                    key={`${task.skill || 'skill'}-${idx}`}
                                    type="button"
                                    onClick={() => selected.onSelectSubtask?.(idx)}
                                    className={`text-left rounded-xl border p-3 transition-all ${isDark ? 'bg-zinc-900/60 border-zinc-800 hover:bg-zinc-900' : 'bg-slate-50 border-slate-100 hover:bg-slate-100'}`}
                                >
                                    <div className="flex items-center justify-between gap-2">
                                        <span className="text-[10px] font-bold uppercase text-blue-500 truncate">{task.agent || '-'}</span>
                                        <span className={`text-[10px] uppercase ${isDark ? 'text-zinc-500' : 'text-slate-500'}`}>{task.status || '-'}</span>
                                    </div>
                                    <div className={`mt-1 text-sm font-semibold break-words ${isDark ? 'text-zinc-200' : 'text-slate-800'}`}>
                                        {task.skill || t('node_label.no_skill')}
                                    </div>
                                    {task.description && (
                                        <p className={`mt-1 text-xs leading-relaxed line-clamp-3 ${isDark ? 'text-zinc-400' : 'text-slate-600'}`}>
                                            {task.description}
                                        </p>
                                    )}
                                </button>
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </div>
    );
};

const initialEditNodes = [
    {
        id: 'startNode',
        type: 'startNode',
        position: { x: 50, y: 300 },
        data: { description: 'this is the start node', name: 'start_node', status: 'start-event' }
    },
    {
        id: 'endNode',
        type: 'endNode',
        position: { x: 1000, y: 300 },
        data: { description: 'this is a end node.', status: 'end_node', type: 'end-event' }
    }
];

const FlowInner = ({
    mode,
    isDark,
    // View Mode Props
    viewNodes = [],
    viewEdges = [],
    onSelectChange,
    // Edit Mode Props
    importedNodes,
    importedEdges,
    workflowId,
    workflowName,
    workflowDescription,
    onCancel,
    onSaveSuccess
}) => {
    const { t } = useTranslation();
    const { screenToFlowPosition, fitView, setCenter, getNode } = useReactFlow();
    const updateNodeInternals = useUpdateNodeInternals();
    const [rfInstance, setRfInstance] = useState(null);

    const themeClasses = useMemo(() => ({
        container: isDark ? 'bg-[#0f172a] text-slate-200' : 'bg-[#f8fafc] text-slate-900',
        gridColor: isDark ? '#334155' : '#cbd5e1',
        activeEdgeColor: '#3b82f6',
        activeStrokeWidth: 2,
        inactiveEdgeColor: isDark ? '#475569' : '#94a3b8',
        inactiveStrokeWidth: 1,
        panel: isDark ? 'bg-zinc-900/80 border-zinc-700 shadow-[0_0_20px_rgba(0,0,0,0.4)]' : 'bg-white/80 border-white/20 shadow-2xl',
    }), [isDark]);

    const [viewSelectedNodeId, setViewSelectedNodeId] = useState(null);
    const [viewSelectedElement, setViewSelectedElement] = useState(null);

    const [viewPositionNodes, setViewPositionNodes] = useNodesState([]);
    const [viewPositionEdges, setViewPositionEdges] = useEdgesState([]);

    const selectViewNode = useCallback((node, subtaskIndex = null) => {
        setViewSelectedNodeId(node.id);
        setViewSelectedElement({ node, subtaskIndex });
        if (onSelectChange) onSelectChange(node);
    }, [onSelectChange]);

    const processedNodes = useMemo(() => {
        if (mode !== 'view') return [];
        return viewNodes.map(node => ({
            ...node,
            data: {
                ...node.data,
                isDark,
                selectedSubtaskIndex: node.id === viewSelectedElement?.node?.id ? viewSelectedElement.subtaskIndex : null,
                onSubtaskClick: (subtaskIndex) => selectViewNode(node, subtaskIndex),
            },
            selected: node.id === viewSelectedNodeId,
            zIndex: 100,
        }));
    }, [viewNodes, viewSelectedNodeId, viewSelectedElement, selectViewNode, isDark, mode]);

    const processedEdges = useMemo(() => {
        if (mode !== 'view') return [];

        const nodeMap = new Map();
        viewNodes.forEach(n => {
            nodeMap.set(n.id, {
                status: n.data?.status || 'not_executed',
                type: n.type
            });
        });

        const sourceOutgoingStats = new Map();
        viewEdges.forEach(edge => {
            const targetNode = nodeMap.get(edge.target);
            if (!targetNode) return;
            if (!sourceOutgoingStats.has(edge.source)) {
                sourceOutgoingStats.set(edge.source, { hasExecutedChild: false });
            }
            const stats = sourceOutgoingStats.get(edge.source);
            if (['executed', 'success'].includes(targetNode.status) && targetNode.type !== 'endNode') {
                stats.hasExecutedChild = true;
            }
        });

        return viewEdges.map(edge => {
            const sourceNode = nodeMap.get(edge.source);
            const targetNode = nodeMap.get(edge.target);
            const sourceStats = sourceOutgoingStats.get(edge.source);

            if (!sourceNode || !targetNode) {
                if (edge.target === 'END_OF_WORKFLOW' && sourceNode && ['executed', 'success'].includes(sourceNode.status)) {
                    return {
                        ...edge,
                        type: 'custom',
                        animated: true,
                        style: { ...edge.style, stroke: themeClasses.activeEdgeColor, strokeWidth: 3, opacity: 1 },
                        markerEnd: { type: MarkerType.ArrowClosed, color: themeClasses.activeEdgeColor },
                        zIndex: 10,
                    };
                }
                return {
                ...edge,
                type: 'custom',
                style: { ...edge.style, stroke: themeClasses.inactiveEdgeColor, strokeWidth: 2, opacity: 0.5 },
                markerEnd: { type: MarkerType.ArrowClosed, color: themeClasses.inactiveEdgeColor }
                };
            }

            const isSourcePassed = ['executed', 'current', 'success', 'running'].includes(sourceNode.status) || sourceNode.type === 'startNode' || sourceNode.id === 'START_NODE';
            const isTargetActive = ['executed', 'current', 'success', 'running', 'failed'].includes(targetNode.status);
            let isActive = isSourcePassed && isTargetActive;

            if (isActive && (targetNode.type === 'endNode' || targetNode.id === 'END_OF_WORKFLOW' || ['current', 'running'].includes(targetNode.status))) {
                if (sourceStats && sourceStats.hasExecutedChild) isActive = false;
            }

            if (!isActive && edge.target === 'END_OF_WORKFLOW' && ['executed', 'success'].includes(sourceNode.status)) {
                isActive = true;
            }

            return {
                ...edge,
                type: 'custom',
                label: edge.label || null,
                data: { ...edge.data, condition: edge.data?.condition || edge.label || '' },
                animated: true,
                style: {
                    ...edge.style,
                    stroke: isActive ? themeClasses.activeEdgeColor : themeClasses.inactiveEdgeColor,
                    strokeWidth: isActive ? 3 : 2,
                    opacity: isActive ? 1 : 0.6,
                },
                markerEnd: {
                    type: MarkerType.ArrowClosed,
                    color: isActive ? themeClasses.activeEdgeColor : themeClasses.inactiveEdgeColor,
                },
                zIndex: isActive ? 10 : 0,
            };
        });
    }, [viewEdges, viewNodes, themeClasses, mode]);

    useEffect(() => {
        if (mode !== 'view') return;

        setViewPositionNodes(prev => {
            if (processedNodes.length === 0) return [];
            if (prev.length === 0) return processedNodes;

            const nextNodeIds = new Set(processedNodes.map(node => node.id));
            const sameGraph = prev.length === processedNodes.length && prev.every(node => nextNodeIds.has(node.id));
            const prevPositions = sameGraph ? new Map(prev.map(n => [n.id, n.position])) : new Map();

            return processedNodes.map(node => ({
                ...node,
                position: prevPositions.get(node.id) || node.position,
            }));
        });
        setViewPositionEdges(processedEdges);
    }, [processedNodes, processedEdges, mode, setViewPositionNodes, setViewPositionEdges]);

    useEffect(() => {
        if (mode !== 'view' || viewPositionNodes.length === 0) return;
        const frame = requestAnimationFrame(() => {
            viewPositionNodes.forEach(node => updateNodeInternals(node.id));
        });
        return () => cancelAnimationFrame(frame);
    }, [mode, viewPositionNodes, viewSelectedNodeId, updateNodeInternals]);

    const lastCenteredNodeId = useRef(null);

    useEffect(() => {
        if (mode === 'view' && viewNodes.length > 0) {
            // Priority 1: Specifically marked 'running' or 'current' nodes
            let activeNode = viewNodes.find(n => {
                const s = String(n.data?.status || '').toLowerCase().trim();
                if (n.type === 'startNode' || n.type === 'endNode') return false;
                return (s === 'running' || s === 'executing' || s === 'current' || s === 'active' || s === 'processing');
            });

            // Priority 2: Nodes that are NOT pending or success (like failed)
            if (!activeNode) {
                activeNode = viewNodes.find(n => {
                    const normalizedStatus = normalizeStatus(n.data?.status);
                    if (n.type !== 'agentNode') return false;
                    return normalizedStatus !== BACKEND_STATUS.PENDING && normalizedStatus !== BACKEND_STATUS.SUCCESS;
                });
            }

            // Priority 3: The last 'success' node (if no focus otherwise)
            if (!activeNode) {
                const successNodes = viewNodes.filter(n => normalizeStatus(n.data?.status) === BACKEND_STATUS.SUCCESS && n.type === 'agentNode');
                if (successNodes.length > 0) {
                    activeNode = successNodes[successNodes.length - 1];
                }
            }

            if (activeNode) {
                if (activeNode.id !== lastCenteredNodeId.current) {
                    lastCenteredNodeId.current = activeNode.id;

                    // Auto-select to visually emphasize the node
                    setViewSelectedNodeId(activeNode.id);

                    const timer = setTimeout(() => {
                        const internalNode = getNode(activeNode.id);
                        const width = internalNode?.measured?.width || activeNode.width || 260;
                        const height = internalNode?.measured?.height || activeNode.height || 110;

                        const centerX = activeNode.position.x + width / 2;
                        const centerY = activeNode.position.y + height / 2;

                        setCenter(centerX, centerY, { zoom: 1.25, duration: 1200 });
                    }, 100);
                    return () => clearTimeout(timer);
                }
            } else if (!lastCenteredNodeId.current) {
                const timer = setTimeout(() => {
                    fitView({ padding: 0.2, duration: 1000 });
                }, 200);
                return () => clearTimeout(timer);
            }
        } else if (mode === 'view' && viewNodes.length === 0) {
            lastCenteredNodeId.current = null;
            setViewSelectedElement(null);
        }
    }, [viewNodes, setCenter, getNode, fitView, mode]);

    useEffect(() => {
        if (mode !== 'view' || !viewSelectedElement) return;
        const latestNode = viewNodes.find(node => node.id === viewSelectedElement.node.id);
        if (!latestNode) {
            setViewSelectedElement(null);
            setViewSelectedNodeId(null);
            return;
        }
        if (latestNode !== viewSelectedElement.node) {
            setViewSelectedElement({ ...viewSelectedElement, node: latestNode });
        }
    }, [mode, viewNodes, viewSelectedElement]);



    const [editNodes, setEditNodes, onNodesChange] = useNodesState(initialEditNodes);
    const [editEdges, setEditEdges, onEdgesChange] = useEdgesState([]);
    const [selectedElement, setSelectedElement] = useState(null);
    const [isDirty, setIsDirty] = useState(false);
    const [showExitConfirm, setShowExitConfirm] = useState(false);
    const [phenomenon, setPhenomenon] = useState('');

    useEffect(() => {
        if (mode === 'edit' && importedNodes?.length > 0) {
            setEditNodes(importedNodes.map(node => ({ ...node, zIndex: 100, data: { ...node.data, isDark } })));
            setIsDirty(false);
        }
    }, [importedNodes, setEditNodes, mode]);

    useEffect(() => {
        if (mode === 'edit') {
            setEditNodes(nds => nds.map(node => ({
                ...node,
                data: { ...node.data, isDark }
            })));
        }
    }, [isDark, mode, setEditNodes]);

    useEffect(() => {
        if (mode === 'edit' && importedEdges?.length > 0) {
            setEditEdges(importedEdges.map(edge => ({
                ...edge,
                type: 'custom',
                data: { ...edge.data, condition: edge.data?.condition || edge.label || '' },
                zIndex: 0,
                animated: true,
                style: { strokeWidth: 3, stroke: isDark ? '#3b82f6' : '#2563eb' },
            })));
            setIsDirty(false);
        }
    }, [importedEdges, setEditEdges, mode]);

    useEffect(() => {
        if (mode === 'edit') {
            setEditEdges(eds => eds.map(edge => ({
                ...edge,
                style: { ...edge.style, stroke: isDark ? '#3b82f6' : '#2563eb' },
            })));
        }
    }, [isDark, mode, setEditEdges]);

    // Track changes for isDirty
    const onNodesChangeWithDirty = useCallback((changes) => {
        onNodesChange(changes);
        const hasChange = changes.some(c => c.type === 'position' || c.type === 'remove' || c.type === 'add' || c.type === 'reset');
        if (hasChange) setIsDirty(true);
    }, [onNodesChange]);

    const onEdgesChangeWithDirty = useCallback((changes) => {
        onEdgesChange(changes);
        const hasChange = changes.some(c => c.type === 'remove' || c.type === 'add' || c.type === 'reset');
        if (hasChange) setIsDirty(true);
    }, [onEdgesChange]);

    useEffect(() => {
        const handleBeforeUnload = (e) => {
            if (isDirty && mode === 'edit') {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => window.removeEventListener('beforeunload', handleBeforeUnload);
    }, [isDirty, mode]);

    const handleCancel = useCallback(() => {
        if (isDirty) {
            setShowExitConfirm(true);
        } else {
            onCancel();
        }
    }, [isDirty, onCancel]);

    const handleSaveSuccess = useCallback(() => {
        setIsDirty(false);
        if (onSaveSuccess) onSaveSuccess();
    }, [onSaveSuccess]);

    const onDeleteSelected = useCallback(() => {
        if (!selectedElement) return;
        if (selectedElement.id === 'startNode' || selectedElement.id === 'endNode') return;

        if (editNodes.some(n => n.id === selectedElement.id)) {
            setEditNodes((nds) => nds.filter((node) => node.id !== selectedElement.id));
            setEditEdges((eds) => eds.filter((edge) => edge.source !== selectedElement.id && edge.target !== selectedElement.id));
        } else {
            setEditEdges((eds) => eds.filter((edge) => edge.id !== selectedElement.id));
        }
        setSelectedElement(null);
    }, [selectedElement, editNodes, setEditNodes, setEditEdges]);

    const onNodeDragStop = useCallback((event, node) => {
        if (mode !== 'edit' || !node || node.type !== 'agentNode' || !rfInstance) return;

        const allNodes = rfInstance.getNodes();
        const targetNode = allNodes.find(n => {
            if (n.id === node.id || n.type !== 'agentNode') return false;
            const { x, y } = n.position;
            const width = n.measured?.width || n.width || 260;
            const height = n.measured?.height || n.height || 110;

            const midX = node.position.x + (node.measured?.width || node.width || 260) / 2;
            const midY = node.position.y + (node.measured?.height || node.height || 110) / 2;

            return (
                midX >= x &&
                midX <= x + width &&
                midY >= y &&
                midY <= y + height
            );
        });

        if (targetNode) {
            setEditNodes((nds) => {
                const sourceNode = nds.find(n => n.id === node.id);
                if (!sourceNode) return nds;

                const subtasksToMove = sourceNode.data.subtasks || [];
                const updatedNodes = nds.filter(n => n.id !== node.id).map(n => {
                    if (n.id === targetNode.id) {
                        const mergedSubtasks = [...(n.data.subtasks || []), ...subtasksToMove];
                        return {
                            ...n,
                            data: { ...n.data, subtasks: mergedSubtasks },
                            height: 80 + mergedSubtasks.length * 55
                        };
                    }
                    return n;
                });
                return updatedNodes;
            });

            setEditEdges((eds) => eds.filter(e => e.source !== node.id && e.target !== node.id));
            if (selectedElement?.id === node.id) setSelectedElement(null);
        }
    }, [mode, rfInstance, setEditNodes, setEditEdges, selectedElement]);

    const onConnect = useCallback((params) => {
        const newEdge = {
            ...params,
            type: 'custom',
            data: { condition: '' },
            animated: true,
            markerEnd: { type: MarkerType.ArrowClosed, color: isDark ? '#3b82f6' : '#2563eb' },
            style: { strokeWidth: 3, stroke: isDark ? '#3b82f6' : '#2563eb' }
        };
        setEditEdges((eds) => addEdge(newEdge, eds));
        setIsDirty(true);
    }, [setEditEdges, isDark]);

    const onDrop = useCallback((event) => {
        event.preventDefault();
        const rawData = event.dataTransfer.getData('application/agent-template');
        if (!rawData || !rfInstance) return;

        try {
            const templateData = JSON.parse(rawData);
            const position = screenToFlowPosition({ x: event.clientX, y: event.clientY });

            // Search for nodes under the release location and attempt to merge them
            const allNodes = rfInstance.getNodes();
            const targetNode = allNodes.find(node => {
                if (node.type !== 'agentNode') return false;
                const { x, y } = node.position;
                const width = node.measured?.width || node.width || 200;
                const height = node.measured?.height || node.height || 110;
                return (
                    position.x >= x &&
                    position.x <= x + width &&
                    position.y >= y &&
                    position.y <= y + height
                );
            });

            if (targetNode) {
                // Merge into existing steps
                setEditNodes((nds) => nds.map(n => {
                    if (n.id === targetNode.id) {
                        const currentSubtasks = n.data.subtasks || [];
                        const newSubtasks = [
                            ...currentSubtasks,
                            {
                                agent: templateData.agent,
                                skill: templateData.skill,
                                skillsList: templateData.skillsList || [],
                                description: templateData.description,
                                status: 'pending'
                            }
                        ];
                        return {
                            ...n,
                            data: {
                                ...n.data,
                                subtasks: newSubtasks
                            },
                            height: 100 + newSubtasks.length * 60
                        };
                    }
                    return n;
                }));
            } else {
                // Create a new step
                const usedStepIds = new Set(editNodes.map(n => n.id));
                let nextIndex = 1;
                while (usedStepIds.has(`step${nextIndex}`)) {
                    nextIndex += 1;
                }
                const newId = `step${nextIndex}`;
                const newSubtask = {
                    agent: templateData.agent,
                    skill: templateData.skill,
                    skillsList: templateData.skillsList || [],
                    description: templateData.description,
                    status: 'pending'
                };
                const newNode = {
                    id: newId,
                    type: 'agentNode',
                    position,
                    data: {
                        ...templateData,
                        label: newId,
                        subtasks: [newSubtask],
                        status: 'pending',
                        name: newId,
                        isDark,
                    },
                    width: 200,
                    height: 100 + 1 * 60
                };
                setEditNodes((nds) => nds.concat(newNode));
                setIsDirty(true);
            }
        } catch (error) {
            console.error(t('error.parse_failed'), error);
        }
    }, [editNodes, screenToFlowPosition, setEditNodes, isDark, t, rfInstance]);

    const displayNodes = mode === 'view' ? viewPositionNodes : editNodes;
    const displayEdges = mode === 'view' ? viewPositionEdges : editEdges;

    return (
        <div className={`h-full w-full relative overflow-hidden select-none transition-colors duration-300 ${themeClasses.container}`}>
            <ReactFlow
                nodes={displayNodes}
                edges={displayEdges}
                nodeTypes={nodeTypes}
                edgeTypes={edgeTypes}
                onNodesChange={mode === 'edit' ? onNodesChangeWithDirty : undefined}
                onEdgesChange={mode === 'edit' ? onEdgesChangeWithDirty : undefined}
                onConnect={mode === 'edit' ? onConnect : undefined}
                onNodeDragStop={(e, n) => { onNodeDragStop(e, n); setIsDirty(true); }}
                onDrop={mode === 'edit' ? onDrop : undefined}
                onDragOver={mode === 'edit' ? (e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; } : undefined}
                onSelectionChange={mode === 'edit' ? (({ nodes, edges }) => setSelectedElement(nodes[0] || edges[0] || null)) : undefined}
                onNodeClick={(e, n) => {
                    if (mode === 'view') {
                        e.stopPropagation();
                        selectViewNode(n);
                    }
                }}
                onPaneClick={() => {
                    if (mode === 'view') {
                        setViewSelectedNodeId(null);
                        setViewSelectedElement(null);
                        if (onSelectChange) onSelectChange(null);
                    }
                }}
                nodesConnectable={mode === 'edit'}
                nodesDraggable={mode === 'edit'}
                elementsSelectable={mode === 'edit'}
                onInit={setRfInstance}
                colorMode={isDark ? 'dark' : 'light'}
                fitView
                fitViewOptions={{ padding: 0.1 }}
                proOptions={{ hideAttribution: true }}
                connectionRadius={50}

                defaultEdgeOptions={{
                    type: 'custom',
                    animated: true,
                    style: { strokeWidth: 3 },
                }}
            >
                <Background color={themeClasses.gridColor} gap={20} variant="dots" />
                <Controls showInteractive={mode === 'edit'} position="bottom-left" />
            </ReactFlow>

            {mode === 'view' && (
                <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-5 pointer-events-none">
                    <div className="pointer-events-auto">
                        <ToolbarLite isDark={isDark} onFitView={() => fitView({ padding: 0.2, duration: 800 })} />
                    </div>
                </div>
            )}

            {mode === 'view' && (
                <div className={`absolute justify-center right-4 top-4 bottom-4 w-80 z-40 pointer-events-none flex flex-col min-h-0 transition-all duration-300 transform ${viewSelectedElement ? 'translate-x-0 opacity-100' : 'translate-x-10 opacity-0'}`}>
                    <div className={`pointer-events-auto flex flex-col backdrop-blur-md border rounded-2xl overflow-hidden ${themeClasses.panel}`}>
                        {viewSelectedElement && (
                            <WorkflowViewDetails
                                isDark={isDark}
                                selected={{
                                    ...viewSelectedElement,
                                    onSelectSubtask: (subtaskIndex) => selectViewNode(viewSelectedElement.node, subtaskIndex),
                                }}
                                onClose={() => {
                                    setViewSelectedElement(null);
                                    setViewSelectedNodeId(null);
                                    if (onSelectChange) onSelectChange(null);
                                }}
                            />
                        )}
                    </div>
                </div>
            )}

            {mode === 'edit' && (
                <>
                    <div className="absolute top-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none">
                        <div className="pointer-events-auto">
                            <Toolbar isDark={isDark} nodes={editNodes} edges={editEdges} workflowId={workflowId} workflowName={workflowName} workflowDescription={workflowDescription} onCancel={handleCancel} onClear={() => { setEditNodes(initialEditNodes); setEditEdges([]); setIsDirty(true); }} onFitView={() => fitView({ padding: 0.4, duration: 800 })} onSaveSuccess={handleSaveSuccess} />
                        </div>
                    </div>
                    <div className="absolute inset-x-4 bottom-8 h-auto z-40 pointer-events-none flex justify-center min-h-0">
                        <div className={`pointer-events-auto flex items-center backdrop-blur-md border rounded-[2rem] overflow-hidden transition-all shadow-2xl max-w-full ${themeClasses.panel}`}>
                            <Sidebar isDark={isDark} />
                        </div>
                    </div>
                    <div className={`absolute justify-center right-4 top-4 bottom-4 w-80 z-40 pointer-events-none flex flex-col min-h-0 transition-all duration-300 transform ${selectedElement ? 'translate-x-0 opacity-100' : 'translate-x-10 opacity-0'}`}>
                        <div className={`pointer-events-auto flex flex-col backdrop-blur-md border rounded-2xl overflow-hidden ${themeClasses.panel}`}>
                            {selectedElement && (
                                <PropertyPanel isDark={isDark} selectedElement={selectedElement} nodes={editNodes} edges={editEdges} setNodes={(nds) => { setEditNodes(nds); setIsDirty(true); }} setEdges={(eds) => { setEditEdges(eds); setIsDirty(true); }} onDelete={onDeleteSelected} setPhenomenon={setPhenomenon} onClose={() => setSelectedElement(null)} />
                            )}
                        </div>
                    </div>
                    {showExitConfirm && (
                        <div className={`fixed inset-0 z-[10000] flex items-center justify-center p-4 bg-slate-900/40 dark:bg-zinc-950/60 backdrop-blur-md`}>
                            <div className={`relative w-full max-w-sm p-6 rounded-[2rem] border shadow-2xl ${isDark ? 'bg-zinc-900 border-zinc-700/50 text-zinc-100' : 'bg-white border-slate-200 text-slate-900'}`}>
                                <h3 className="text-lg font-black mb-3">{t('workflow.exit.title')}</h3>
                                <p className={`text-sm mb-6 ${isDark ? 'text-zinc-400' : 'text-slate-500'}`}>{t('workflow.exit.desc')}</p>
                                <div className="flex gap-4">
                                    <button onClick={() => setShowExitConfirm(false)} className={`flex-1 py-3 text-sm font-bold rounded-2xl transition-all ${isDark ? 'hover:bg-zinc-800 text-zinc-400' : 'hover:bg-slate-100 text-slate-500'}`}>{t('common.cancel')}</button>
                                    <button onClick={onCancel} className={`flex-1 py-3 text-sm font-black rounded-2xl transition-all shadow-lg ${isDark ? 'bg-zinc-100 text-zinc-950 hover:bg-white' : 'bg-slate-900 text-white hover:bg-slate-800'}`}>{t('common.confirm')}</button>
                                </div>
                            </div>
                        </div>
                    )}
                </>
            )}
        </div>
    );
};
const UnifiedWorkflow = ({
    mode = 'view',
    isDark = false,
    nodes = [],
    edges = [],
    isLoading = false,
    loadingMessage,
    onSelectChange,
    visible = true,
    importedNodes,
    importedEdges,
    workflowId,
    workflowName,
    workflowDescription,
    onCancel,
    onSaveSuccess
}) => {
    const { t } = useTranslation();

    if (mode === 'view' && isLoading) {
        return <WorkflowLoader isDark={isDark} loadingMessage={loadingMessage} />;
    }

    if (mode === 'view' && !isLoading && nodes.length === 0) {
        return (
            <div className="w-full h-full min-h-[300px] flex flex-col items-center justify-center p-8 bg-zinc-50/50 dark:bg-zinc-800/20 rounded-[2rem] border-2 border-dashed border-zinc-200 dark:border-zinc-700/50 transition-all duration-300">
                <div className="w-20 h-20 mb-6 rounded-3xl bg-white dark:bg-zinc-800/80 shadow-md flex items-center justify-center border border-zinc-100 dark:border-zinc-700/50">
                    <Layers className="w-10 h-10 text-zinc-300 dark:text-zinc-600" strokeWidth={1.5} />
                </div>
                <h3 className="text-lg font-black text-zinc-600 dark:text-zinc-300 mb-2 tracking-tight">{t('workflow_empty.title')}</h3>
                <p className="text-sm text-zinc-400 dark:text-zinc-500 max-w-sm text-center leading-relaxed">
                    {t('workflow_empty.desc')}
                </p>
            </div>
        );
    }

    const baseBg = isDark ? "bg-[#0f172a]" : "bg-[#f8fafc]";
    const editWrapperClass = visible
        ? `absolute inset-0 z-[50] translate-y-0 opacity-100 transition-all duration-300 ${baseBg}`
        : `absolute inset-0 z-[-1] translate-y-4 opacity-0 pointer-events-none transition-all duration-300 ${baseBg}`;

    return (
        <div className={mode === 'edit' ? editWrapperClass : "w-full h-full min-h-[300px]"}>
            <ReactFlowProvider>
                <FlowInner
                    mode={mode}
                    isDark={isDark}
                    viewNodes={nodes}
                    viewEdges={edges}
                    onSelectChange={onSelectChange}
                    importedNodes={importedNodes}
                    importedEdges={importedEdges}
                    workflowId={workflowId}
                    workflowName={workflowName}
                    workflowDescription={workflowDescription}
                    onCancel={onCancel}
                    onSaveSuccess={onSaveSuccess}
                />
            </ReactFlowProvider>
        </div>
    );
};

export default UnifiedWorkflow;
