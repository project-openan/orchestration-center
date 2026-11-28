// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useReducer, useRef, useState } from 'react';
import { getExecutionTimelinePage } from '@/service/api.js';

export async function loadObservationReplay(executionId, afterCursor, throughCursor, signal) {
    const events = [];
    let cursor = Number(afterCursor);
    const end = Number(throughCursor);
    if (!Number.isSafeInteger(cursor) || !Number.isSafeInteger(end) || cursor < 0 || end < cursor) {
        throw new Error('Invalid execution replay cursor range');
    }
    while (cursor < end) {
        const page = await getExecutionTimelinePage(executionId, String(cursor), throughCursor, signal);
        const next = Number(page?.next_cursor);
        if (!Array.isArray(page?.events) || !Number.isSafeInteger(next) || next <= cursor || next > end) {
            throw new Error('Execution replay cursor did not advance within the selected snapshot');
        }
        for (const { event } of page.events) events.push(event);
        cursor = next;
    }
    return events;
}

export function useObservationReplay(executionId, throughCursor) {
    const cache = useRef(null);
    const [result, setResult] = useState(null);
    const [attempt, retry] = useReducer(count => count + 1, 0);

    useEffect(() => {
        if (!executionId || !throughCursor) return;
        const controller = new AbortController();
        const previous = cache.current;
        const reusable = previous?.executionId === executionId
            && Number(previous.throughCursor) <= Number(throughCursor);
        const afterCursor = reusable ? previous.throughCursor : '0';

        loadObservationReplay(executionId, afterCursor, throughCursor, controller.signal)
            .then(delta => {
                if (controller.signal.aborted) return;
                // Arrival cursors can include older execution sequences that arrived late.
                const events = reusable ? [...previous.events, ...delta] : delta;
                events.sort((left, right) => Number(left.seq) - Number(right.seq));
                const snapshot = { executionId, throughCursor, attempt, status: 'ready', events };
                cache.current = snapshot;
                setResult(snapshot);
            })
            .catch(() => {
                if (!controller.signal.aborted) {
                    setResult({ executionId, throughCursor, attempt, status: 'failed' });
                }
            });
        return () => controller.abort();
    }, [executionId, throughCursor, attempt]);

    if (!executionId || !throughCursor) return { status: null };
    const current = result?.executionId === executionId
        && result.throughCursor === throughCursor && result.attempt === attempt;
    return current ? { ...result, retry } : { status: 'loading' };
}
