# PSOP Orchestration Center API 文档

## 概述

PSOP (Parallel-Standard Operation Process) 是运行时工作流，用于系统执行。它定义了明确的任务及其在智能体粒度上的关系。每个任务指定了使用哪个智能体和技能。

本文档描述了 `framework/server/frontend_support_server.py` 中的所有API接口。

## 服务器信息

- **服务器地址**: `http://localhost:60000`
- **启动命令**: `python -m framework.server.frontend_support_server`
- **默认端口**: 60000
- **日志输出**: 启动时会显示所有可用接口

## 接口概览

### 1. PDF解析接口
- `POST /parse-pdf` - 上传PDF文件并解析

### 2. 工作流规划接口
- `POST /plan` - 提交任务和步骤，获取规划结果

### 3. PSOP管理接口
- `GET /psops` - 获取PSOP列表
- `GET /psops/<workflow_id>` - 根据ID获取PSOP详情
- `POST /psops` - 保存PSOP
- `DELETE /psops/<workflow_id>` - 删除PSOP

### 4. AgentCard管理接口
- `GET /agent-cards` - 获取全量AgentCard列表

### 5. 意图生成接口
- `POST /generate-from-intent` - 根据自然语言意图生成PSOP
- `POST /retrieve-by-intent` - 根据自然语言意图检索PSOP

### 6. SSE执行接口
- `GET /rest/start_process_stream?psop_id=<id>` - 启动PSOP执行并推送实时进展

---

## 接口详情

### 1. PDF解析接口

#### `POST /parse-pdf`

上传PDF文件并解析"5. Interaction Flow"章节。

**请求**:
- **方法**: POST
- **Content-Type**: multipart/form-data

**参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| file | file | 是 | PDF文件 |

**响应**:
```json
{
  "status": "success",
  "message": "PDF文件解析成功",
  "content": "PreFlow JSON数据"
}
```

**错误响应**:
- 400: 未提供文件、文件名为空、非PDF文件
- 400: PDF解析失败，未找到指定章节
- 500: 解析失败

---

### 2. 工作流规划接口

#### `POST /plan`

提交任务和步骤，获取规划结果。

**请求**:
- **方法**: POST
- **Content-Type**: application/json

**请求体**:
```json
{
  "preflow": {
    "name": "工作流名称",
    "description": "工作流描述",
    "steps_md": "Markdown格式的步骤描述"
  },
  "agent_cards": [
    {
      "name": "Agent名称",
      "description": "Agent描述",
      "skills": ["技能1", "技能2"]
    }
  ]
}
```

**响应**:
```json
{
  "status": "success",
  "data": "PSOP工作流JSON数据"
}
```

**错误响应**:
- 400: 请求体为空
- 400: 缺少必要字段
- 500: 规划失败

---

### 3. PSOP管理接口

#### 3.1 `GET /psops`

获取所有PSOP的列表。

**请求**:
- **方法**: GET

**查询参数**:
| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|--------|------|------|--------|------|
| limit | integer | 否 | 10 | 返回结果数量限制 |
| workflow_type | string | 否 | "psop" | 工作流类型，可选值: "all", "psop", "preflow" |

**响应**:
```json
{
  "status": "success",
  "count": 2,
  "data": [
    {
      "workflow_id": "test-psop-001",
      "workflow_type": "psop",
      "name": "能源节约分析流程",
      "description": "用于分析能源使用情况的PSOP",
      "tags": ["energy", "analysis", "automation"],
      "created_at": "2026-03-18T18:18:26.264191",
      "score": 1.0
    }
  ]
}
```

#### 3.2 `GET /psops/<workflow_id>`

根据ID获取单个PSOP的完整详情。

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| workflow_id | string | 是 | PSOP的唯一标识符 |

