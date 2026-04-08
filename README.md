# A2A-T 多智能体编排中心

## 项目简介

编排中心是一个用于编排多个 Agent（智能体）协作的 Web 平台。用户在可视化工作流设计器中编排 Agent 之间的调用关系和流程图，后端 Python 框架负责解析流程、执行编排逻辑并驱动 Agent 协同工作。

## 核心功能

### 1. 可视化工作流设计器
- **拖拽式编排**: 基于 React Flow 的可视化画布，支持拖拽 Agent 节点构建流程图
- **自动布局**: 集成 Dagre 引擎，自动计算节点位置和边的连接
- **图数据转换**: 支持可视化图形与 PSOP JSON 格式之间的双向转换
- **暗色/亮色主题**: 随时切换深色和浅色主题
- **国际化支持**: 支持中文和英文界面
- **节点类型**: 支持开始节点、结束节点、Agent 节点、条件节点等多种节点类型
- **连线控制**: 支持自定义连线样式、条件分支和并行执行路径

### 2. PSOP 工作流管理
- **PSOP 列表**: 查看所有已创建的工作流，支持分页和类型过滤
- **PSOP 详情**: 获取单个工作流的完整定义，包括步骤、任务、Agent 分配等
- **PSOP 保存**: 创建或更新工作流定义，支持自动 ID 生成和时间戳记录
- **Preflow 支持**: 关联用户意图生成的工作流，支持从意图到可执行流程的转换
- **标签管理**: 为工作流添加标签，方便分类和检索

### 3. Agent 编排引擎
- **SolutionPackage 解析**: 解析 AN SolutionPackage 中的流程描述，提取关键信息
- **意图识别**: 根据用户意图自动生成工作流 (Intent-PSOP Generator)
- **PSOP 生成**: 将预定义流程转换为可执行的工作流定义
- **任务分发**: 根据工作流步骤调度和分发任务到各个 Agent
- **条件判断**: 支持 AllSuccess、AnySuccess 等多种执行条件
- **跳转逻辑**: 定义步骤之间的跳转条件和执行顺序

### 4. 执行引擎
- **流程执行**: 驱动编排流程运转，协调各 Agent 之间的协作
- **状态跟踪**: 跟踪任务执行状态 (pending/running/success/failed)
- **持久化**: 保存执行结果和中间状态到本地存储
- **错误处理**: 提供完善的错误处理和重试机制
- **并发控制**: 支持并行任务执行和资源管理

### 5. LLM 集成
- **LLM 调用**: 封装大语言模型调用逻辑，支持多种 LLM 提供商
- **意图理解**: 使用 LLM 理解用户需求并生成工作流
- **提示工程**: 内置优化的提示模板，提高工作流生成质量
- **上下文管理**: 维护对话上下文，支持多轮交互

### 6. Agent Card 管理
- **配置管理**: 集中管理 Agent Card 定义和 LLM 配置
- **技能绑定**: 管理和绑定各 Agent 的可用技能
- **Agent 注册**: 支持动态注册和发现新的 Agent
- **能力描述**: 定义 Agent 的能力范围、输入输出格式

### 7. API 服务
- **RESTful API**: 提供完整的 REST API 接口，支持前端调用
- **文件上传**: 支持 PDF 文件上传和解析
- **工作流规划**: 提交任务和步骤，获取智能规划结果
- **实时状态**: 提供工作流执行状态的实时查询

## 技术架构

### 前端架构
- **React 18**: 现代化的前端框架，支持函数组件和 Hooks
- **Vite**: 快速的构建工具，支持热重载和按需编译
- **React Flow**: 专业的流程图库，提供丰富的节点和连线功能
- **Tailwind CSS**: 实用的 CSS 框架，支持快速样式开发
- **i18next**: 国际化解决方案，支持多语言切换
- **Framer Motion**: 动画库，提供流畅的交互体验

### 后端架构
- **FastAPI**: 高性能的 Python Web 框架，支持异步处理
- **Pydantic**: 数据验证和序列化库，确保数据一致性
- **a2a-sdk**: Agent-to-Agent SDK，提供 Agent 通信基础
- **Loguru**: 日志记录库，提供结构化的日志输出
- **Uvicorn**: ASGI 服务器，支持高并发请求

