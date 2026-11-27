// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

// 泳道图视图 (竖向·精致版): 每个智能体一条纵向泳道, 子任务按执行顺序向下流动,
// 跨泳道流转为圆角虚线折线; 任务卡带状态徽章与步号圆徽; 顶部状态图例。
import React from 'react';

const LANE_HEAD_H = 76;  // 泳道标题高度 (容纳3行全名)
const CARD_W = 200;      // 任务卡宽
const CARD_H = 64;       // 任务卡高
const COL_GAP = 28;      // 泳道列间距
const ROW_GAP = 30;      // 行间距
const LEFT_PAD = 18;
const TOP_PAD = 12;

const statusKey = (status) => {
    const s = String(status || '').toLowerCase().trim();
    if (['running', 'current', 'executing', 'active'].includes(s)) return 'running';
    if (['success', 'completed', 'executed', 'finished'].includes(s)) return 'success';
    if (['failed', 'error', 'stopped'].includes(s)) return 'failed';
    return 'pending';
};

const STATUS_STYLE = {
    running: { dot: 'bg-blue-500', bar: 'bg-blue-500', pill: 'bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30', stroke: '#3b82f6' },
    success: { dot: 'bg-emerald-500', bar: 'bg-emerald-500', pill: 'bg-emerald-50 text-emerald-600 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30', stroke: '#10b981' },
    failed: { dot: 'bg-rose-500', bar: 'bg-rose-500', pill: 'bg-rose-50 text-rose-600 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30', stroke: '#f43f5e' },
    pending: { dot: 'bg-zinc-400', bar: 'bg-zinc-400', pill: 'bg-zinc-50 text-zinc-500 border-zinc-200 dark:bg-zinc-500/15 dark:text-zinc-300 dark:border-zinc-500/30', stroke: '#a1a1aa' },
};

const LANE_SOLID = ['bg-blue-600', 'bg-purple-600', 'bg-teal-600', 'bg-orange-600', 'bg-pink-600', 'bg-indigo-600'];
const LANE_TINT = ['bg-blue-50/60 dark:bg-blue-500/[0.06]', 'bg-purple-50/60 dark:bg-purple-500/[0.06]', 'bg-teal-50/60 dark:bg-teal-500/[0.06]', 'bg-orange-50/60 dark:bg-orange-500/[0.06]', 'bg-pink-50/60 dark:bg-pink-500/[0.06]', 'bg-indigo-50/60 dark:bg-indigo-500/[0.06]'];
const LANE_RING = ['ring-blue-500/20', 'ring-purple-500/20', 'ring-teal-500/20', 'ring-orange-500/20', 'ring-pink-500/20', 'ring-indigo-500/20'];

const agentHash = (name) => {
    let h = 0;
    for (let i = 0; i < (name || '').length; i++) h = name.charCodeAt(i) + ((h << 5) - h);
    return Math.abs(h);
};

