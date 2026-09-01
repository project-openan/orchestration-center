// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { usePortalContext } from '@openan/portal-sdk';
import { Zap, CheckCircle2, XCircle, Loader2 } from 'lucide-react';

export default function ApiCall() {
    const { t } = useTranslation('demo-showcase');
    const { api, theme } = usePortalContext();
    const isDark = theme.isDark;
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleFetch = async () => {
        setLoading(true);
        setError(null);
        setResult(null);
        try {
            const resp = await api.get('/rest/v1/orchestrate/agent-cards');
            setResult(resp);
        } catch (err) {
            setError(err.message || String(err));
        } finally {
            setLoading(false);
        }
    };

    const cardClass = isDark ? 'bg-zinc-900 border-zinc-800' : 'bg-white border-zinc-200';

    return (
        <div className="space-y-4">
            <button
                onClick={handleFetch}
                disabled={loading}
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-blue-500 hover:bg-blue-600 text-white font-bold text-sm transition-all disabled:opacity-50"
            >
                {loading ? <Loader2 size={16} className="animate-spin" /> : <Zap size={16} />}
                {loading ? t('api.fetching') : t('api.fetch_btn')}
            </button>

            {error && (
                <div className={`rounded-xl border p-4 ${isDark ? 'bg-red-950/30 border-red-900' : 'bg-red-50 border-red-200'}`}>
                    <div className="flex items-center gap-2 text-red-500 mb-2">
                        <XCircle size={16} />
                        <span className="font-bold text-sm">{t('api.error')}</span>
                    </div>
                    <pre className="text-xs text-red-400 font-mono whitespace-pre-wrap">{error}</pre>
                </div>
            )}

            {result && (
                <div className={`rounded-xl border p-4 ${cardClass}`}>
                    <div className="flex items-center gap-2 mb-3">
                        <CheckCircle2 size={16} className="text-emerald-500" />
                        <span className="font-bold text-sm">
                            {t('api.result')} — {Array.isArray(result.data) ? result.data.length : 0} {t('api.count')}
                        </span>
                    </div>
                    <pre className={`text-xs font-mono whitespace-pre-wrap max-h-80 overflow-auto rounded-lg p-3 ${isDark ? 'bg-zinc-950 text-zinc-300' : 'bg-zinc-50 text-zinc-700'}`}>
                        {JSON.stringify(result, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    );
}
