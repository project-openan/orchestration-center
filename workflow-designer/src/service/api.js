import axios from "axios";

const STORAGE_KEY = 'server_config';
export const defaultIp = '127.0.0.1';
export const defaultPort = '60000';

export const getBaseUrl = () => {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        const config = saved ? JSON.parse(saved) : {};
        const ip = config.ip || defaultIp;
        const port = config.port || defaultPort;
        console.log(`http://${ip}:${port}`);
        return `http://${ip}:${port}`;
    } catch (e) {
        return `http://${defaultIp}:${defaultPort}`;
    }
}

const api = axios.create({ timeout: 10000 });

api.interceptors.response.use(
    (response) => response.data,
    (error) => Promise.reject(error)
);

export async function getAgentCards() {
    return api.get(`${getBaseUrl()}/agent-cards`);
}

export async function getWorkflow() {
    return api.get(`${getBaseUrl()}/psops`);
}

export async function getWorkflowById(id) {
    return api.get(`${getBaseUrl()}/psops/${id}`);
}

export async function delWorkflowById(id) {
    return api.delete(`${getBaseUrl()}/psops/${id}`);
}

export async function createWorkflow(data) {
    return api.post(`${getBaseUrl()}/psops`, { psop: data });
}


export async function switchLanguage(local) {
    return axios.post(`${getBaseUrl()}/rest/agents/switch-language?scenario='5g'`, {
        language: local,
    })
}


export async function parsePdf(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await axios.post(`${getBaseUrl()}/parse-pdf`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        });

        if (response.data.status === "success") {
            return JSON.parse(response.data.content);
        } else {
            throw new Error(response.data?.message || "PDF解析失败");
        }
    } catch (error) {
        const errorMsg = error.response?.data?.error || error.message || "PDF解析接口请求失败";
        throw new Error(errorMsg);
    }
}

export async function handlePlan(preflow, agentCards) {
    try {
        const response = await axios.post(`${getBaseUrl()}/plan`, {
            preflow: preflow,
            agent_cards: agentCards
        });

        if (response.data.status === "success") {
            const workflowData = JSON.parse(response.data.data);
            console.log("规划生成成功:", workflowData);
            return workflowData;
        } else {
            throw new Error(response.data?.message || "规划生成失败");
        }
    } catch (error) {
        const errorMsg = error.response?.data?.error || error.message || "规划接口请求失败";
        throw new Error(errorMsg);
    }
}

export async function generateWorkflowFromIntent(intent, name = "Generated Workflow") {
    try {
        const response = await axios.post(`${getBaseUrl()}/generate-from-intent`, {
            user_intent: intent,
            workflow_name: name
        });

        if (response.data.status === "success" || response.status === 200) {
            const workflowData = response.data.data || response.data;
            console.log("自然语言生成成功:", workflowData);
            return workflowData;
        } else {
            throw new Error(response.data?.message || "生成失败");
        }
    } catch (error) {
        const errorMsg = error.response?.data?.error || error.message || "接口请求失败";
        throw new Error(errorMsg);
    }
}

export async function getWorkflowQuestions() {
    return api.get(`${getBaseUrl()}/rest/workflow_questions`);
}

export async function getWorkFlowRecords(questionId) {
    return api.get(`${getBaseUrl()}/rest/workflow_records?questionId=${questionId}`);
}

export async function startProcess(questionId, questionText) {
    return api.post(`${getBaseUrl()}/rest/start_process`, {
        question_id: questionId,
        question_text: questionText
    });
}

export async function deleteWorkflowByQuestionId(questionId) {
    return api.delete(`${getBaseUrl()}/rest/workflow_question?questionId=${questionId}`);
}

export async function deleteWorkflowDbByQuestionId(questionId) {
    return api.delete(`${getBaseUrl()}/rest/workflow_db?questionId=${questionId}`);
}

export function getStartProcessStreamUrl(psopId) {
    return `${getBaseUrl()}/rest/start_process_stream?psop_id=${psopId}`;
}

export async function matchWorkflows(intent) {
    try {
        const response = await axios.post(`${getBaseUrl()}/retrieve-by-intent`, {
            user_intent: intent,
        });

        if (response.data.status === "success" || response.status === 200) {
            const data = response.data.data;
            if (!data) return [];

            const list = Array.isArray(data) ? data : [data];

            return list.map(item => ({
                workflow_id: item.id || item.workflow_id,
                name: item.name || item.workflow_name,
                description: item.description,
                tags: item.tags || []
            }));
        } else {
            throw new Error(response.data?.error || "检索失败");
        }
    } catch (error) {
        const errorMsg = error.response?.data?.error || error.message || "接口请求失败";
        throw new Error(errorMsg);
    }
}

