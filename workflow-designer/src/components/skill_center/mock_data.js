export const mockSkills = [
    {
        id: 'skill-001',
        name: 'RAN ES Intent Exploration',
        description: '评估并确定指定RAN ES意图目标的最佳可能性，考虑当前资源状况和系统能力。支持多维度分析和智能推荐。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['wireless', 'energy-saving', 'intent', 'exploration'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '2.1.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-15' },
            { version: '2.0.0', status: 'deprecated', riskLevel: 'medium', createdAt: '2026-03-01' },
            { version: '1.0.0', status: 'archived', riskLevel: 'low', createdAt: '2025-11-20' }
        ],
        createdAt: '2025-11-20T08:00:00Z',
        updatedAt: '2026-05-15T10:30:00Z'
    },
    {
        id: 'skill-002',
        name: 'Intent Generation',
        description: '根据探索报告和业务需求生成RAN节能意图内容，包括不同时段、不同RAT的吞吐量和节能目标。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['wireless', 'energy-saving', 'intent', 'generation'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '1.3.0', status: 'active', riskLevel: 'low', createdAt: '2026-04-20' },
            { version: '1.2.0', status: 'active', riskLevel: 'low', createdAt: '2026-02-10' }
        ],
        createdAt: '2025-12-01T08:00:00Z',
        updatedAt: '2026-04-20T14:00:00Z'
    },
    {
        id: 'skill-003',
        name: 'Event Info Parsing',
        description: '提取赛事的路线与业务需求，支持多种格式解析和智能字段映射。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['live', 'info', 'parsing', 'streaming'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Standard' },
        versions: [
            { version: '1.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-01-10' }
        ],
        createdAt: '2026-01-10T08:00:00Z',
        updatedAt: '2026-01-10T08:00:00Z'
    },
    {
        id: 'skill-004',
        name: 'KQI Monitoring',
        description: '实时反馈保障任务关键质量指标及任务状态，提供告警和趋势分析能力。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['live', 'monitoring', 'kqi', 'realtime'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '2.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-01' },
            { version: '1.5.0', status: 'deprecated', riskLevel: 'medium', createdAt: '2026-02-15' }
        ],
        createdAt: '2025-10-05T08:00:00Z',
        updatedAt: '2026-05-01T09:00:00Z'
    },
    {
        id: 'skill-005',
        name: 'Strategy Generation',
        description: '将赛事保障需求转换为网络需求，包含带宽上下行要求等策略参数。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['assurance', 'strategy', 'network', 'bandwidth'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '1.1.0', status: 'active', riskLevel: 'low', createdAt: '2026-03-20' }
        ],
        createdAt: '2026-01-15T08:00:00Z',
        updatedAt: '2026-03-20T16:00:00Z'
    },
    {
        id: 'skill-006',
        name: 'Analysis and Evaluations',
        description: '分析网络负载现状，提供容量评估和优化建议。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['ran', 'analysis', 'evaluation', 'capacity'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Standard' },
        versions: [
            { version: '3.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-10' },
            { version: '2.5.0', status: 'active', riskLevel: 'low', createdAt: '2026-03-01' },
            { version: '2.0.0', status: 'deprecated', riskLevel: 'medium', createdAt: '2025-12-01' }
        ],
        createdAt: '2025-09-01T08:00:00Z',
        updatedAt: '2026-05-10T11:00:00Z'
    },
    {
        id: 'skill-007',
        name: 'Plan Design',
        description: '根据网络负载现状及网络保障需求规划网络策略方案，支持多方案对比和推荐。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['ran', 'plan', 'design', 'optimization'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '2.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-04-15' }
        ],
        createdAt: '2025-11-10T08:00:00Z',
        updatedAt: '2026-04-15T13:00:00Z'
    },
    {
        id: 'skill-008',
        name: 'Network Policy Execution',
        description: '执行或恢复网络策略，支持灰度发布和回滚机制。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['ran', 'exec', 'policy', 'rollback'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '1.2.0', status: 'active', riskLevel: 'medium', createdAt: '2026-05-05' },
            { version: '1.1.0', status: 'active', riskLevel: 'low', createdAt: '2026-02-20' }
        ],
        createdAt: '2025-12-20T08:00:00Z',
        updatedAt: '2026-05-05T15:00:00Z'
    },
    {
        id: 'skill-009',
        name: 'Dispatch Diagnosis',
        description: '向多个地市SPN故障处理Agent同时下发专线故障诊断指令，支持并行执行和结果汇总。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['dispatch', 'diagnosis', 'spn', 'parallel'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '1.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-03-10' }
        ],
        createdAt: '2026-03-10T08:00:00Z',
        updatedAt: '2026-03-10T08:00:00Z'
    },
    {
        id: 'skill-010',
        name: 'Aggregate Analysis',
        description: '收集并汇总各地市SPN Agent的诊断结果，进行综合分析并生成报告。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['aggregate', 'analysis', 'report', 'spn'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Standard' },
        versions: [
            { version: '1.1.0', status: 'active', riskLevel: 'low', createdAt: '2026-04-01' },
            { version: '1.0.0', status: 'deprecated', riskLevel: 'low', createdAt: '2026-01-20' }
        ],
        createdAt: '2026-01-20T08:00:00Z',
        updatedAt: '2026-04-01T10:00:00Z'
    },
    {
        id: 'skill-011',
        name: 'Leased-line Fault Diagnosis',
        description: '根据接收到的指令，对专线进行故障诊断，输出诊断结果和修复建议。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['spn', 'diagnosis', 'fault', 'leased-line'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '2.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-20' },
            { version: '1.0.0', status: 'deprecated', riskLevel: 'medium', createdAt: '2025-10-15' }
        ],
        createdAt: '2025-10-15T08:00:00Z',
        updatedAt: '2026-05-20T08:00:00Z'
    },
    {
        id: 'skill-012',
        name: 'Uncertainty Simulation',
        description: '模拟需要更多信息才能完成任务的场景，触发引擎的协商流程。用于测试A2A-T履约协商功能。',
        author: 'Huawei',
        domain: '算',
        category: 'ServiceLayer',
        tags: ['uncertainty', 'negotiation', 'simulation', 'testing'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Community' },
        versions: [
            { version: '1.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-02-01' }
        ],
        createdAt: '2026-02-01T08:00:00Z',
        updatedAt: '2026-02-01T08:00:00Z'
    },
    {
        id: 'skill-013',
        name: 'Cloud Resource Provisioning',
        description: '自动化云资源申请和配置，支持多云环境下的资源编排和弹性伸缩。',
        author: 'Huawei',
        domain: '云',
        category: 'ServiceLayer',
        tags: ['cloud', 'provisioning', 'automation', 'multi-cloud'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '3.2.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-25' },
            { version: '3.1.0', status: 'active', riskLevel: 'low', createdAt: '2026-04-10' },
            { version: '3.0.0', status: 'deprecated', riskLevel: 'medium', createdAt: '2026-01-05' }
        ],
        createdAt: '2025-08-15T08:00:00Z',
        updatedAt: '2026-05-25T12:00:00Z'
    },
    {
        id: 'skill-014',
        name: 'Revenue Analytics',
        description: '分析网络运营收入数据，提供ROI评估和营收视图。',
        author: 'Huawei',
        domain: '营',
        category: 'ServiceLayer',
        tags: ['revenue', 'analytics', 'roi', 'operations'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Standard' },
        versions: [
            { version: '1.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-04-25' }
        ],
        createdAt: '2026-04-25T08:00:00Z',
        updatedAt: '2026-04-25T08:00:00Z'
    },
    {
        id: 'skill-015',
        name: 'Intent Lifecycle Management',
        description: '管理RAN节能意图的生命周期，包括创建、修改、删除、激活、去激活意图，并执行数据采集、分析、解决方案制定与配置。',
        author: 'Huawei',
        domain: '网',
        category: 'ServiceLayer',
        tags: ['wireless', 'energy-saving', 'intent', 'lifecycle'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '2.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-05-18' },
            { version: '1.5.0', status: 'deprecated', riskLevel: 'low', createdAt: '2026-02-28' }
        ],
        createdAt: '2025-11-01T08:00:00Z',
        updatedAt: '2026-05-18T14:00:00Z'
    },
    {
        id: 'skill-016',
        name: 'Recovery Delivery',
        description: '恢复保障前网络配置，支持一键回滚和配置验证。',
        author: 'Huawei',
        domain: '维',
        category: 'ServiceLayer',
        tags: ['assurance', 'recovery', 'rollback', 'verification'],
        vendor: { name: 'Huawei', contact: 'support@huawei.com', supportLevel: 'Enterprise' },
        versions: [
            { version: '1.0.0', status: 'active', riskLevel: 'low', createdAt: '2026-03-15' }
        ],
        createdAt: '2026-03-15T08:00:00Z',
        updatedAt: '2026-03-15T08:00:00Z'
    }
];

export const domainColors = {
    '网': { bg: 'bg-indigo-500', light: 'bg-indigo-100 dark:bg-indigo-900/30', text: 'text-indigo-600 dark:text-indigo-400', border: 'border-indigo-300 dark:border-indigo-700' },
    '云': { bg: 'bg-emerald-500', light: 'bg-emerald-100 dark:bg-emerald-900/30', text: 'text-emerald-600 dark:text-emerald-400', border: 'border-emerald-300 dark:border-emerald-700' },
    '维': { bg: 'bg-amber-500', light: 'bg-amber-100 dark:bg-amber-900/30', text: 'text-amber-600 dark:text-amber-400', border: 'border-amber-300 dark:border-amber-700' },
    '算': { bg: 'bg-violet-500', light: 'bg-violet-100 dark:bg-violet-900/30', text: 'text-violet-600 dark:text-violet-400', border: 'border-violet-300 dark:border-violet-700' },
    '营': { bg: 'bg-rose-500', light: 'bg-rose-100 dark:bg-rose-900/30', text: 'text-rose-600 dark:text-rose-400', border: 'border-rose-300 dark:border-rose-700' },
};
