import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
    AlertTriangle,
    ArrowRight,
    CheckCircle2,
    FlaskConical,
    Loader,
    Play,
    Send,
    Terminal,
    X,
} from "lucide-react";
import { getSandboxEvents, getSandboxReport, startSandboxRun } from "@/service/api.js";

const SCENARIOS = ["success", "error", "delay", "negotiation"];

const EVENT_ICONS = {
    start: Play,
    step_start: Play,
    step_complete: CheckCircle2,
    task_request: Send,
    task_response: CheckCircle2,
    task_status_changed: CheckCircle2,
    route_decision: ArrowRight,
    agent_request: Send,
    agent_response: CheckCircle2,
    negotiation_request: Send,
    negotiation_resolved: CheckCircle2,
    workflow_complete: CheckCircle2,
    error: AlertTriangle,
};

const VerdictBadge = ({ verdict }) => {
    const { t } = useTranslation();
    const value = String(verdict || "unknown");
    const color = value === "pass"
        ? "bg-emerald-500/10 text-emerald-500"
        : value === "warning"
            ? "bg-amber-500/10 text-amber-500"
            : value === "fail"
                ? "bg-rose-500/10 text-rose-500"
                : "bg-zinc-500/10 text-zinc-500";
    return (
        <span className={`px-2 py-0.5 rounded-md text-[10px] font-black uppercase ${color}`}>
            {t(`sandbox.verdicts.${value}`, { defaultValue: value })}
        </span>
    );
};

const subjectOf = (event) => {
    const data = event?.data || {};
    return data.step || data.agent || data.workflow || "";
};

const detailOf = (event, t) => {
    const data = event?.data || {};
    if (event?.type === "task_request") {
        return data.task || data.task_id || "";
    }
    if (event?.type === "task_status_changed") {
        return data.status ? t(`sandbox.states.${data.status}`, { defaultValue: data.status }) : "";
    }
    if (event?.type === "task_response") {
        return data.status
            ? t(`sandbox.states.${data.status}`, { defaultValue: data.status })
            : data.error || data.error_code || "";
    }
    if (event?.type === "route_decision") {
        return data.decision || data.next_step || "";
    }
    if (event?.type === "workflow_complete") {
        return data.success === true
            ? t("sandbox.states.success")
            : t("sandbox.states.failed");
    }
    if (event?.type === "error") {
        return data.error || data.failure || "";
    }
    return data.skill || data.task || data.task_id || "";
};