## 项目结构

```
orchestration-center/
├── workflow-designer/          # 前端工作流设计器
│   ├── src/
│   │   ├── components/orchestration_center/  # 编排中心组件
│   │   ├── components/registry_center/       # 注册中心组件
│   │   ├── locales/                          # 国际化文件
│   │   └── service/                          # API 服务层
│   └── package.json
├── framework/                  # 后端框架
│   ├── server/                # 服务端代码
│   │   ├── frontend_support_server.py  # 前端支持服务器
│   │   └── PSOP_API_DOCUMENTATION.md   # API 文档
│   ├── orchestration/         # 编排引擎
│   │   ├── model/             # 数据模型
│   │   ├── psop_generator.py  # PSOP 生成器
│   │   ├── intent_psop_generator.py  # 意图-PSOP 生成器
│   │   └── persistence.py     # 持久化模块
│   ├── runtime/               # 执行引擎
│   │   └── exec_engine.py     # 执行引擎
│   ├── llm/                   # LLM 集成
│   │   └── llm.py             # LLM 调用封装
│   ├── solution_package/      # SolutionPackage 解析
│   │   ├── parse_flow.py      # 流程解析
│   │   └── manager.py         # 管理器
│   └── agentcard_lib.py       # Agent Card 库
├── config/                    # 配置文件
│   ├── agent_cards/           # Agent Card 定义
│   └── llm_config/            # LLM 配置
├── samples/                   # 示例代码
│   └── run.py                 # 运行示例
└── README.md                  # 项目说明
```

## 快速开始

### 环境要求
- Node.js 18+ 和 Yarn（前端）
- Python 3.8+ 和 pip（后端）

### 启动步骤

1. **启动前端开发服务器**
```bash
cd workflow-designer
yarn install
yarn dev
```
前端将在 http://localhost:5173 启动

2. **启动后端服务器**
```bash
python samples/run.py
```
后端将在 http://localhost:6000 启动

### 访问应用
1. 打开浏览器访问 http://localhost:5173
2. 使用工作流设计器创建和编辑流程图
3. 通过 API 接口管理 PSOP 工作流

## API 文档

详细的 API 文档请参考 `framework/server/PSOP_API_DOCUMENTATION.md`，包含以下主要接口：

- `GET /psops` - 获取 PSOP 列表
- `GET /psops/{workflow_id}` - 获取 PSOP 详情
- `POST /psops` - 保存 PSOP
- `POST /parse-pdf` - 解析 PDF 文件
- `POST /plan` - 获取工作流规划

## 使用场景

### 1. 智能客服系统
- 多个客服 Agent 协同处理用户问题
- 根据问题类型自动路由到合适的专家 Agent
- 记录完整的服务流程和解决方案

### 2. 数据分析流水线
- 数据收集、清洗、分析、可视化 Agent 协同工作
- 自动化数据预处理和特征工程
- 生成分析报告和可视化图表

### 3. 自动化测试
- 测试用例生成、执行、结果分析 Agent 协作
- 自动化回归测试和性能测试
- 生成测试报告和缺陷分析

### 4. 内容创作
- 研究、写作、编辑、校对 Agent 协同创作
- 自动化内容生成和优化
- 多语言内容翻译和本地化

## 开发指南

### 添加新的 Agent
1. 在 `config/agent_cards/` 目录下创建 Agent Card 定义文件
2. 定义 Agent 的能力、技能和配置参数
3. 在前端设计器中添加对应的节点类型
4. 在编排逻辑中集成 Agent 的调用逻辑

### 扩展工作流类型
1. 在 `framework/orchestration/model/` 中定义新的数据模型
2. 实现对应的解析器和生成器
3. 在前端设计器中支持新的节点和连线类型
4. 更新执行引擎以支持新的工作流逻辑

### 集成新的 LLM
1. 在 `config/llm_config/` 中添加 LLM 配置
2. 在 `framework/llm/llm.py` 中实现新的 LLM 适配器
3. 更新提示模板以优化新 LLM 的效果

## 贡献指南

欢迎提交 Issue 和 Pull Request 来改进项目。在提交代码前，请确保：

1. 代码符合项目的编码规范
2. 添加必要的测试用例
3. 更新相关文档
4. 通过现有的测试套件

