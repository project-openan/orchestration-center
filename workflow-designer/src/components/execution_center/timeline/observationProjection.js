// Copyright (c) 2026 Huawei Technologies Co., Ltd.
// SPDX-License-Identifier: Apache-2.0

export function observationOutcome(outcome, defaultStatus = 'running') {
    return {
        succeeded: 'completed',
        success: 'completed',
        failed: 'failed',
        cancelled: 'cancelled',
        stopped: 'cancelled',
        skipped: 'skipped',
    }[outcome] ?? defaultStatus;
}

export function timelineStatusText(status) {
    return {
        running: '执行中', completed: '已完成', failed: '失败',
        cancelled: '已取消', skipped: '已跳过',
    }[status] ?? '等待中';
}

export function observedSteps(workflow, { stepHistory, taskHistory, projectedThrough }, events) {
    const steps = new Map();
    const progressByAttempt = new Map();
    for (const event of events) {
        const data = event.data;
        if (!data?.task_id || !Number.isSafeInteger(Number(event.seq)) || Number(event.seq) > Number(projectedThrough)
            || (event.type !== 'task_status_changed' && !data.interaction)) continue;
        const key = `${data.task_id}:${data.attempt}`;
        const progress = progressByAttempt.get(key) ?? { summaries: new Set(), interactions: 0 };
        if (typeof data.summary === 'string') progress.summaries.add(data.summary);
        if (data.interaction) progress.interactions++;
        progressByAttempt.set(key, progress);
    }
    const stepFor = ref => {
        if (!steps.has(ref)) {
            const index = Number(ref.slice(1));
            const definition = workflow?.steps?.[index];
            steps.set(ref, {
                ref, index, definition,
                name: definition?.name ?? ref,
                status: 'running',
                interactions: [],
                tasks: [],
                isSelfLoop: false,
            });
        }
        return steps.get(ref);
    };
    for (const state of stepHistory) {
        const step = stepFor(state.step_ref);
        step.status = observationOutcome(state.outcome);
        step.startTime = Date.parse(state.started_at) / 1000;
        step.endTime = Date.parse(state.completed_at) / 1000;
        step.error = state.error;
    }
    for (const state of taskHistory) {
        const step = stepFor(state.step_ref);
        const subtaskIndex = Number(state.task_ref.split('/t')[1]);
        const definition = step.definition?.subtasks?.[subtaskIndex];
        const content = state.result?.summary || state.summary || '';
        const progress = progressByAttempt.get(`${state.task_id}:${state.attempt}`);
        step.tasks.push({
            key: state.task_id,
            taskRef: state.task_ref,
            subtaskIndex,
            agent: definition?.agent,
            description: definition?.description,
            status: observationOutcome(state.outcome),
            attempt: state.attempt,
            attemptCount: Object.keys(state.attempts ?? {}).length,
            inputSummary: typeof state.input_summary === 'string' ? state.input_summary : '',
            content: typeof content === 'string' ? content : '',
            progress: progress ? [...progress.summaries] : [],
            outputs: state.result?.outputs,
            error: state.error,
            interactionCount: progress?.interactions ?? 0,
        });
    }
    const ordered = [...steps.values()].sort((left, right) => left.index - right.index);
    ordered.forEach(step => step.tasks.sort((left, right) => left.subtaskIndex - right.subtaskIndex));
    return ordered;
}