**响应**:
```json
{
  "status": "success",
  "data": {
    "id": "test-psop-001",
    "name": "能源节约分析流程",
    "description": "用于分析能源使用情况的PSOP",
    "created_at": "2026-03-18T18:18:26.264191",
    "steps": [
      {
        "name": "数据收集",
        "type": "AllSuccess",
        "subtasks": [
          {
            "description": "收集能源使用数据",
            "agent": "data-collector",
            "skill": "data-collection",
            "status": "pending"
          }
        ],
        "next": null
      }
    ],
    "related_preflow": null,
    "user_intent": null,
    "tags": ["energy", "analysis", "automation"]
  }
}
```

#### 3.3 `POST /psops`

保存PSOP到存储系统。

**请求**:
- **方法**: POST
- **Content-Type**: application/json

**请求体**:
PSOP的JSON数据，必须符合PSOP模型定义。

**响应**:
```json
{
  "status": "success",
  "message": "PSOP保存成功",
  "workflow_id": "test-psop-003"
}
```

#### 3.4 `DELETE /psops/<workflow_id>`

删除指定ID的PSOP工作流。

**请求**:
- **方法**: DELETE

**路径参数**:
| 参数名 | 类型 | 必填 | 描述 |
|--------|------|------|------|
| workflow_id | string | 是 | PSOP的唯一标识符 |

**响应**:
**成功响应 (200 OK):**
```json
{
  "status": "success",
  "message": "PSOP test-psop-001 删除成功"
}
```

**错误响应 (404 Not Found):**
```json
{
  "error": "未找到ID为 test-psop-999 的PSOP"
}
```

**错误响应 (500 Internal Server Error):**
```json
{
  "error": "删除PSOP失败: 文件可能不存在"
}
```

**使用示例**:
```bash
# 删除ID为test-psop-001的PSOP
curl -X DELETE "http://localhost:60000/psops/test-psop-001"
```

---

### 4. AgentCard管理接口

#### `GET /agent-cards`

获取全量AgentCard列表。

**请求**:
- **方法**: GET

**响应**:
```json
{
  "status": "success",
  "count": 5,
  "data": [
    {
      "name": "Agent名称",
      "description": "Agent描述",
      "skills": ["技能1", "技能2"],
      "config": {}
    }
  ]
}
```

---

### 5. 意图生成接口

#### 5.1 `POST /generate-from-intent`

根据自然语言意图生成PSOP工作流。

**请求**:
- **方法**: POST
- **Content-Type**: application/json

**请求体**:
```json
{
  "user_intent": "自然语言描述的业务意图",
  "workflow_name": "可选的工作流名称"
}
```

**响应**:
```json
{
  "status": "success",
  "message": "PSOP生成成功",
  "data": {
    "id": "psop-uuid",
    "name": "PSOP名称",
    "description": "PSOP描述",
    "steps": [...],
    "tags": [...],
    "created_at": "2024-01-01T00:00:00"
  }
}
```

#### 5.2 `POST /retrieve-by-intent`

根据自然语言意图检索最合适的PSOP工作流。

**请求**:
- **方法**: POST
- **Content-Type**: application/json

**请求体**:
```json
{
  "user_intent": "自然语言描述的业务意图"
}
```

**响应**:
找到匹配的PSOP:
```json
{
  "status": "success",
  "message": "PSOP检索成功",
  "data": {
    "id": "psop-uuid",
    "name": "PSOP名称",
    "description": "PSOP描述",
    "steps": [...],
    "tags": [...],
    "created_at": "2024-01-01T00:00:00"
  }
}
```

未找到匹配的PSOP:
```json
{
  "status": "success",
  "message": "未找到匹配的PSOP",
  "data": null
}
```

---

### 6. SSE执行接口

#### `GET /rest/start_process_stream`

启动PSOP工作流执行，并通过Server-Sent Events (SSE) 实时推送执行进度和事件到前端。

**请求**:
- **方法**: GET
- **Content-Type**: text/event-stream

**查询参数**:
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| psop_id | string | 是 | 要执行的PSOP工作流ID |

**响应格式**:
SSE事件流，每个事件格式如下：
```
data: {"type": "事件类型", "data": {事件数据}, "timestamp": 时间戳}
```