## 许可证

本项目采用 Apache 2.0 许可证，详情请参阅 LICENSE 文件。

## 联系方式

如有问题或建议，请通过以下方式联系：
- 提交 GitHub Issue
- 查看项目文档
- 参与社区讨论

---

# English Version

## Project Overview

Orchestration Center is a web platform for orchestrating multi-agent collaboration. Users can orchestrate agent call relationships and flowcharts in a visual workflow designer, while the Python backend parses flows, executes orchestration logic, and drives agent collaboration.

## Core Features

### 1. Visual Workflow Designer
- **Drag-and-drop Orchestration**: Visual canvas based on React Flow, supporting drag-and-drop of Agent nodes to build flowcharts
- **Auto Layout**: Integrated Dagre engine for automatic node positioning and edge routing
- **Graph Data Conversion**: Bidirectional conversion between visual graph and PSOP JSON format
- **Dark/Light Theme**: Switch between dark and light themes anytime
- **Internationalization**: Support for Chinese and English interfaces
- **Node Types**: Support for start nodes, end nodes, Agent nodes, condition nodes, and more
- **Connection Control**: Customizable connection styles, conditional branches, and parallel execution paths

### 2. PSOP Workflow Management
- **PSOP List**: View all created workflows with pagination and type filtering
- **PSOP Detail**: Get complete workflow definition including steps, tasks, and agent assignments
- **PSOP Save**: Create or update workflow definitions with auto ID generation and timestamp recording
- **Preflow Support**: Associate with user-intent generated workflows, supporting intent-to-executable flow conversion
- **Tag Management**: Add tags to workflows for easy categorization and retrieval

### 3. Agent Orchestration Engine
- **SolutionPackage Parsing**: Parse flow descriptions from AN SolutionPackage, extracting key information
- **Intent Recognition**: Automatically generate workflows from user intent (Intent-PSOP Generator)
- **PSOP Generation**: Convert predefined flows to executable workflow definitions
- **Task Distribution**: Schedule and distribute tasks to agents based on workflow steps
- **Condition Evaluation**: Support for AllSuccess, AnySuccess, and other execution conditions
- **Jump Logic**: Define jump conditions and execution order between steps

### 4. Execution Engine
- **Flow Execution**: Drive orchestration flow, coordinate collaboration between agents
- **Status Tracking**: Track task execution status (pending/running/success/failed)
- **Persistence**: Save execution results and intermediate states to local storage
- **Error Handling**: Comprehensive error handling and retry mechanisms
- **Concurrency Control**: Support for parallel task execution and resource management

### 5. LLM Integration
- **LLM Calls**: Encapsulate large language model call logic, supporting multiple LLM providers
- **Intent Understanding**: Use LLM to understand user requirements and generate workflows
- **Prompt Engineering**: Built-in optimized prompt templates for better workflow generation quality
- **Context Management**: Maintain conversation context, supporting multi-turn interactions

### 6. Agent Card Management
- **Configuration Management**: Centralized management of Agent Card definitions and LLM configurations
- **Skill Binding**: Manage and bind available skills for each Agent
- **Agent Registration**: Support dynamic registration and discovery of new agents
- **Capability Description**: Define agent capabilities, input/output formats

### 7. API Services
- **RESTful API**: Complete REST API interface supporting frontend calls
- **File Upload**: Support PDF file upload and parsing
- **Workflow Planning**: Submit tasks and steps, get intelligent planning results
- **Real-time Status**: Provide real-time query of workflow execution status

## Technical Architecture

### Frontend Architecture
- **React 18**: Modern frontend framework supporting functional components and Hooks
- **Vite**: Fast build tool supporting hot reload and on-demand compilation
- **React Flow**: Professional flowchart library with rich node and connection functionality
- **Tailwind CSS**: Utility-first CSS framework for rapid styling
- **i18next**: Internationalization solution supporting multi-language switching
- **Framer Motion**: Animation library providing smooth interaction experience

### Backend Architecture
- **FastAPI**: High-performance Python web framework supporting asynchronous processing
- **Pydantic**: Data validation and serialization library ensuring data consistency
- **a2a-sdk**: Agent-to-Agent SDK providing agent communication foundation
- **Loguru**: Logging library providing structured log output
- **Uvicorn**: ASGI server supporting high-concurrency requests

