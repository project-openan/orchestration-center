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
import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, LineChart, Line, Legend
} from 'recharts';
import { Calendar, TrendingUp, Award, Activity } from 'lucide-react';
import { getExecutionRecords } from '@/service/api.js';

// Status bars are drawn in the order success / failed / running, so the palette
// leads with the semantic colours (emerald success, rose error, brand blue for
// running) and continues down the China Mobile brand ramp. Recharts needs real
// colour values here, so these are the token values from tailwind.config.js.
const COLORS = ['#10B981', '#F43F5E', '#2464E8', '#6E9DF4', '#357BF1', '#1B4FD1', '#A9C8FB', '#2F60B6'];

const ExecutionStatistics = ({ isDark }) => {
    const { t } = useTranslation();
    const [records, setRecords] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedWorkflow, setSelectedWorkflow] = useState(null);

    useEffect(() => {
        const fetchRecords = async () => {
            try {
                setLoading(true);
                const res = await getExecutionRecords();
                if (res.status === 'success') {
                    setRecords(res.data || []);
                }
            } catch (err) {
                console.error("Failed to load execution records:", err);
            } finally {
                setLoading(false);
            }
        };
        fetchRecords();
    }, []);

    const frequencyRanking = useMemo(() => {
        const counts = {};
        records.forEach(r => {
            const name = r.psop_name || r.psop_id || 'Unknown';
            counts[name] = (counts[name] || 0) + 1;
        });

        return Object.entries(counts)
            .map(([name, count]) => ({ name, count }))
            .sort((a, b) => b.count - a.count)
            .slice(0, 10);
    }, [records]);

    const statusDistribution = useMemo(() => {
        const counts = { success: 0, failed: 0, running: 0 };
        records.forEach(r => {
            const status = r.status || 'success';
            if (status in counts) {
                counts[status]++;
            } else {
                counts.success++;
            }
        });

        const total = Object.values(counts).reduce((a, b) => a + b, 0);
        return Object.entries(counts).map(([status, count]) => ({
            name: t(`execution.status_${status}`),
            value: count,
            percentage: total > 0 ? ((count / total) * 100).toFixed(1) : 0
        }));
    }, [records, t]);

    const workflowList = useMemo(() => {
        const names = new Set();
        records.forEach(r => {
            names.add(r.psop_name || r.psop_id || 'Unknown');
        });
        return Array.from(names);
    }, [records]);

    const trendData = useMemo(() => {
        if (!selectedWorkflow) return [];

        const monthlyData = {};
        records.forEach(r => {
            const name = r.psop_name || r.psop_id || 'Unknown';
            if (name !== selectedWorkflow) return;

            const date = new Date(r.started_at || r.created_at);
            const monthKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
            monthlyData[monthKey] = (monthlyData[monthKey] || 0) + 1;
        });

        return Object.entries(monthlyData)
            .map(([month, count]) => ({ month, count }))
            .sort((a, b) => a.month.localeCompare(b.month))
            .slice(-12);
    }, [records, selectedWorkflow]);

    useEffect(() => {
        if (workflowList.length > 0 && !selectedWorkflow) {
            setSelectedWorkflow(workflowList[0]);
        }
    }, [workflowList, selectedWorkflow]);

    const theme = {
        bg: isDark ? 'bg-zinc-900' : 'bg-white',
        border: isDark ? 'border-zinc-700' : 'border-cm-line',
        text: isDark ? 'text-zinc-100' : 'text-cm-heading',
        textSecondary: isDark ? 'text-zinc-400' : 'text-cm-muted',
        chartText: isDark ? '#94A9C2' : '#7188AA',
        grid: isDark ? '#33496A' : '#EAF0F8',
        tooltip: isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-cm-line'
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="flex flex-col items-center gap-3 text-cm-faint dark:text-zinc-500">
                    <div className="w-7 h-7 border-2 border-cm-line dark:border-zinc-700 border-t-cm-primary rounded-full animate-spin" />
                    <span className="text-[12px] font-medium">{t('common.loading')}</span>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full p-6 overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between mb-5">
                <h2 className="cm-section-title dark:text-zinc-100">
                    {t('execution.statistics_title')}
                </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
                <div className="cm-card p-5 dark:bg-zinc-900 dark:border-zinc-700">
                    <div className="flex items-center gap-2 mb-4">
                        <Award size={16} className="text-cm-primary" />
                        <h3 className={`text-[14px] font-bold ${theme.text}`}>
                            {t('execution.frequency_ranking')}
                        </h3>
                    </div>
                    {frequencyRanking.length > 0 ? (
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={frequencyRanking} layout="vertical" margin={{ left: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                                <XAxis type="number" stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 11 }} />
                                <YAxis dataKey="name" type="category" width={150} stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 11 }} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: isDark ? '#142843' : '#FFFFFF',
                                        border: `1px solid ${isDark ? '#33496A' : '#E1E9F6'}`,
                                        borderRadius: '7px',
                                        color: isDark ? '#EEF3FB' : '#172D4D'
                                    }}
                                />
                                <Bar dataKey="count" fill="#2464E8" radius={[0, 4, 4, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-[300px] flex items-center justify-center text-cm-faint dark:text-zinc-500 text-[13px]">
                            {t('execution.no_data')}
                        </div>
                    )}
                </div>

                <div className="cm-card p-5 dark:bg-zinc-900 dark:border-zinc-700">
                    <div className="flex items-center gap-2 mb-4">
                        <Activity size={16} className="text-cm-primary" />
                        <h3 className={`text-[14px] font-bold ${theme.text}`}>
                            {t('execution.status_distribution')}
                        </h3>
                    </div>
                    {statusDistribution.some(s => s.value > 0) ? (
                        <div className="space-y-4">
                            {statusDistribution.map((item, idx) => (
                                <div key={item.name}>
                                    <div className="flex items-center justify-between mb-1.5">
                                        <span className={`text-[13px] font-medium ${theme.text}`}>{item.name}</span>
                                        <span className={`text-[12px] font-mono ${theme.textSecondary}`}>
                                            {item.value} ({item.percentage}%)
                                        </span>
                                    </div>
                                    <div className="h-2 bg-cm-line-soft dark:bg-zinc-800 rounded-[3px] overflow-hidden">
                                        <div
                                            className="h-full rounded-[3px] transition-all duration-500"
                                            style={{
                                                width: `${item.percentage}%`,
                                                backgroundColor: COLORS[idx % COLORS.length]
                                            }}
                                        />
                                    </div>
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="h-[300px] flex items-center justify-center text-cm-faint dark:text-zinc-500 text-[13px]">
                            {t('execution.no_data')}
                        </div>
                    )}
                </div>
            </div>

            <div className="cm-card p-5 dark:bg-zinc-900 dark:border-zinc-700">
                <div className="flex items-center justify-between gap-3 mb-4">
                    <div className="flex items-center gap-2">
                        <TrendingUp size={16} className="text-cm-primary" />
                        <h3 className={`text-[14px] font-bold ${theme.text}`}>
                            {t('execution.monthly_trend')}
                        </h3>
                    </div>
                    <select
                        value={selectedWorkflow || ''}
                        onChange={(e) => setSelectedWorkflow(e.target.value)}
                        className="cm-input max-w-[220px] shrink-0 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-100"
                    >
                        {workflowList.map(wf => (
                            <option key={wf} value={wf}>{wf}</option>
                        ))}
                    </select>
                </div>
                {trendData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={300}>
                        <LineChart data={trendData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                            <XAxis dataKey="month" stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 11 }} />
                            <YAxis stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 11 }} />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: isDark ? '#142843' : '#FFFFFF',
                                    border: `1px solid ${isDark ? '#33496A' : '#E1E9F6'}`,
                                    borderRadius: '7px',
                                    color: isDark ? '#EEF3FB' : '#172D4D'
                                }}
                            />
                            <Line
                                type="monotone"
                                dataKey="count"
                                stroke="#2464E8"
                                strokeWidth={2}
                                dot={{ fill: '#2464E8', r: 3 }}
                                activeDot={{ r: 5 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="h-[300px] flex items-center justify-center text-cm-faint dark:text-zinc-500 text-[13px]">
                        {t('execution.no_data')}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ExecutionStatistics;