**事件类型**:
1. **init** - 初始化事件
2. **start** - 开始执行事件
3. **agent_request** - Agent请求事件
4. **agent_response** - Agent响应事件
5. **psop_update** - PSOP状态更新事件
6. **complete** - 完成事件
7. **error** - 错误事件
8. **close** - 关闭事件

**示例事件**:
```json
{
  "type": "agent_request",
  "data": {
    "agent": "RAN Energy Saving Agent",
    "request": "{\"contextId\": null, \"extensions\": null, \"kind\": \"message\", \"messageId\": \"73d37d27-7cd7-4b70-a099-8ec90aef1858\", \"metadata\": null, \"parts\": [{\"kind\": \"text\", \"metadata\": null, \"text\": \"获取包含目标最佳可能值的RAN节能探索报告\"}], \"referenceTaskIds\": null, \"role\": \"user\", \"taskId\": null}"
  },
  "timestamp": 1234567890.789
}
```

---

## PSOP数据结构

### PSOP模型定义
```python
class PSOP(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()),
                    description="Unique workflow identifier (auto-generated if not provided)")
    name: str = Field(..., description="Workflow name", examples=['energy_saving_process', 'fault_diagnosis_process'])
    description: Optional[str] = Field(None, description="Brief work description, empty by default")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    steps: List[Step] = Field(..., description="List of steps in the agent collaboration workflow")
    related_preflow: Optional[str] = Field(None,
                                           description="Associated Preflow ID that this PSOP was generated from")
    user_intent: Optional[str] = Field(None,
                                       description="Original user intent that generated this workflow")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for quick filtering")
```

### Step模型定义
```python
class Step(BaseModel):
    name: str = Field(..., description="Step identifier", examples=['step1', 'step2'])
    type: StepType = Field(StepType.ALL_SUCCESS,
                           description="Step success condition")
    subtasks: List[Task] = Field(..., description="List of subtasks within the step")
    next: Optional[List[JumpCondition]] = Field(None,
                                                description="Jump conditions to next steps")
```

### Task模型定义
```python
class Task(BaseModel):
    description: str = Field(..., description="Task description")
    agent: str = Field(..., description="Name of the agent executing the task")
    skill: str = Field(..., description="Skill required to execute the task")
    status: TaskStatus = Field(TaskStatus.PENDING, description="Task execution status")
```

### 枚举类型
```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"

class StepType(str, Enum):
    ALL_SUCCESS = "AllSuccess"
    ANY_SUCCESS = "AnySuccess"
```

---

## 使用示例

### Python示例
```python
import requests
import json

BASE_URL = "http://localhost:60000"

# 1. 获取PSOP列表
def get_psop_list(limit=10):
    response = requests.get(f"{BASE_URL}/psops", params={"limit": limit})
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"获取列表失败: {response.text}")

# 2. 保存PSOP
def save_psop(psop_data):
    headers = {"Content-Type": "application/json"}
    response = requests.post(f"{BASE_URL}/psops", 
                           json=psop_data, 
                           headers=headers)
    if response.status_code == 201:
        return response.json()
    else:
        raise Exception(f"保存失败: {response.text}")

# 3. 根据意图检索PSOP
def retrieve_psop_by_intent(user_intent):
    url = f"{BASE_URL}/retrieve-by-intent"
    payload = {"user_intent": user_intent}
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

# 4. 删除PSOP
def delete_psop(workflow_id):
    response = requests.delete(f"{BASE_URL}/psops/{workflow_id}")
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        raise Exception(f"PSOP不存在: {workflow_id}")
    else:
        raise Exception(f"删除失败: {response.text}")

# 5. 启动PSOP执行（SSE）
def start_psop_execution(psop_id):
    url = f"{BASE_URL}/rest/start_process_stream?psop_id={psop_id}"
    event_source = requests.get(url, stream=True)
    
    for line in event_source.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                event_data = json.loads(line_str[6:])
                print(f"事件类型: {event_data['type']}")
                print(f"事件数据: {event_data['data']}")
```