## Project Structure

```
orchestration-center/
├── workflow-designer/          # Frontend workflow designer
│   ├── src/
│   │   ├── components/orchestration_center/  # Orchestration center components
│   │   ├── components/registry_center/       # Registry center components
│   │   ├── locales/                          # Internationalization files
│   │   └── service/                          # API service layer
│   └── package.json
├── framework/                  # Backend framework
│   ├── server/                # Server code
│   │   ├── frontend_support_server.py  # Frontend support server
│   │   └── PSOP_API_DOCUMENTATION.md   # API documentation
│   ├── orchestration/         # Orchestration engine
│   │   ├── model/             # Data models
│   │   ├── psop_generator.py  # PSOP generator
│   │   ├── intent_psop_generator.py  # Intent-PSOP generator
│   │   └── persistence.py     # Persistence module
│   ├── runtime/               # Execution engine
│   │   └── exec_engine.py     # Execution engine
│   ├── llm/                   # LLM integration
│   │   └── llm.py             # LLM call encapsulation
│   ├── solution_package/      # SolutionPackage parsing
│   │   ├── parse_flow.py      # Flow parsing
│   │   └── manager.py         # Manager
│   └── agentcard_lib.py       # Agent Card library
├── config/                    # Configuration files
│   ├── agent_cards/           # Agent Card definitions
│   └── llm_config/            # LLM configurations
├── samples/                   # Sample code
│   └── run.py                 # Run example
└── README.md                  # Project documentation
```

## Quick Start

### Requirements
- Node.js 18+ and Yarn (frontend)
- Python 3.8+ and pip (backend)

### Setup Steps

1. **Start Frontend Development Server**
```bash
cd workflow-designer
yarn install
yarn dev
```
Frontend will start at http://localhost:5173

2. **Start Backend Server**
```bash
python samples/run.py
```
Backend will start at http://localhost:6000

### Access Application
1. Open browser and visit http://localhost:5173
2. Use workflow designer to create and edit flowcharts
3. Manage PSOP workflows through API interfaces

## API Documentation

Detailed API documentation is available in `framework/server/PSOP_API_DOCUMENTATION.md`, including:

- `GET /psops` - Get PSOP list
- `GET /psops/{workflow_id}` - Get PSOP detail
- `POST /psops` - Save PSOP
- `POST /parse-pdf` - Parse PDF file
- `POST /plan` - Get workflow planning

## Use Cases

### 1. Intelligent Customer Service System
- Multiple customer service agents collaborate to handle user issues
- Automatically route to appropriate expert agents based on issue type
- Record complete service process and solutions

### 2. Data Analysis Pipeline
- Data collection, cleaning, analysis, and visualization agents work together
- Automated data preprocessing and feature engineering
- Generate analysis reports and visual charts

### 3. Automated Testing
- Test case generation, execution, and result analysis agents collaborate
- Automated regression testing and performance testing
- Generate test reports and defect analysis

### 4. Content Creation
- Research, writing, editing, and proofreading agents collaborate
- Automated content generation and optimization
- Multi-language content translation and localization

## Development Guide

### Adding New Agents
1. Create Agent Card definition file in `config/agent_cards/` directory
2. Define agent capabilities, skills, and configuration parameters
3. Add corresponding node type in frontend designer
4. Integrate agent call logic in orchestration logic

### Extending Workflow Types
1. Define new data models in `framework/orchestration/model/`
2. Implement corresponding parsers and generators
3. Support new node and connection types in frontend designer
4. Update execution engine to support new workflow logic

### Integrating New LLMs
1. Add LLM configuration in `config/llm_config/`
2. Implement new LLM adapter in `framework/llm/llm.py`
3. Update prompt templates to optimize new LLM effectiveness

## Contribution Guidelines

Welcome to submit Issues and Pull Requests to improve the project. Before submitting code, please ensure:

1. Code follows project coding standards
2. Add necessary test cases
3. Update relevant documentation
4. Pass existing test suite

## License

This project is licensed under the Apache 2.0 License. See LICENSE file for details.

## Contact

For questions or suggestions, please contact:
- Submit GitHub Issue
- Check project documentation
- Participate in community discussions
