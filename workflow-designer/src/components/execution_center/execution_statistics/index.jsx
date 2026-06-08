import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    PieChart, Pie, Cell, LineChart, Line, Legend
} from 'recharts';
import { Calendar, TrendingUp, Award, Activity } from 'lucide-react';
import { getExecutionRecords } from '@/service/api.js';

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

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
        border: isDark ? 'border-zinc-800' : 'border-zinc-200',
        text: isDark ? 'text-zinc-100' : 'text-zinc-900',
        textSecondary: isDark ? 'text-zinc-400' : 'text-zinc-600',
        chartText: isDark ? '#a1a1aa' : '#52525b',
        grid: isDark ? '#27272a' : '#e4e4e7',
        tooltip: isDark ? 'bg-zinc-800 border-zinc-700' : 'bg-white border-zinc-200'
    };

    if (loading) {
        return (
            <div className="h-full flex items-center justify-center">
                <div className="flex flex-col items-center gap-3 text-zinc-400">
                    <div className="w-8 h-8 border-2 border-zinc-300 dark:border-zinc-600 border-t-blue-500 rounded-full animate-spin" />
                    <span className="text-sm font-bold uppercase tracking-wider">{t('common.loading')}</span>
                </div>
            </div>
        );
    }

    return (
        <div className="h-full p-6 overflow-y-auto custom-scrollbar">
            <div className="flex items-center justify-between mb-6">
                <h2 className="text-lg font-black dark:text-white uppercase">
                    {t('execution.statistics_title')}
                </h2>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                <div className={`${theme.bg} ${theme.border} border rounded-2xl p-6`}>
                    <div className="flex items-center gap-2 mb-4">
                        <Award size={20} className="text-blue-500" />
                        <h3 className={`text-sm font-black uppercase ${theme.text}`}>
                            {t('execution.frequency_ranking')}
                        </h3>
                    </div>
                    {frequencyRanking.length > 0 ? (
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={frequencyRanking} layout="vertical" margin={{ left: 20 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                                <XAxis type="number" stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 12 }} />
                                <YAxis dataKey="name" type="category" width={150} stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 12 }} />
                                <Tooltip
                                    contentStyle={{
                                        backgroundColor: isDark ? '#18181b' : '#fff',
                                        border: `1px solid ${isDark ? '#3f3f46' : '#e4e4e7'}`,
                                        borderRadius: '8px',
                                        color: isDark ? '#fafafa' : '#18181b'
                                    }}
                                />
                                <Bar dataKey="count" fill="#3b82f6" radius={[0, 8, 8, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    ) : (
                        <div className="h-[300px] flex items-center justify-center text-zinc-400 text-sm">
                            {t('execution.no_data')}
                        </div>
                    )}
                </div>

                <div className={`${theme.bg} ${theme.border} border rounded-2xl p-6`}>
                    <div className="flex items-center gap-2 mb-4">
                        <Activity size={20} className="text-emerald-500" />
                        <h3 className={`text-sm font-black uppercase ${theme.text}`}>
                            {t('execution.status_distribution')}
                        </h3>
                    </div>
                    {statusDistribution.some(s => s.value > 0) ? (
                        <div className="space-y-4">
                            {statusDistribution.map((item, idx) => (
                                <div key={item.name}>
                                    <div className="flex items-center justify-between mb-2">
                                        <span className={`text-sm font-bold ${theme.text}`}>{item.name}</span>
                                        <span className={`text-sm font-mono ${theme.textSecondary}`}>
                                            {item.value} ({item.percentage}%)
                                        </span>
                                    </div>
                                    <div className="h-3 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
                                        <div
                                            className="h-full rounded-full transition-all duration-500"
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
                        <div className="h-[300px] flex items-center justify-center text-zinc-400 text-sm">
                            {t('execution.no_data')}
                        </div>
                    )}
                </div>
            </div>

            <div className={`${theme.bg} ${theme.border} border rounded-2xl p-6`}>
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <TrendingUp size={20} className="text-purple-500" />
                        <h3 className={`text-sm font-black uppercase ${theme.text}`}>
                            {t('execution.monthly_trend')}
                        </h3>
                    </div>
                    <select
                        value={selectedWorkflow || ''}
                        onChange={(e) => setSelectedWorkflow(e.target.value)}
                        className={`px-4 py-2 rounded-lg border text-sm font-bold outline-none
                            ${theme.bg} ${theme.border} ${theme.text}`}
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
                            <XAxis dataKey="month" stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 12 }} />
                            <YAxis stroke={theme.chartText} tick={{ fill: theme.chartText, fontSize: 12 }} />
                            <Tooltip
                                contentStyle={{
                                    backgroundColor: isDark ? '#18181b' : '#fff',
                                    border: `1px solid ${isDark ? '#3f3f46' : '#e4e4e7'}`,
                                    borderRadius: '8px',
                                    color: isDark ? '#fafafa' : '#18181b'
                                }}
                            />
                            <Line
                                type="monotone"
                                dataKey="count"
                                stroke="#8b5cf6"
                                strokeWidth={3}
                                dot={{ fill: '#8b5cf6', r: 5 }}
                                activeDot={{ r: 7 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                ) : (
                    <div className="h-[300px] flex items-center justify-center text-zinc-400 text-sm">
                        {t('execution.no_data')}
                    </div>
                )}
            </div>
        </div>
    );
};

export default ExecutionStatistics;
