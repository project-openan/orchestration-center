// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";

vi.mock("react-i18next", () => ({
    useTranslation: () => ({ t: (key) => key }),
}));

vi.mock("@/service/api.js", () => ({
    createWorkflow: vi.fn(),
}));

import Toolbar from "@/components/orchestration_center/workflow/toolbar/index.jsx";
import { SandboxProcessView, SandboxReportView } from "../SandboxDialog.jsx";


const report = {
    mode: "sandbox",
    verdict: "warning",
    scenario: "error",
    static_checks: [
        { check_id: "agents.skill_match", status: "warning", detail: "Skill mismatch", suggestions: ["Check skill"] },
        { check_id: "agents.missing", status: "fail", detail: "Missing agent", suggestions: ["Register agent"] },
    ],
    execution_path: ["a", "merge"],
    context_trace: [{ step: "merge", upstream_steps: ["a"], upstream_result_count: 1 }],
    stub_interactions: [{ step: "a", agent: "agent-a", task_state: "TASK_STATE_FAILED", error_code: "stub.task_failed" }],
    risks: ["An intentional Stub error scenario was selected."],
};

describe("sandbox toolbar entry", () => {
    it("renders the sandbox entry only for a saved workflow", () => {
        const saved = renderToString(<Toolbar workflowId="wf-1" nodes={[]} edges={[]} isDark={false} />);
        expect(saved).toContain("workflow.toolbar.sandbox");

        const unsaved = renderToString(<Toolbar nodes={[]} edges={[]} isDark={false} />);
        expect(unsaved).not.toContain("workflow.toolbar.sandbox");
    });
});

describe("sandbox report view", () => {
    it("renders sandbox identity, verdict, and failure details", () => {
        const html = renderToString(<SandboxReportView report={report} isDark={false} />);

        expect(html).toContain("SANDBOX");
        expect(html).toContain("agents.skill_match");
        expect(html).toContain("agents.missing");
        expect(html).toContain("stub.task_failed");
        expect(html).toContain("sandbox.report.executionPath");
        expect(html).toContain(">a</span>");
        expect(html).toContain(">merge</span>");
    });
});

describe("sandbox process view", () => {
    it("renders ordered lifecycle events with error and completion states", () => {
        const html = renderToString(
            <SandboxProcessView
                isDark={false}
                status="completed"
                events={[
                    { type: "start", data: { workflow: "wf-1" } },
                    { type: "step_start", data: { step: "diagnose" } },
                    { type: "task_request", data: { step: "diagnose", task: "diagnose spn" } },
                    { type: "error", data: { error: "transport failed" } },
                ]}
            />
        );

        expect(html).toContain("start");
        expect(html).toContain("diagnose");
        expect(html).toContain("diagnose spn");
        expect(html).toContain("transport failed");
        expect(html).toContain("01");
    });

    it("renders the waiting state before events arrive", () => {
        const html = renderToString(
            <SandboxProcessView isDark={false} status="running" events={[]} />
        );

        expect(html).toContain("sandbox.waiting");
        expect(html).toContain("running");
    });
});