export function SandboxProcessView({ events, isDark, status }) {
    const { t } = useTranslation();
    const endRef = useRef(null);

    useEffect(() => {
        endRef.current?.scrollIntoView({ block: "end" });
    }, [events]);

    return (
        <div className="mt-6">
            <div className="flex items-center gap-2 mb-3">
                <Terminal size={15} className="text-violet-500" />
                <h4 className="text-sm font-bold">{t("sandbox.process")}</h4>
                <span className="ml-auto text-[10px] font-bold uppercase opacity-60">
                    {t(`sandbox.states.${status}`, { defaultValue: status })}
                </span>
            </div>
            <div className={`max-h-64 overflow-y-auto custom-scrollbar rounded-xl border p-3 ${
                isDark ? "border-zinc-800 bg-zinc-900/50" : "border-zinc-200 bg-zinc-50"
            }`}>
                {events.length === 0 ? (
                    <p className="text-xs opacity-60">{t("sandbox.waiting")}</p>
                ) : (
                    <div className="relative space-y-3">
                        <div className="absolute left-[13px] top-1 bottom-1 w-px bg-violet-500/20" />
                        {events.map((event, index) => {
                            const Icon = EVENT_ICONS[event?.type] || Terminal;
                            const subject = subjectOf(event);
                            const detail = detailOf(event, t);
                            const isError = event?.type === "error";
                            const isSuccess = event?.type === "step_complete" || event?.type === "workflow_complete";
                            return (
                                <div key={`${event?.type}-${index}`} className="relative flex items-start gap-3">
                                    <span className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${
                                        isError
                                            ? "border-rose-500/40 bg-rose-500/10 text-rose-500"
                                            : isSuccess
                                                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-500"
                                                : isDark
                                                    ? "border-zinc-800 bg-zinc-950 text-violet-400"
                                                    : "border-zinc-200 bg-white text-violet-600"
                                    }`}>
                                        <Icon size={13} />
                                    </span>
                                    <div className="min-w-0 pt-1">
                                        <p className={`text-xs font-semibold break-words ${isError ? "text-rose-500" : ""}`}>
                                            <span className="opacity-40 mr-2">{String(index + 1).padStart(2, "0")}</span>
                                            {t(`sandbox.events.${event?.type || "unknown"}`, {
                                                defaultValue: event?.type || "unknown",
                                            })}
                                            {subject && <span className="ml-2 opacity-70">{subject}</span>}
                                        </p>
                                        {detail && <p className="mt-0.5 text-[11px] opacity-60 break-words">{detail}</p>}
                                    </div>
                                </div>
                            );
                        })}
                        <div ref={endRef} />
                    </div>
                )}
            </div>
        </div>
    );
}

export function SandboxReportView({ report, isDark }) {
    const { t } = useTranslation();
    if (!report) return null;
    return (
        <div className="space-y-4">
            <div className="flex items-center gap-3">
                <span className={`px-2 py-1 rounded-md text-[10px] font-black uppercase ${
                    isDark ? "bg-violet-500/20 text-violet-300" : "bg-violet-100 text-violet-700"
                }`}>
                    SANDBOX
                </span>
                <VerdictBadge verdict={report.verdict} />
                <span className="text-xs uppercase opacity-60">
                    {t(`sandbox.scenarios.${report.scenario}`, { defaultValue: report.scenario })}
                </span>
            </div>

            {report.error && (
                <p className="text-xs text-rose-500">{report.error}</p>
            )}

            <div>
                <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.checks")}</h4>
                <div className="space-y-2">
                    {(report.static_checks || []).map((check) => (
                        <div
                            key={check.check_id}
                            className={`rounded-xl border p-3 ${
                                isDark ? "border-zinc-800 bg-zinc-900/50" : "border-zinc-200 bg-white"
                            }`}
                        >
                            <div className="flex items-center gap-2">
                                <VerdictBadge verdict={check.status} />
                                <span className="text-xs font-bold">
                                    {t(`sandbox.checks.${check.check_id}`, { defaultValue: check.check_id })}
                                </span>
                            </div>
                            <p className="text-xs opacity-70 mt-1">{check.detail}</p>
                            {(check.suggestions || []).map((item) => (
                                <p key={item} className="text-[11px] opacity-60 mt-1">{item}</p>
                            ))}
                        </div>
                    ))}
                </div>
            </div>

            <div>
                <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.executionPath")}</h4>
                {(report.execution_path || []).length > 0 ? (
                    <div className="flex flex-wrap items-center gap-2">
                        {report.execution_path.map((step, index) => (
                            <span key={`${step}-${index}`} className="inline-flex items-center gap-2">
                                {index > 0 && <ArrowRight size={12} className="opacity-40" />}
                                <span className={`px-2 py-1 rounded-lg text-xs font-semibold ${
                                    isDark ? "bg-zinc-900 text-zinc-200" : "bg-zinc-100 text-zinc-700"
                                }`}>{step}</span>
                            </span>
                        ))}
                    </div>
                ) : (
                    <p className="text-xs opacity-70">-</p>
                )}
            </div>

            <div>
                <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.contextTrace")}</h4>
                <div className="space-y-2">
                    {(report.context_trace || []).length > 0 ? report.context_trace.map((trace) => (
                        <div key={`${trace.step}-${trace.subtask_index}`} className="text-xs opacity-70">
                            {trace.step}: {trace.upstream_steps?.join(", ") || t("sandbox.report.noUpstream")} (
                            {trace.upstream_result_count})
                        </div>
                    )) : <p className="text-xs opacity-70">{t("sandbox.report.noContext")}</p>}
                </div>
            </div>

            <div>
                <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.stubInteractions")}</h4>
                <div className="space-y-2">
                    {(report.stub_interactions || []).length > 0 ? report.stub_interactions.map((interaction, index) => (
                        <div key={index} className="text-xs opacity-70">
                            {interaction.step} / {interaction.agent}: {t(
                                `sandbox.taskStates.${interaction.task_state}`,
                                { defaultValue: interaction.task_state },
                            )}
                            {interaction.error_code ? ` (${interaction.error_code})` : ""}
                        </div>
                    )) : <p className="text-xs opacity-70">{t("sandbox.report.noInteractions")}</p>}
                </div>
            </div>

            {(report.risks || []).length > 0 && (
                <div>
                    <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.risks")}</h4>
                    {(report.risks || []).map((risk) => (
                        <p key={risk} className="text-xs text-amber-500">{risk}</p>
                    ))}
                </div>
            )}

            {(report.suggestions || []).length > 0 && (
                <div>
                    <h4 className="text-xs font-bold uppercase opacity-60 mb-2">{t("sandbox.report.suggestions")}</h4>
                    {(report.suggestions || []).map((item) => (
                        <p key={item} className="text-xs opacity-70">{item}</p>
                    ))}
                </div>
            )}
        </div>
    );
}

const SandboxDialog = ({ workflowId, psop, isDark, onClose }) => {
    const { t, i18n } = useTranslation();
    const [scenario, setScenario] = useState("success");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [status, setStatus] = useState("");
    const [events, setEvents] = useState([]);
    const [report, setReport] = useState(null);
    const [phase, setPhase] = useState("idle");
    const cancelledRef = useRef(false);

    const pollReport = useCallback(async (verificationId) => {
        for (let attempt = 0; attempt < 75; attempt += 1) {
            if (cancelledRef.current) return;
            const [reportResponse, eventResponse] = await Promise.all([
                getSandboxReport(verificationId),
                getSandboxEvents(verificationId).catch(() => ({ data: [] })),
            ]);
            const payload = reportResponse?.data || reportResponse;
            const nextEvents = eventResponse?.data || [];
            setStatus(payload?.status || "running");
            setEvents(Array.isArray(nextEvents) ? nextEvents : []);
            if (payload?.report) {
                setReport(payload.report);
                setPhase("completed");
                setLoading(false);
                return;
            }
            await new Promise((resolve) => setTimeout(resolve, 800));
        }
        setError(t("sandbox.stillRunning"));
        setPhase("failed");
        setLoading(false);
    }, [t]);

    const start = async () => {
        if (!workflowId) {
            setError(t("sandbox.saveFirst"));
            return;
        }
        cancelledRef.current = false;
        setLoading(true);
        setError("");
        setReport(null);
        setEvents([]);
        setStatus("starting");
        setPhase("running");
        try {
            const lang = String(i18n.language || "zh").toLowerCase().startsWith("zh") ? "zh" : "en";
            const body = { scenario, lang };
            if (psop) body.psop = psop;
            const response = await startSandboxRun(workflowId, body);
            const verificationId = response?.data?.verification_id;
            if (!verificationId) throw new Error(t("sandbox.missingVerificationId"));
            await pollReport(verificationId);
        } catch (err) {
            setError(err?.response?.data?.detail || err?.message || t("sandbox.failed"));
            setPhase("failed");
            setLoading(false);
        }
    };

    useEffect(() => () => {
        cancelledRef.current = true;
    }, []);

    return createPortal(
        <div className="fixed inset-0 z-[10000] flex items-center justify-center p-6 bg-black/40 backdrop-blur-sm">
            <div className={`w-full max-w-3xl max-h-[88vh] overflow-y-auto custom-scrollbar rounded-2xl border p-6 ${
                isDark ? "bg-zinc-950 border-zinc-800 text-zinc-100" : "bg-white border-zinc-200 text-zinc-900"
            }`}>
                <div className="flex items-center gap-3 mb-6">
                    <FlaskConical size={20} className="text-violet-500" />
                    <h3 className="text-lg font-bold">{t("sandbox.title")}</h3>
                    <button onClick={onClose} className="ml-auto p-2 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800">
                        <X size={16} />
                    </button>
                </div>

                <div className="flex flex-wrap gap-2 mb-6">
                    {SCENARIOS.map((item) => (
                        <button
                            key={item}
                            onClick={() => setScenario(item)}
                            disabled={loading}
                            className={`px-3 py-2 rounded-xl border text-xs font-bold uppercase ${
                                scenario === item
                                    ? "border-violet-500 bg-violet-500/10 text-violet-500"
                                    : isDark
                                        ? "border-zinc-800 text-zinc-400"
                                        : "border-zinc-200 text-zinc-600"
                            }`}
                        >
                            {t(`sandbox.scenarios.${item}`)}
                        </button>
                    ))}
                </div>

                <button
                    onClick={start}
                    disabled={loading || !workflowId}
                    title={workflowId ? t("sandbox.run") : t("sandbox.saveFirst")}
                    className="w-full flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-violet-600 text-white text-sm font-bold disabled:opacity-50"
                >
                    {loading ? <Loader size={16} className="animate-spin" /> : <FlaskConical size={16} />}
                    {t("sandbox.run")}
                </button>

                {error && <p className="mt-4 text-sm text-rose-500">{error}</p>}

                {phase !== "idle" && (
                    <SandboxProcessView
                        events={events}
                        isDark={isDark}
                        status={status || "running"}
                    />
                )}

                {report && <div className="mt-6"><SandboxReportView report={report} isDark={isDark} /></div>}
            </div>
        </div>,
        document.body
    );
};

export default SandboxDialog;
