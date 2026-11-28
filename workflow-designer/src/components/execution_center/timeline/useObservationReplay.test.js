// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0

import { beforeEach, expect, it, vi } from 'vitest';
import { getExecutionTimelinePage } from '@/service/api.js';
import { loadObservationReplay } from './useObservationReplay.js';

vi.mock('@/service/api.js', () => ({ getExecutionTimelinePage: vi.fn() }));

beforeEach(() => getExecutionTimelinePage.mockReset());

it('walks the frozen cursor range even when a page has no projected events', async () => {
    const signal = new AbortController().signal;
    const earlyReply = { seq: '2', type: 'task_status_changed', data: { summary: 'early reply' } };
    const outcome = { seq: '1100', type: 'complete', data: {} };
    getExecutionTimelinePage
        .mockResolvedValueOnce({ events: [], next_cursor: '1' })
        .mockResolvedValueOnce({ events: [{ event: earlyReply }], next_cursor: '101' })
        .mockResolvedValueOnce({ events: [{ event: outcome }], next_cursor: '1100' });

    await expect(loadObservationReplay('run', '0', '1100', signal)).resolves.toEqual([earlyReply, outcome]);
    expect(getExecutionTimelinePage.mock.calls).toEqual([
        ['run', '0', '1100', signal],
        ['run', '1', '1100', signal],
        ['run', '101', '1100', signal],
    ]);
});

it('rejects an incomplete page chain instead of treating it as a complete replay', async () => {
    getExecutionTimelinePage.mockResolvedValueOnce({ events: [], next_cursor: '100' });
    await expect(loadObservationReplay('run', '100', '1100')).rejects.toThrow('cursor did not advance');
    expect(getExecutionTimelinePage).toHaveBeenCalledTimes(1);
});
