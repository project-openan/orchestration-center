# OpenAN Portal 统一 Web 框架 — 可分可合的可插拔门户

---

## 第 1 页 · 封面

# OpenAN Portal
## 统一 Web 框架 — 可插拔门户架构

**一个框架壳 × N 个业务插件 = 可分可合的 OpenAN 前端**

Issue #77 · Provide a Unified Web Framework (Pluggable Portal)

2026-08

---

## 第 2 页 · 一句话讲清楚方案

## 核心理念：框架是壳，业务是插件

```
┌─────────────────────────────────────────────────────────┐
│                 OpenAN Portal (框架壳)                    │
│                                                         │
│   导航栏   认证   主题   国际化   插件管理器   路由        │
│                                                         │
│   ┌───────────┐ ┌───────────┐ ┌───────────┐            │
│   │ 注册中心   │ │ 编排中心   │ │ 执行中心   │  ← 插件    │
│   │ 插件       │ │ 插件       │ │ 插件       │            │
│   └───────────┘ └───────────┘ └───────────┘            │
└─────────────────────────────────────────────────────────┘
```

**Portal 只提供骨架，不含任何业务逻辑**

**任意 Web 页面 → 写一个 manifest → 注册进 Portal → 集成完成**

---

## 第 3 页 · 可分可合的架构逻辑

## 分与合，由配置决定

### 合 — 统一门户模式

所有插件注册到同一个 Portal，统一导航、统一登录、统一主题

```
Portal (:3003)
 ├── /registry      注册中心插件
 ├── /orchestrate   编排中心插件
 ├── /execution     执行中心插件
 └── /demos         Demo 插件
```

### 分 — 独立运行模式

每个插件是一个独立 npm 包，可以脱离 Portal 单独运行

```
registry-center 独立运行 → 自带 MockPortal 包装，直接 dev
orchestration-center 独立运行 → 同上
```

### 关键机制

| 能力 | 实现方式 |
|------|----------|
| 合：统一集成 | `plugins.config.js` 声明启用哪些插件 |
| 分：独立运行 | 每个插件有 `standalone.jsx` + `MockPortal` |
| 合：共享服务 | `usePortalContext()` 获取 api/auth/theme/i18n |
| 分：互不依赖 | 插件间不共享 state，通过各自后端 API 通信 |

---

## 第 4 页 · 如何集成一个已有 Web 服务

## 3 步完成集成，业务逻辑零修改，Portal 代码零改动

以**注册中心**为例（原有 395 行组件代码）：

### 第 1 步：建插件目录 + 写清单 `plugin.manifest.js`

声明"我是谁、菜单长什么样、路由是什么、有哪些翻译、后端在哪"

```
plugins/
└── my-service/                  ← 丢进这个目录即自动注册
    ├── package.json
    ├── plugin.manifest.js
    └── src/
        ├── index.jsx            ← 你的页面组件（原样搬过来）
        └── locales/
```

```js
export default {
    id: 'registry-center',
    name: 'Registry Center',
    version: '0.1.0',
    backend: { gateway: '/api/registry' },   // 声明自己的后端
    menu: [{ id: 'agents', labelKey: 'registry-center:registry.title',
             icon: LayoutDashboard, order: 1, route: '/registry' }],
    routes: [{ path: '/registry',
               component: () => import('./src/index.jsx') }],
    i18n: { namespace: 'registry-center', resources: {...} },
};
```

### 第 2 步：改组件签名（2 行，改在插件自己的代码里）

```jsx
// 之前：从 App.jsx 接 props
const AgentRegistry = ({ isDark, t }) => { ... }

// 之后：从 PortalContext 获取
const AgentRegistry = () => {
    const { theme, api } = usePortalContext();      // ← 加这行
    const { t } = useTranslation('registry-center'); // ← 加这行
    const isDark = theme.isDark;
    // 以下 395 行业务逻辑、UI、CSS 全部不变
};
```

### 第 3 步：改 API 调用（1 行，改在插件自己的代码里）

```jsx
// 之前：import { getAgentCards } from "@/service/api.js"
const response = await api.get('/rest/v1/registry/agent-cards');
```

**完成。不需要注册、不需要改任何 Portal 代码。**

### 改动边界：谁改什么

第 2、3 步的所有改动都发生在**插件自己的文件**里（如 `plugins/registry-center/src/index.jsx`），
由插件开发者自己完成，不需要了解 Portal 内部实现：