const WorkflowSwimlane = ({ viewNodes, isDark, t, onSubtaskClick }) => {
    const tasks = [];
    (viewNodes || []).forEach((node) => {
        const subs = node.data?.subtasks || [];
        subs.forEach((st, idx) => {
            tasks.push({
                nodeId: node.id,
                nodeLabel: node.data?.label || node.id,
                subtaskIndex: idx,
                agent: st.agent || t('workflow.panel.agentName'),
                skill: st.skill || '',
                status: st.status || node.data?.status || '',
            });
        });
    });

    const lanes = [];
    tasks.forEach((tk) => {
        if (!lanes.includes(tk.agent)) lanes.push(tk.agent);
    });
    const laneIndex = (a) => lanes.indexOf(a);
    const laneCount = (a) => tasks.filter((tk) => tk.agent === a).length;

    const laneW = CARD_W + COL_GAP;
    const laneX = (i) => LEFT_PAD + i * laneW;
    const cardX = (lane) => laneX(lane) + COL_GAP / 2;
    const cardY = (seq) => LANE_HEAD_H + TOP_PAD + seq * (CARD_H + ROW_GAP);
    const gridW = LEFT_PAD + lanes.length * laneW + 40;
    const gridH = LANE_HEAD_H + TOP_PAD + tasks.length * (CARD_H + ROW_GAP) + 48;

    // 连线: 圆角折线 (底部中点 → 垂直 → 圆角 → 水平 → 圆角 → 垂直入目标顶部)
    const r = 10;
    const connectors = [];
    for (let i = 0; i < tasks.length - 1; i++) {
        const a = tasks[i];
        const b = tasks[i + 1];
        const x1 = cardX(laneIndex(a.agent)) + CARD_W / 2;
        const y1 = cardY(i) + CARD_H;
        const x2 = cardX(laneIndex(b.agent)) + CARD_W / 2;
        const y2 = cardY(i + 1);
        const midY = y1 + (y2 - y1) / 2;
        const sameLane = a.agent === b.agent;
        let d;
        if (sameLane) {
            d = `M ${x1} ${y1} L ${x1} ${y2 - 7}`;
        } else {
            const dir = x2 > x1 ? 1 : -1;
            d = `M ${x1} ${y1} L ${x1} ${midY - r} Q ${x1} ${midY} ${x1 + dir * r} ${midY} L ${x2 - dir * r} ${midY} Q ${x2} ${midY} ${x2} ${midY + r} L ${x2} ${y2 - 7}`;
        }
        connectors.push({ d, key: `${a.nodeId}-${a.subtaskIndex}`, cross: !sameLane, x: x2, yTip: y2 - 7, stroke: sameLane ? STATUS_STYLE[statusKey(b.status)].stroke : (isDark ? '#818cf8' : '#6366f1') });
    }

    const panelBorder = isDark ? 'border-zinc-800' : 'border-slate-200';
    const legend = ['pending', 'running', 'success', 'failed'];

    if (tasks.length === 0) {
        return (
            <div className={`h-full w-full flex items-center justify-center ${isDark ? 'text-zinc-500' : 'text-slate-400'}`}>
                <span className="text-sm">{t('workflow.panel.subtasks')}</span>
            </div>
        );
    }

    return (
        <div className={`h-full w-full overflow-auto custom-scrollbar border-t ${panelBorder} ${isDark ? 'bg-zinc-950' : 'bg-gradient-to-b from-slate-50 to-white'}`}
            style={isDark ? {} : { backgroundImage: 'radial-gradient(#cbd5e1 1px, transparent 1px)', backgroundSize: '22px 22px' }}>
            {/* 状态图例 (右上角) */}
            <div className="sticky top-0 z-20 flex justify-end pr-6 pt-3 pointer-events-none">
                <div className={`flex items-center gap-3 px-3 py-1.5 rounded-full border shadow-sm backdrop-blur-md ${isDark ? 'bg-zinc-900/80 border-zinc-700' : 'bg-white/90 border-slate-200'}`}>
                    {legend.map((k) => (
                        <span key={k} className="flex items-center gap-1.5 text-[10px] font-bold">
                            <span className={`w-2 h-2 rounded-full ${STATUS_STYLE[k].dot}`} />
                            <span className={isDark ? 'text-zinc-300' : 'text-slate-600'}>{t(`workflow.panel.status_${k}`)}</span>
                        </span>
                    ))}
                </div>
            </div>
            <div className="relative -mt-8" style={{ width: gridW, height: gridH, minWidth: '100%' }}>
                {/* 纵向泳道带 */}
                {lanes.map((agent, i) => {
                    const ci = i % LANE_SOLID.length;
                    return (
                        <div key={agent} className={`absolute top-0 bottom-0 ${LANE_TINT[ci]}`}
                            style={{ left: laneX(i) + 4, width: laneW - 8 }}>
                            <div className="absolute inset-x-1 bottom-2 top-2 rounded-xl border border-dashed opacity-60"
                                style={{ borderColor: isDark ? '#3f3f4666' : '#cbd5e166' }} />
                        </div>
                    );
                })}
                {/* 泳道标题 (列头) */}
                {lanes.map((agent, i) => {
                    const ci = i % LANE_SOLID.length;
                    return (
                        <div key={agent} className={`absolute top-3 left-2 right-2 rounded-xl shadow-md ring-1 ${LANE_SOLID[ci]} ${LANE_RING[ci]} px-2.5 py-2 flex flex-col items-center gap-1`}
                            style={{ left: laneX(i) + COL_GAP / 2, width: CARD_W, height: LANE_HEAD_H - 12, top: 12 }}
                            title={agent}>
                            <span className="w-2 h-2 rounded-full shrink-0 bg-white/90" />
                            <span className="text-[11px] font-bold leading-tight text-center line-clamp-3 text-white" title={agent}>{agent}</span>
                        </div>
                    );
                })}
                {/* 连线层 */}
                <svg className="absolute inset-0 pointer-events-none" width={gridW} height={gridH}>
                    {connectors.map((cn) => (
                        <g key={cn.key}>
                            <path d={cn.d} fill="none"
                                strokeWidth={cn.cross ? 2.5 : 2}
                                stroke={cn.stroke}
                                strokeDasharray={cn.cross ? '6 4' : undefined}
                                strokeLinecap="round" />
                            <path d={`M ${cn.x} ${cn.yTip} l -4 -8 l 8 0 z`} fill={cn.stroke} />
                        </g>
                    ))}
                </svg>
                {/* 任务卡 */}
                {tasks.map((tk, i) => {
                    const sk = STATUS_STYLE[statusKey(tk.status)];
                    const lane = laneIndex(tk.agent);
                    const ci = lane % LANE_SOLID.length;
                    return (
                        <button
                            key={`${tk.nodeId}-${tk.subtaskIndex}`}
                            onClick={() => onSubtaskClick && onSubtaskClick(tk.nodeId, tk.subtaskIndex)}
                            className={`absolute rounded-xl bg-white dark:bg-zinc-900/90 border border-slate-200/90 dark:border-zinc-700/80 shadow-sm hover:shadow-xl hover:-translate-y-0.5 transition-all cursor-pointer overflow-visible ${isDark ? 'hover:border-blue-500/60' : 'hover:border-blue-400/70'}`}
                            style={{ left: cardX(lane), top: cardY(i), width: CARD_W, height: CARD_H }}
                            title={tk.skill}
                        >
                            <span className={`absolute left-0 top-2 bottom-2 w-1 rounded-full ${sk.bar}`} />
                            <span className={`absolute top-2 right-2 inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full border text-[9px] font-bold ${sk.pill}`}>
                                <span className={`w-1.5 h-1.5 rounded-full ${sk.dot}`} />
                                {t(`workflow.panel.status_${statusKey(tk.status)}`)}
                            </span>
                            <span className="block pl-3.5 pr-2 pt-2 text-left">
                                <span className={`block text-[11px] font-bold truncate pr-14 ${isDark ? 'text-zinc-100' : 'text-slate-800'}`}>{tk.skill || '-'}</span>
                                <span className={`block mt-1 text-[9px] font-medium truncate ${isDark ? 'text-zinc-500' : 'text-slate-400'}`}>{tk.nodeLabel}</span>
                            </span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
};

export default WorkflowSwimlane;
