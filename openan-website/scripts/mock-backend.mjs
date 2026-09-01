// Mock backend for Portal demo — returns realistic data for all endpoints
import http from 'http';

const AGENT_CARDS = [
    {
        name: "spn-agent",
        version: "1.0.0",
        description: "Service Provider Network Agent — manages SPN topology and fault diagnostics",
        provider: { organization: "Huawei" },
        skills: [
            { id: "topo-discovery", name: "Topology Discovery", description: "Discover network topology" },
            { id: "fault-diagnosis", name: "Fault Diagnosis", description: "Diagnose network faults" },
            { id: "config-sync", name: "Config Sync", description: "Synchronize configurations" },
        ],
        capabilities: { streaming: true, pushNotifications: false },
    },
    {
        name: "workbench-agent",
        version: "2.1.0",
        description: "Workbench Agent — orchestrates multi-step workflows via A2A-T protocol",
        provider: { organization: "Huawei" },
        skills: [
            { id: "workflow-exec", name: "Workflow Execution", description: "Execute PSOP workflows" },
            { id: "negotiation", name: "A2A-T Negotiation", description: "Negotiate with peer agents" },
        ],
        capabilities: { streaming: true, pushNotifications: true },
    },
    {
        name: "ericsson-nms",
        version: "3.2.1",
        description: "Ericsson Network Management System — provides fault and performance management",
        provider: { organization: "Ericsson" },
        skills: [
            { id: "alarm-mgmt", name: "Alarm Management", description: "Manage network alarms" },
            { id: "perf-monitor", name: "Performance Monitor", description: "Monitor KPIs" },
        ],
        capabilities: { streaming: false, pushNotifications: true },
    },
    {
        name: "zte-controller",
        version: "1.5.0",
        description: "ZTE SDN Controller — manages transport network segments",
        provider: { organization: "ZTE" },
        skills: [
            { id: "path-compute", name: "Path Computation", description: "Compute optimal paths" },
            { id: "traffic-eng", name: "Traffic Engineering", description: "Engineer traffic flows" },
        ],
        capabilities: { streaming: true, pushNotifications: false },
    },
    {
        name: "service-orchestrator",
        version: "0.9.0",
        description: "Service Orchestrator — end-to-end service provisioning across multi-vendor",
        provider: { organization: "直真" },
        skills: [
            { id: "service-create", name: "Service Creation", description: "Create end-to-end services" },
            { id: "service-monitor", name: "Service Monitoring", description: "Monitor service health" },
        ],
        capabilities: { streaming: true, pushNotifications: true },
    },
    {
        name: "data-analytics",
        version: "2.0.0",
        description: "Data Analytics Agent — ML-driven network analytics and predictions",
        provider: { organization: "新大陆" },
        skills: [
            { id: "anomaly-detect", name: "Anomaly Detection", description: "Detect network anomalies" },
            { id: "capacity-forecast", name: "Capacity Forecast", description: "Forecast capacity needs" },
        ],
        capabilities: { streaming: false, pushNotifications: false },
    },
];

const WORKFLOWS = [
    {
        workflow_id: "wf-001",
        id: "wf-001",
        name: "Fault Diagnosis Workflow",
        description: "End-to-end fault diagnosis across multi-vendor network",
        tags: ["fault", "diagnosis", "multi-vendor"],
        source: "graph_editor",
        steps: [
            { name: "collect-alarms", type: "ALL_SUCCESS", subtasks: [{ task_id: "t1", agent: "ericsson-nms", skill: "alarm-mgmt" }] },
            { name: "analyze", type: "ALL_SUCCESS", subtasks: [{ task_id: "t2", agent: "data-analytics", skill: "anomaly-detect" }] },
        ],
    },
    {
        workflow_id: "wf-002",
        id: "wf-002",
        name: "Service Provisioning",
        description: "Automated end-to-end service provisioning",
        tags: ["service", "provisioning"],
        source: "ai_intent",
        steps: [
            { name: "compute-path", type: "ALL_SUCCESS", subtasks: [{ task_id: "t1", agent: "zte-controller", skill: "path-compute" }] },
        ],
    },
    {
        workflow_id: "wf-003",
        id: "wf-003",
        name: "Capacity Planning",
        description: "ML-driven capacity forecast and optimization",
        tags: ["capacity", "ml"],
        source: "solution_package",
        steps: [
            { name: "forecast", type: "ALL_SUCCESS", subtasks: [{ task_id: "t1", agent: "data-analytics", skill: "capacity-forecast" }] },
        ],
    },
];