```
Portal (框架, 永不改动)              各业务插件 (各自改各自的)
┌──────────────────────┐            ┌───────────────────────────┐
│ PortalApp.jsx        │            │ plugins/registry-center/  │
│ Header / Login       │            │   └── src/index.jsx       │
│ ThemeContext         │  提供 hook  │     ↓ 注册中心开发者改这里 │
│ AuthContext          │ ────────→  │     1. 组件签名 props→hook │
│ api.js + createApi() │            │     2. API 调用路径        │
│ plugin-discovery     │            │     3. 自己的 locales/     │
└──────────────────────┘            └───────────────────────────┘
      提供 usePortalContext()              消费 usePortalContext()
```

| 改动点 | 在哪里改 | 谁来改 |
|--------|----------|--------|
| 写 `plugin.manifest.js` | 插件目录 | 插件开发者 |
| 组件签名 props → hooks | 插件 `src/index.jsx` | 插件开发者 |
| API 调用路径 | 插件 `src/index.jsx` | 插件开发者 |
| i18n locale 文件 | 插件 `src/locales/` | 插件开发者 |
| 插件注册 | `plugins/` 目录（丢文件夹即自动发现） | 无需任何人 |
| Portal 框架代码 | — | **无人改动** |

注册中心改 `plugins/registry-center/src/index.jsx`，编排中心改 `plugins/orchestration-center/src/index.jsx` —— 各自独立、互不影响。

### 约定式自动发现（零配置注册）

Portal 内置 `openan-plugin-discovery` Vite 插件：

```
启动/构建时 → fs 扫描 plugins/*/plugin.manifest.js
           → 生成虚拟模块 virtual:openan-plugins
           → 禁用的插件连 import 都不生成（真正 tree-shake）
           → dev 运行中丢入新文件夹 → 自动热重载识别
```

| 场景 | 操作 | 改 Portal 代码？ |
|------|------|----------------|
| 新增插件 | 插件文件夹丢进 `plugins/` | ❌ |
| 交付裁剪 | 编辑 `plugins/plugin-overrides.json`（纯 JSON，运维可改） | ❌ |
| 运行时禁用 | Plugin Manager 界面点开关 | ❌ |
| 删除插件 | 删除文件夹 | ❌ |

### 迁移结果

| 维度 | 变化 |
|------|------|
| 改动行数 | **3 处，约 5 行** |
| Portal 代码改动 | **零** |
| 业务逻辑 | **零修改** |
| UI/UX | **零修改** |
| 子组件 | **零修改**（isDark 仍由父组件传） |

---

## 第 5 页 · 插件定义规范

## 一个插件 = 一个 npm 包 = 一个 manifest

### manifest 声明字段

```js
export default {
    // ── 标识 ──
    id: 'registry-center',              // 唯一 ID
    name: 'Registry Center',            // 显示名
    version: '0.1.0',                   // 语义版本

    // ── 后端声明（可选）──
    backend: { gateway: '/api/registry' },
    // Portal 为此插件创建独立 axios 实例
    // 通过 usePortalContext().api 访问

    // ── 菜单 ── 导航栏自动生成按钮
    menu: [{
        id: 'agents',
        labelKey: 'registry-center:registry.title',  // i18n key
        icon: LayoutDashboard,          // 导航图标
        order: 1,                       // 导航排序
        route: '/registry',             // 路由路径
    }],

    // ── 路由 ── 自动注册到 React Router
    routes: [{
        path: '/registry',
        component: () => import('./src/index.jsx'),  // 懒加载
        menuId: 'agents',
    }],

    // ── 国际化 ── 独立 namespace，避免 key 冲突
    i18n: {
        namespace: 'registry-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },

    // ── 独立运行（可选）──
    standalone: { enabled: true, entry: './src/standalone.jsx' },
};
```

### PortalContext — 插件获得的框架服务

| 服务 | 类型 | 说明 |
|------|------|------|
| `api` | axios 实例 | 按插件 backend.gateway 创建，自动带 cookie |
| `auth` | object | 用户、角色、认证状态、登录/登出 |
| `theme` | object | 暗色/亮色切换 |
| `i18n` | i18next | 插件用独立 namespace |
| `navigate` | function | 编程式导航 |

---

## 第 6 页 · 插件加载运行流程

## 从启动到渲染的完整链路

