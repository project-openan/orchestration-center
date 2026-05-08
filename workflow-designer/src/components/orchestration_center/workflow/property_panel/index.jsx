import React, { useCallback, useEffect, useMemo } from 'react';
import KvIndex from "@/components/orchestration_center/workflow/kv_editor/index.jsx";
import { useTranslation } from "react-i18next";
import DeleteConfirm from "@/components/common/pop_confirm/index.jsx";
import { getAgentCards } from "@/service/api.js";

const PropertyPanel = ({ selectedElement, nodes, edges, setPhenomenon, setNodes, setEdges, isDark, onDelete, onClose }) => {
    const { t } = useTranslation();
    const [allAgents, setAllAgents] = React.useState([]);

    useEffect(() => {
        const fetchAgents = async () => {
            try {
                const res = await getAgentCards();
                setAllAgents(res.data || []);
            } catch (err) {
                console.error("Failed to fetch agent cards in property panel:", err);
            }
        };
        fetchAgents();
    }, []);
    const theme = {
        container: isDark ? 'bg-zinc-950 text-zinc-300' : 'bg-white text-zinc-800',
        emptyBg: isDark ? 'bg-zinc-950' : 'bg-zinc-50/50',
        header: isDark ? 'bg-zinc-900/50 border-zinc-800' : 'bg-zinc-50/30 border-zinc-200/50',
        label: isDark ? 'text-zinc-500' : 'text-zinc-500',
        inputArea: isDark ? 'bg-zinc-900 border-zinc-800 focus:border-zinc-500 text-zinc-200' : 'bg-zinc-50 border-zinc-200 focus:border-zinc-400',
        footer: isDark ? 'bg-zinc-900/50 border-zinc-800' : 'bg-zinc-50/50 border-zinc-100',
        confirmBtn: isDark ? 'bg-zinc-100 text-zinc-950 hover:bg-white' : 'bg-zinc-800 text-white hover:bg-zinc-900'
    };
    const activeElement = useMemo(() => {
        if (!selectedElement) return null;
        if (selectedElement.source) {
            return edges.find(e => e.id === selectedElement.id);
        } else {
            return nodes.find(n => n.id === selectedElement.id);
        }
    }, [selectedElement, nodes, edges]);
    const updateData = useCallback((key, value, extraProps = {}) => {
        if (!selectedElement) return;

        const isNode = !('source' in selectedElement);

        if (isNode) {
            setNodes((nds) =>
                nds.map((node) => {
                    if (node.id === selectedElement.id) {
                        return { ...node, ...extraProps, data: { ...node.data, [key]: value } };
                    }
                    return node;
                })
            );
        } else {
            setEdges((eds) =>
                eds.map((edge) => {
                    if (edge.id === selectedElement.id) {
                        const updated = { ...edge, ...extraProps, data: { ...edge.data, [key]: value } };
                        if (key === 'condition') {
                            updated.label = value;
                        }
                        return updated;
                    }
                    return edge;
                })
            );
        }
    }, [selectedElement, setNodes, setEdges]);

    useEffect(() => {
        const d = activeElement?.data || {};
        if (d.skill && (!d.inputs || Object.keys(d.inputs).length === 0)) {
            const currentSkill = d.skillsList?.find(s => s.name === d.skill);
            if (currentSkill && currentSkill.inputs) {
                const parsedInputs = {};
                currentSkill.inputs.split('\n').forEach(line => {
                    const [key, ...descParts] = line.split(':');
                    if (key) {
                        parsedInputs[key.trim()] = descParts.join(':').trim();
                    }
                });

                updateData('inputs', parsedInputs);
                console.log("初始化：已自动解析并同步 inputDefine");
            }
        }
    }, [activeElement?.data?.skill, activeElement?.data?.skillsList, updateData]);

    useEffect(() => {
        const d = activeElement?.data || {};
        if (d.skill && (!d.outputs || Object.keys(d.outputs).length === 0)) {
            const currentSkill = d.skillsList?.find(s => s.name === d.skill);
            if (currentSkill && currentSkill.outputs) {
                const parsedInputs = {};
                currentSkill.outputs.split('\n').forEach(line => {
                    const [key, ...descParts] = line.split(':');
                    if (key) {
                        parsedInputs[key.trim()] = descParts.join(':').trim();
                    }
                });

                updateData('outputs', parsedInputs);
                console.log("初始化：已自动解析并同步 outputDefine");
            }
        }
    }, [activeElement?.data?.skill, activeElement?.data?.skillsList, updateData]);

    const handleRemoveSubtask = (idx) => {
        const d = activeElement?.data || {};
        if (!d.subtasks) return;
        const newSubtasks = d.subtasks.filter((_, i) => i !== idx);
        const newHeight = 80 + Math.max(newSubtasks.length, 1) * 55;
        updateData('subtasks', newSubtasks, { height: newHeight });
    };

    const handleDelete = () => {
        onDelete();
    }

    const handleSubtaskSkillChange = (idx, selectedName) => {
        const d = activeElement?.data || {};
        if (!d.subtasks) return;
        const newSubtasks = [...d.subtasks];
        const task = newSubtasks[idx];
        const agentInfo = allAgents.find(a => (a.name || a.id) === task.agent);
        const availableSkills = task.skillsList || agentInfo?.skills || d.skillsList || [];
        const selectedSkill = availableSkills.find(s => s.name === selectedName);

        if (selectedSkill) {
            const parsedInputs = {};
            if (selectedSkill.inputs) {
                selectedSkill.inputs.split('\n').forEach(line => {
                    const [key, ...descParts] = line.split(':');
                    if (key) {
                        parsedInputs[key.trim()] = descParts.join(':').trim();
                    }
                });
            }

            const parsedOutputs = {};
            if (selectedSkill.outputs) {
                selectedSkill.outputs.split('\n').forEach(line => {
                    const [key, ...descParts] = line.split(':');
                    if (key) {
                        parsedOutputs[key.trim()] = descParts.join(':').trim();
                    }
                });
            }

            newSubtasks[idx] = {
                ...task,
                skill: selectedName,
                description: selectedSkill.description || task.description
            };

            if (newSubtasks.length === 1) {
                updateData('skill', selectedName);
                updateData('inputs', parsedInputs);
                updateData('outputs', parsedOutputs);
                updateData('description', selectedSkill.description || task.description);
            }

            updateData('subtasks', newSubtasks);
        }
    };

    if (!activeElement) {
        return (
            <div className={`w-80 h-full flex flex-col items-center justify-center p-8 text-center transition-colors ${theme.emptyBg}`}>
                <div className={`w-12 h-12 rounded-full mb-4 flex items-center justify-center ${isDark ? 'bg-zinc-900 text-zinc-700' : 'bg-zinc-200 text-zinc-400'}`}>
                    <svg fill="none" viewBox="0 0 24 24" stroke="currentColor" className="w-6 h-6"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5" /></svg>
                </div>
                <p className={`text-sm font-medium ${isDark ? 'text-zinc-500' : 'text-zinc-500'}`}>{t('workflow.panel.empty')}</p>
            </div>
        );
    }
    const renderValue = (val) => {
        if (typeof val === 'object' && val !== null) {
            return (
                <pre className="p-2 bg-zinc-100 dark:bg-zinc-800 rounded text-xs overflow-auto max-h-40">
                    {JSON.stringify(val, null, 2)}
                </pre>
            );
        }
        return <span className="font-medium">{String(val)}</span>;
    };
    const isNode = !('source' in activeElement);
    const data = activeElement.data || {};
    const renderSafeValue = (val) => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'object') {
            return <span className="text-[11px] opacity-70 break-all">{JSON.stringify(val)}</span>;
        }
        return val;
    };
    return (
        <div className={`flex flex-col h-full w-full transition-colors ${theme.container}`}>
            <div className={`flex flex-row items-center justify-between p-4 border-b transition-colors ${theme.header}`}>
                <h3 className="text-sm font-bold flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full shadow-[0_0_8px_rgba(255,255,255,0.2)] ${isNode ? 'bg-zinc-400' : 'bg-zinc-500'}`} />
                    {isNode ? t('workflow.panel.nodeConfig') : t('workflow.panel.edgeConfig')}
                </h3>
                <p className="text-[12px] text-zinc-500 font-mono tracking-wider uppercase truncate">
                    ID: {activeElement.id}
                </p>
                <DeleteConfirm
                    title={t('common.confirm_delete')}
                    onConfirm={onDelete}
                    isDark={isDark}
                >
                    <button className="px-3 py-1 text-sm bg-red-500/10 hover:bg-red-500 text-red-500 border border-red-500/20 rounded-lg transition-all">
                        {t('common.delete')}
                    </button>
                </DeleteConfirm>
            </div>

            <div className="p-4 space-y-6 flex-1 overflow-y-auto custom-scrollbar">
                {isNode ? (
                    <>

                        <ReadOnlyField label={t('workflow.panel.stepName')} value={data.label} isDark={isDark} />

                        {data.subtasks && data.subtasks.length > 0 ? (
                            <div className="space-y-3">
                                <label className={`text-[12px] ml-1 font-bold uppercase tracking-widest ${theme.label}`}>
                                    {t('workflow.panel.subtasks')} ({data.subtasks.length})
                                </label>
                                <div className="flex flex-col gap-2.5">
                                    {data.subtasks.map((task, idx) => (
                                        <div key={idx} className={`group/task relative p-3 rounded-xl border transition-all ${isDark ? 'bg-zinc-900 border-zinc-800/50' : 'bg-zinc-50 border-zinc-200/50 shadow-sm'}`}>
                                            <div className="flex justify-between items-center mb-1.5">
                                                <span className="text-[10px] font-bold text-blue-500 uppercase tracking-tight">{task.agent}</span>
                                                <div className="flex items-center gap-2">
                                                    <div className="flex items-center gap-1.5">
                                                        <div className={`w-1.5 h-1.5 rounded-full ${(task.status === 'success' || task.status === 'completed') ? 'bg-emerald-500' :
                                                                (task.status === 'running' || task.status === 'current') ? 'bg-blue-500' :
                                                                    (task.status === 'failed' || task.status === 'error') ? 'bg-rose-500' :
                                                                        'bg-zinc-400'
                                                            }`} />
                                                        <span className="text-[10px] opacity-60 uppercase font-medium">{task.status}</span>
                                                    </div>
                                                    <button
                                                        onClick={() => handleRemoveSubtask(idx)}
                                                        className="p-1 hover:bg-red-500/10 rounded-md text-red-500 opacity-0 group-hover/task:opacity-100 transition-opacity"
                                                        title={t('workflow.panel.removeSubtask')}
                                                    >
                                                        <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                                                    </button>
                                                </div>
                                            </div>
                                            <div className="relative mt-1">
                                                <select
                                                    value={task.skill}
                                                    onChange={(e) => handleSubtaskSkillChange(idx, e.target.value)}
                                                    className={`
                                                        w-full px-2 py-1.5 text-[12px] font-bold rounded-lg border appearance-none outline-none transition-all
                                                        ${isDark ? 'bg-zinc-800 border-zinc-700 text-zinc-200 focus:border-blue-500' : 'bg-white border-zinc-200 text-slate-800 focus:border-blue-400'}
                                                    `}
                                                    style={{ paddingRight: '24px' }}
                                                >
                                                    {(() => {
                                                        const agentInfo = allAgents.find(a => (a.name || a.id) === task.agent);
                                                        const availableSkills = task.skillsList || agentInfo?.skills || data.skillsList || [];
                                                        return (
                                                            <>
                                                                {availableSkills.map(s => (
                                                                    <option key={s.name} value={s.name}>{s.name}</option>
                                                                ))}
                                                                {!availableSkills.some(s => s.name === task.skill) && (
                                                                    <option value={task.skill}>{task.skill}</option>
                                                                )}
                                                            </>
                                                        );
                                                    })()}
                                                </select>
                                                <div className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none opacity-50">
                                                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                                                </div>
                                            </div>
                                            {task.description && (
                                                <p className={`text-[12px] mt-1.5 leading-relaxed opacity-70 ${isDark ? 'text-zinc-400' : 'text-slate-600'}`}>
                                                    {task.description}
                                                </p>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ) : (
                            <>
                                <ReadOnlyField label={t('workflow.panel.agentName')} value={data.agent} isDark={isDark} />
                                <ReadOnlyField label={t('workflow.panel.executeSkill')} value={data.skill} isDark={isDark} />
                            </>
                        )}
                    </>
                ) : (
                    <section className="space-y-4">
                        <div className={`flex flex-col gap-2 p-3 rounded-xl border ${isDark ? 'bg-zinc-900/50 border-zinc-800' : 'bg-zinc-50 border-zinc-100'}`}>
                            <div className="flex justify-between text-[12px] tracking-tight">
                                <span className="text-zinc-500 font-bold uppercase">{t('workflow.panel.source')}</span>
                                <span className={isDark ? 'text-zinc-300' : 'text-zinc-700'}>{activeElement.source}</span>
                            </div>
                            <div className="flex justify-between text-[12px] tracking-tight">
                                <span className="text-zinc-500 font-bold uppercase">{t('workflow.panel.target')}</span>
                                <span className={isDark ? 'text-zinc-300' : 'text-zinc-700'}>{activeElement.target}</span>
                            </div>
                        </div>
                        <Field
                            label={t('workflow.panel.condition')}
                            value={data.condition}
                            onChange={(v) => updateData('condition', v)}
                            placeholder={t('workflow.panel.conditionPlaceholder')}
                            isDark={isDark}
                            fontMono
                        />
                    </section>
                )}
            </div>

            <div className={`p-4 border-t sticky bottom-0 transition-colors ${theme.footer}`}>
                <button
                    className={`w-full py-2.5 text-xs font-bold rounded-xl transition-all active:scale-95 shadow-lg ${theme.confirmBtn}`}
                    onClick={() => {
                        console.log('Confirmed Config:', data);
                        if (onClose) onClose();
                    }}
                >
                    {t('workflow.panel.confirm')}
                </button>
            </div>
        </div>
    );
};


const ReadOnlyField = ({ label, value, isDark }) => (
    <div className={`flex justify-between items-center py-3 border-b transition-colors ${isDark ? 'border-zinc-800/50' : 'border-zinc-100'}`}>
        <span className={`text-[14px] ${isDark ? 'text-zinc-200' : 'text-zinc-500'}`}>{label}</span>
        <span className={`text-[14px] font-semibold ${isDark ? 'text-zinc-200' : 'text-zinc-900'}`}>{value || '-'}</span>
    </div>
);

const Field = ({ label, value, onChange, placeholder, isTextArea, fontMono, isDark }) => {
    const baseClass = `w-full px-3 py-2 rounded-lg text-sm transition-all outline-none border shadow-sm placeholder:text-zinc-600 ${isDark
            ? 'bg-zinc-900 border-zinc-800 focus:border-zinc-500 text-zinc-100'
            : 'bg-zinc-50 border-zinc-200 focus:border-zinc-400 text-zinc-800'
        } ${fontMono ? 'font-mono text-[14px]' : ''}`;

    return (
        <div className="space-y-1.5">
            <label className={`text-[14px] ml-1 font-bold uppercase tracking-wide ${isDark ? 'text-zinc-500' : 'text-zinc-500'}`}>
                {label}
            </label>
            {isTextArea ? (
                <textarea rows={3} className={`${baseClass} resize-none`} value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
            ) : (
                <input className={baseClass} value={value || ''} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
            )}
        </div>
    );
};

export default PropertyPanel;
