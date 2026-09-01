// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useState, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Radio, Square, Activity } from 'lucide-react';

export default function SseStream() {
    const { t } = useTranslation('demo-showcase');
    const { api, theme } = usePortalContext();
    const isDark = theme.isDark;
    const [events, setEvents] = useState([]);
    const [running, setRunning] = useState(false);
    const timerRef = useRef(null);

    const startStream = useCallback(() => {
        setEvents([]);
        setRunning(true);
        const mockEvents = [
            { type: 'init', timestamp: new Date().toISOString(), data: { psop_id: 'demo-wf-001' } },
            { type: 'start', timestamp: new Date().toISOString(), data: {} },
            { type: 'agent_request', timestamp: new Date().toISOString(), data: { agent: 'spn-agent', task: 'topology discovery' } },
            { type: 'agent_response', timestamp: new Date().toISOString(), data: { agent: 'spn-agent', status: 'success', duration: '1.2s' } },
            { type: 'agent_request', timestamp: new Date().toISOString(), data: { agent: 'workbench-agent', task: 'workflow execution' } },
            { type: 'agent_response', timestamp: new Date().toISOString(), data: { agent: 'workbench-agent', status: 'success', duration: '3.5s' } },
            { type: 'psop_update', timestamp: new Date().toISOString(), data: { step: 'analyze', progress: '100%' } },
            { type: 'complete', timestamp: new Date().toISOString(), data: { total_duration: '4.7s' } },
            { type: 'close', timestamp: new Date().toISOString(), data: {} },
        ];
        let idx = 0;
        timerRef.current = setInterval(() => {
            if (idx >= mockEvents.length) {
                clearInterval(timerRef.current);
                setRunning(false);
                return;
            }
            setEvents(prev => [...prev, mockEvents[idx]]);
            idx++;
        }, 600);
    }, []);

    const stopStream = useCallback(() => {
        if (timerRef.current) clearInterval(timerRef.current);
        setRunning(false);
    }, []);

    const eventColors = {
        init: 'text-blue-400', start: 'text-emerald-400',
        agent_request: 'text-amber-400', agent_response: 'text-cyan-400',
        psop_update: 'text-purple-400', complete: 'text-emerald-400',
        close: 'text-zinc-400', error: 'text-red-400',
    };

    return (
        <div className="space-y-4">
            <div className="flex gap-3">
                <button
                    onClick={startStream}
                    disabled={running}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-bold text-sm transition-all disabled:opacity-50"
                >
                    <Radio size={16} className={running ? 'animate-pulse' : ''} />
                    {t('sse.start_btn')}
                </button>
                {running && (
                    <button
                        onClick={stopStream}
                        className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-red-500 hover:bg-red-600 text-white font-bold text-sm transition-all"
                    >
                        <Square size={16} />
                        {t('sse.stop_btn')}
                    </button>
                )}
            </div>

            <div className={`rounded-xl border p-4 ${isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200'}`}>
                <div className="flex items-center gap-2 mb-3">
                    <Activity size={14} className={running ? 'text-emerald-500 animate-pulse' : 'text-zinc-400'} />
                    <span className={`text-xs font-bold ${isDark ? 'text-zinc-300' : 'text-zinc-700'}`}>
                        {t('sse.events')} ({events.length})
                    </span>
                    {running && <span className="text-xs text-emerald-500 font-bold">{t('sse.connected')}</span>}
                    {!running && events.length > 0 && <span className="text-xs text-zinc-400 font-bold">{t('sse.closed')}</span>}
                </div>

                {events.length === 0 ? (
                    <div className="py-12 text-center text-zinc-400 text-sm">{t('sse.waiting')}</div>
                ) : (
                    <div className="space-y-1.5 max-h-96 overflow-auto font-mono text-xs">
                        {events.map((evt, i) => (
                            <div key={i} className={`flex items-start gap-3 py-1.5 px-3 rounded-lg ${isDark ? 'bg-zinc-800/30' : 'bg-zinc-50'}`}>
                                <span className="text-zinc-500 shrink-0">{evt.timestamp.split('T')[1]?.split('.')[0] || evt.timestamp}</span>
                                <span className={`font-bold shrink-0 ${eventColors[evt.type] || 'text-zinc-400'}`}>
                                    {evt.type}
                                </span>
                                <span className={`flex-1 ${isDark ? 'text-zinc-400' : 'text-zinc-500'}`}>
                                    {JSON.stringify(evt.data)}
                                </span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