```
Vite 启动/构建时
     │
     ▼
① 插件自动发现（openan-plugin-discovery）
   ├── fs 扫描 plugins/*/plugin.manifest.js
   ├── 读取 plugin-overrides.json 过滤禁用项
   ├── 生成虚拟模块 virtual:openan-plugins
   │   （禁用插件连 import 都不生成 → 真正 tree-shake）
   │
     ▼
浏览器加载 Portal (:3003)
     │
     ▼
② PortalApp 启动
   ├── 初始化 i18n 基座
   ├── 认证检查 (/auth/check)
     │
     ▼
③ 加载插件清单
   ├── 导入虚拟模块（自动发现的插件列表）
   ├── 动态 import() 每个 manifest
   ├── validateManifest() 校验字段
     │
     ▼
④ 加载插件 i18n
   ├── 读取 manifest.i18n.resources
   ├── 按需加载 en.json / zh.json
   ├── 注册到独立 namespace
     │
     ▼
⑤ 组装 PortalContext
   ├── 检查 manifest.backend.gateway
   ├── 有 → createApi(gateway) 创建独立 axios
   ├── 无 → 用默认 API 实例
     │
     ▼
⑥ 渲染 Portal Shell
   ├── Header 从 manifest.menu[] 生成导航按钮
   ├── 路由从 manifest.routes[] 注册到 React Router
   ├── 每个路由包裹 PortalProvider + ErrorBoundary + Suspense
     │
     ▼
⑦ 懒加载插件组件
   ├── 用户点击导航 → React.lazy() 触发 import()
   ├── 插件组件独立 chunk 按需加载
   ├── 组件内 usePortalContext() 获取共享服务
   └── 插件崩溃只影响自己（ErrorBoundary 隔离）
```

### 禁用插件的加载逻辑

```
plugin-overrides.json 中 "enabled": false
     │
     ▼
自动发现阶段直接跳过（不生成 import）
     │
     ▼
生产构建中被完全 tree-shake
     │
     ▼
产物中完全不存在该插件代码
```

---

## 第 7 页 · 代码目录结构

## 框架仓库 openan-website/

```
openan-website/                          ← 框架仓库（独立）
│
├── packages/                            ← 共享包
│   ├── portal-sdk/          6 files     ← @openan/portal-sdk
│   │   └── src/
│   │       ├── index.js                 库入口
│   │       ├── plugin-context.jsx       PortalContext + usePortalContext
│   │       ├── plugin-manifest.js       manifest 接口 + 校验器
│   │       ├── config-loader.js         loadEnabledPlugins()
│   │       └── standalone.jsx           MockPortal（独立运行用）
│   │
│   └── shared-workflow/     14 files    ← @openan/shared-workflow
│       └── src/                         UnifiedWorkflow 画布
│           ├── index.jsx                （编排+执行共用）
│           ├── utils/                   transformWorkflowToReactFlow
│           └── CustomNodes/ toolbar/ sidebar/ ...
│
├── portal/                  20 files    ← @openan/portal (框架壳)
│   ├── vite.config.js                   Vite 配置 + 多后端代理
│   ├── tailwind.config.js               content 含全部插件源码
│   └── src/
│       ├── index.js                     库入口: export { PortalApp }
│       ├── PortalApp.jsx                可复用壳（接收 pluginsConfig）
│       ├── plugins.config.js            插件启用/禁用配置 ★
│       ├── auth/                        AuthContext + Login
│       ├── theme/                       ThemeContext
│       ├── i18n/                        基础翻译 + 插件 namespace 加载
│       ├── service/api.js               共享 axios + createApi(gateway)
│       └── components/
│           ├── header/                  动态导航（从 manifest 生成）
│           ├── plugin_manager/           运行时启用/禁用/查看配置
│           └── error_boundary/           插件级错误隔离
│
├── plugins/                            ← 业务插件 ★
│   ├── registry-center/     5 files     ← 有独立后端 (:5000)
│   ├── orchestration-center/ 4 files    ← 默认后端 (:5001)
│   ├── execution-center/    5 files     ← 默认后端 (:5001)
│   ├── demo-showcase/       10 files    ← 无后端 Demo
│   └── hello-portal/        4 files     ← 框架验证 Mock
│
├── scripts/
│   ├── dev-all.js                       一键启动
│   └── mock-backend.mjs                 双后端 Mock (:5000 + :5001)
│
├── docs/                               方案文档
├── README.md / README_zh.md            中英文文档
└── package.json                         npm workspaces 根
```

---

## 第 8 页 · 业务插件目录结构

## 注册中心插件（有独立后端）

