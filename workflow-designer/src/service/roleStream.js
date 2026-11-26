// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// All Rights Reserved.
//
// SPDX-License-Identifier: Apache-2.0

import { getPortalAwareBaseUrl } from './api.js';

/**
 * POST-based SSE consumer for confirmed role execution.
 *
 * EventSource can only issue GET requests, but the confirmation digest and
 * manual overrides must travel in a JSON body, so the execute endpoint is
 * consumed through fetch and the text/event-stream frames are parsed here.
 * Heartbeat comments (": heartbeat") carry no data and are ignored.
 */
export async function streamRoleExecution(body, { onEvent, onDone, onError }, signal) {
    let response;
    try {
        response = await fetch(`${getPortalAwareBaseUrl()}/rest/v1/orchestrate/role-execution/execute`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
            credentials: 'include',
            body: JSON.stringify(body),
            signal,
        });
    } catch (err) {
        if (err?.name === 'AbortError') return;
        onError?.(err);
        return;
    }
    if (!response.ok || !response.body) {
        let detail = `HTTP ${response.status}`;
        try {
            const payload = await response.json();
            detail = payload?.detail || payload?.message || detail;
        } catch {
            // Non-JSON error body: fall back to the status code.
        }
        onError?.(new Error(detail));
        return;
    }

    const emitFrame = (frame) => {
        for (const line of frame.split('\n')) {
            if (!line.startsWith('data: ')) continue;
            try {
                onEvent?.(JSON.parse(line.slice(6)));
            } catch (err) {
                console.error('Failed to parse role execution event:', err);
            }
        }
    };

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            let boundary;
            while ((boundary = buffer.indexOf('\n\n')) >= 0) {
                const frame = buffer.slice(0, boundary);
                buffer = buffer.slice(boundary + 2);
                emitFrame(frame);
            }
        }
        if (buffer.trim()) emitFrame(buffer);
        onDone?.();
    } catch (err) {
        if (err?.name === 'AbortError') return;
        onError?.(err);
    }
}