const TEMPLATES = [
    { id: "tpl-001", name: "Standard Fault Diagnosis", description: "Standard multi-vendor fault diagnosis template", tags: ["fault"], step_count: 3, agent_count: 2 },
    { id: "tpl-002", name: "Service Activation", description: "End-to-end service activation template", tags: ["service"], step_count: 5, agent_count: 3 },
];

const EXECUTION_RECORDS = [
    { execution_id: "exec-001", psop_id: "wf-001", psop_name: "Fault Diagnosis Workflow", started_at: "2026-08-26T10:00:00Z", completed_at: "2026-08-26T10:05:00Z", status: "completed", step_count: 2 },
    { execution_id: "exec-002", psop_id: "wf-002", psop_name: "Service Provisioning", started_at: "2026-08-26T11:00:00Z", completed_at: null, status: "running", step_count: 1 },
];

function ok(data, message = 'ok') {
    return JSON.stringify({ code: 200, message, status: 'success', data });
}

const server = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    const url = new URL(req.url, 'http://127.0.0.1:5001');
    const path = url.pathname;
    const seg = path.replace('/rest/v1/orchestrate/', '').split('/');

    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
        // Auth
        if (path === '/rest/v1/orchestrate/auth/check') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok({ auth_required: false }));
            return;
        }

        // Agent cards — now served by registry backend (port 5000), not here.

        // Workflows
        if (path === '/rest/v1/orchestrate/workflows' && req.method === 'GET') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok(WORKFLOWS));
            return;
        }
        if (seg[0] === 'workflows' && seg[1] && req.method === 'GET') {
            const wf = WORKFLOWS.find(w => w.id === seg[1]);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok(wf || null));
            return;
        }
        if (path === '/rest/v1/orchestrate/workflows' && req.method === 'POST') {
            res.writeHead(201, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ code: 201, message: 'created', status: 'success', data: { workflow_id: 'wf-new-' + Date.now() } }));
            return;
        }
        if (seg[0] === 'workflows' && seg[1] && req.method === 'DELETE') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok({ deleted: seg[1] }));
            return;
        }

        // Templates
        if (path === '/rest/v1/orchestrate/templates' && req.method === 'GET') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok(TEMPLATES));
            return;
        }

        // Execution records
        if (path === '/rest/v1/orchestrate/execution-records' && req.method === 'GET') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok(EXECUTION_RECORDS));
            return;
        }

        // Execute (SSE) — return a minimal SSE stream
        if (seg[0] === 'execute' && req.method === 'GET') {
            res.writeHead(200, {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            });
            res.write('data: ' + JSON.stringify({ type: 'init', psop_id: url.searchParams.get('psop_id') }) + '\n\n');
            res.write('data: ' + JSON.stringify({ type: 'start' }) + '\n\n');
            setTimeout(() => {
                res.write('data: ' + JSON.stringify({ type: 'complete' }) + '\n\n');
                res.write('data: ' + JSON.stringify({ type: 'close' }) + '\n\n');
                res.end();
            }, 2000);
            return;
        }

        // Retrieve by intent
        if (path === '/rest/v1/orchestrate/retrieve-topn-by-intent' && req.method === 'POST') {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(ok(WORKFLOWS.slice(0, 3).map(w => ({
                workflow_id: w.workflow_id,
                name: w.name,
                description: w.description,
                tags: w.tags,
                score: 0.85 + Math.random() * 0.1,
            }))));
            return;
        }

        // Default
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(ok({}));
    });
});