```
plugins/registry-center/
├── package.json                  ← @openan-plugins/registry-center
│                                    exports: ./plugin.manifest.js
├── plugin.manifest.js            ← 插件声明 ★ 核心
│                                    id / menu / routes / i18n / backend
├── vite.config.js                ← 独立构建配置（可独立部署）
├── tsconfig.json
├── index.html                    ← 独立运行入口
└── src/
    ├── index.jsx                 ← 主组件（usePortalContext）
    ├── standalone.jsx            ← 独立运行入口（MockPortal 包装）
    ├── agentcard_visualization/  ← AgentCard 详情组件
    ├── code_inspector/           ← JSON 查看器
    └── locales/
        ├── en.json               ← 插件专属翻译
        └── zh.json
```

## 编排中心插件（默认后端）

```
plugins/orchestration-center/
├── package.json                  ← @openan-plugins/orchestration-center
├── plugin.manifest.js            ← 声明 menu/routes/i18n（无 backend）
├── vite.config.js
└── src/
    ├── index.jsx                 ← 主组件
    ├── standalone.jsx            ← 独立运行入口
    ├── packages/                 ← SolutionPackage 上传
    └── locales/
        ├── en.json
        └── zh.json

依赖：@openan/shared-workflow      ← 共享工作流画布
                                    （与执行中心共用，不重复实现）
```

## 插件目录共性

| 文件 | 必须 | 作用 |
|------|------|------|
| `plugin.manifest.js` | ✅ | 声明菜单、路由、i18n、后端 |
| `src/index.jsx` | ✅ | 插件主组件 |
| `src/locales/*.json` | ✅ | 插件专属翻译 |
| `src/standalone.jsx` | 可选 | 脱离 Portal 独立运行 |
| `vite.config.js` | 可选 | 独立构建（可独立部署） |

---

## 第 9 页 · 多后端与部署

## 每个插件可直连自己的后端

```
浏览器 (:3003)
    │
    ├── /api/registry/*    →  注册中心后端 (:5000)   ← registry-center 插件
    │                          /rest/v1/registry/agent-cards
    │
    ├── /api/orchestrate/* →  编排中心后端 (:5001)   ← orchestration/execution 插件
    │                          /rest/v1/orchestrate/workflows
    │                          /rest/v1/orchestrate/execute (SSE)
    │
    └── (无后端)            →  demo-showcase 插件
```

## 生产部署（docker-compose）

```yaml
services:
  portal:                        # 框架壳
    build: ./openan-website/portal
    ports: ["3003:80"]
    environment:
      - REGISTRY_URL=http://registry-center:5000
      - BACKEND_URL=http://orchestration-center:5001

  orchestration-center:          # 编排中心（后端 + 插件）
    build: ./orchestration-center
    ports: ["5001:5001"]

  registry-center:               # 注册中心（独立服务）
    build: ./registry-center
    ports: ["5000:5000"]
```

## 独立部署演进路径

| 阶段 | 集成方式 | 插件部署方式 |
|------|----------|--------------|
| **当前** | 构建时集成（workspace） | 与 Portal 一起构建，统一发布 |
| **近期** | 独立构建 + nginx 分发 | 各自构建、各自部署、各自版本 |
| **远期** | Module Federation | 运行时远程加载，Portal 无需重建 |

---

## 第 10 页 · 演进路线与价值总结

## 已验证成果

| 验证项 | 结果 |
|--------|------|
| 框架构建 | ✅ 1838 modules, ~1s |
| 4 插件全部加载 | ✅ 动态导航 + 路由 + i18n |
| 插件独立运行 | ✅ MockPortal standalone 模式 |
| 运行时启用/禁用 | ✅ localStorage 持久化 |
| 多后端代理 | ✅ /api/registry + /api/orchestrate |
| 迁移成本 | ✅ 每插件仅改 5 处，业务零修改 |
| 代码量 | 68 文件（原单体 40 文件，结构清晰） |

## 核心价值

**可分** — 每个插件是独立 npm 包，可独立开发、独立运行、独立构建、独立部署

**可合** — 插件丢进目录即自动注册，共享导航、认证、主题、国际化，Portal 代码零改动

**可扩展** — 未来 Skill Center 只需写一个 manifest + 改组件签名 2 行，丢进目录完成集成

**可裁剪** — `plugin-overrides.json` 设 `"enabled": false`（纯 JSON），构建时自动 tree-shake

## 下一步

1. 完成 Skill Center 插件迁移（复用规范，预计半天）
2. Docker 化全栈部署验证
3. 发布 `@openan/portal` 到 npm，供外部消费方接入
4. 探索独立构建 + Module Federation 运行时加载