### JavaScript SSE示例
```javascript
// 创建EventSource连接
const psopId = 'd188df84-0dba-48af-ad49-8a7eafee1abb';
const eventSource = new EventSource(`/rest/start_process_stream?psop_id=${psopId}`);

// 监听消息事件
eventSource.onmessage = function(event) {
  try {
    const data = JSON.parse(event.data);
    
    switch(data.type) {
      case 'init':
        console.log('初始化:', data.data.message);
        break;
        
      case 'start':
        console.log('开始执行工作流:', data.data.psop_id);
        break;
        
      case 'agent_request':
        console.log(`Agent请求: ${data.data.agent}`);
        break;
        
      case 'agent_response':
        console.log(`Agent响应: ${data.data.agent}`);
        break;
        
      case 'psop_update':
        console.log('PSOP状态更新');
        break;
        
      case 'complete':
        console.log('工作流执行完成');
        eventSource.close();
        break;
        
      case 'error':
        console.error('执行错误:', data.data.error);
        eventSource.close();
        break;
    }
  } catch (error) {
    console.error('解析事件数据失败:', error);
  }
};

// 监听错误事件
eventSource.onerror = function(error) {
  console.error('SSE连接错误:', error);
  eventSource.close();
};
```

---

## 错误处理指南

### 常见错误及解决方法

1. **400 Bad Request**
   - **原因**: 请求体为空或格式错误
   - **解决方法**: 检查请求体是否为有效的JSON格式

2. **404 Not Found**
   - **原因**: 请求的PSOP ID不存在
   - **解决方法**: 检查PSOP ID是否正确，或先调用列表接口确认可用ID

3. **500 Internal Server Error**
   - **原因**: 服务器内部错误或数据验证失败
   - **解决方法**: 
     - 检查数据结构是否符合模型定义
     - 查看服务器日志获取详细错误信息
     - 确保所有必需字段都已提供

### SSE连接问题
- **连接中断**: SSE连接可能因网络问题中断，建议前端实现重连机制
- **超时处理**: 长时间无响应应考虑超时处理
- **浏览器兼容性**: 确保目标浏览器支持EventSource API

---

## 注意事项

1. **ID生成**: 如果请求中不提供`id`字段，系统会自动生成UUID作为ID
2. **时间戳**: `created_at`字段会自动设置为当前时间
3. **数据持久化**: PSOP数据保存在`workflow_storage/psop/`目录下的JSON文件中
4. **并发安全**: 接口支持并发访问，但同一ID的PSOP多次保存会覆盖之前的数据
5. **数据验证**: 所有输入数据都会进行严格的Pydantic验证
6. **LLM调用**: 意图生成和检索接口需要调用LLM API，响应时间可能较长
7. **环境变量**: 需要设置`DEEPSEEK_API_KEY`环境变量用于LLM调用

---

## 接口关系图

```
PDF解析 → 生成PreFlow → 规划 → 生成PSOP → 保存 → 执行
    ↑           ↑          ↑         ↑         ↑
    └───────────┴──────────┴─────────┴─────────┘
          AgentCard管理          意图生成/检索
```

## 调试建议

1. **查看日志**: 服务器启动时会显示所有可用接口
2. **测试顺序**: 建议按以下顺序测试接口：
   - 获取AgentCard列表 (`GET /agent-cards`)
   - 获取PSOP列表 (`GET /psops`)
   - 保存PSOP (`POST /psops`)
   - 删除PSOP (`DELETE /psops/<id>`)
   - 执行PSOP (`GET /rest/start_process_stream`)
3. **使用工具**: 使用Postman或curl测试API接口
4. **检查端口**: 确保服务器端口(60000)可访问
5. **验证数据**: 确保PSOP数据结构正确

---

## 更新日志

- **2026-03-26**: 新增PSOP删除接口 (`DELETE /psops/<id>`)
- **2026-03-24**: 新增SSE执行接口
- **2026-03-23**: 新增意图检索接口
- **2026-03-18**: 新增PSOP管理接口
- **2026-03-15**: 初始版本，包含PDF解析和规划接口