// ──── Registry Center backend (port 5000) ────
// The registry-center is a SEPARATE service with its own API.
// It serves agent cards at /rest/v1/registry/agent-cards.

const REGISTRY_AGENT_CARDS = [
    {
        name: "spn-agent",
        version: "1.0.0",
        description: "Service Provider Network Agent — manages SPN topology and fault diagnostics",
        provider: { organization: "Huawei" },
        skills: [
            { id: "topo-discovery", name: "Topology Discovery", description: "Discover network topology" },
            { id: "fault-diagnosis", name: "Fault Diagnosis", description: "Diagnose network faults" },
            { id: "config-sync", name: "Config Sync", description: "Synchronize configurations" },
        ],
        capabilities: { streaming: true, pushNotifications: false },
    },
    {
        name: "workbench-agent",
        version: "2.1.0",
        description: "Workbench Agent — orchestrates multi-step workflows via A2A-T protocol",
        provider: { organization: "Huawei" },
        skills: [
            { id: "workflow-exec", name: "Workflow Execution", description: "Execute PSOP workflows" },
            { id: "negotiation", name: "A2A-T Negotiation", description: "Negotiate with peer agents" },
        ],
        capabilities: { streaming: true, pushNotifications: true },
    },
    {
        name: "ericsson-nms",
        version: "3.2.1",
        description: "Ericsson Network Management System — provides fault and performance management",
        provider: { organization: "Ericsson" },
        skills: [
            { id: "alarm-mgmt", name: "Alarm Management", description: "Manage network alarms" },
            { id: "perf-monitor", name: "Performance Monitor", description: "Monitor KPIs" },
        ],
        capabilities: { streaming: false, pushNotifications: true },
    },
    {
        name: "zte-controller",
        version: "1.5.0",
        description: "ZTE SDN Controller — manages transport network segments",
        provider: { organization: "ZTE" },
        skills: [
            { id: "path-compute", name: "Path Computation", description: "Compute optimal paths" },
            { id: "traffic-eng", name: "Traffic Engineering", description: "Engineer traffic flows" },
        ],
        capabilities: { streaming: true, pushNotifications: false },
    },
    {
        name: "service-orchestrator",
        version: "0.9.0",
        description: "Service Orchestrator — end-to-end service provisioning across multi-vendor",
        provider: { organization: "直真" },
        skills: [
            { id: "service-create", name: "Service Creation", description: "Create end-to-end services" },
            { id: "service-monitor", name: "Service Monitoring", description: "Monitor service health" },
        ],
        capabilities: { streaming: true, pushNotifications: true },
    },
    {
        name: "data-analytics",
        version: "2.0.0",
        description: "Data Analytics Agent — ML-driven network analytics and predictions",
        provider: { organization: "新大陆" },
        skills: [
            { id: "anomaly-detect", name: "Anomaly Detection", description: "Detect network anomalies" },
            { id: "capacity-forecast", name: "Capacity Forecast", description: "Forecast capacity needs" },
        ],
        capabilities: { streaming: false, pushNotifications: false },
    },
];

const registryServer = http.createServer((req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    const url = new URL(req.url, 'http://127.0.0.1:5000');
    const path = url.pathname;

    if (path === '/rest/v1/registry/agent-cards' && req.method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(ok(REGISTRY_AGENT_CARDS));
        return;
    }

    // Default
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(ok({}));
});

registryServer.listen(5000, '127.0.0.1', () => {
    console.log('Mock registry backend on http://127.0.0.1:5000');
    console.log('  ' + REGISTRY_AGENT_CARDS.length + ' agent cards (registry own API)');
});

// ──── Orchestration Center backend (port 5001) ────

server.listen(5001, '127.0.0.1', () => {
    console.log('Mock orchestrate backend on http://127.0.0.1:5001');
    console.log('  ' + WORKFLOWS.length + ' workflows, ' + TEMPLATES.length + ' templates');
});
