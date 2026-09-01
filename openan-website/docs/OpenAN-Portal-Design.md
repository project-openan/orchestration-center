# OpenAN Portal — 统一 Web 框架(可插拔门户)方案文档

> **Issue**: [#77 — Provide a Unified Web Framework (Pluggable Portal)](https://github.com/project-openan/orchestration-center/issues/77)
>
> **版本**: 1.0
> **日期**: 2026-08-26

---

## 1. 背景与目标

### 1.1 现状问题

OpenAN 编排中心(`orchestration-center`)的前端是一个单体 React SPA(`workflow-designer/`),存在以下问题:

| 问题 | 描述 |
|------|------|
| **导航硬编码** | 4 个 tab 按钮(注册中心、编排中心、执行中心、技能中心)写死在 `App.jsx` 和 `Header` 中,新增模块需侵入式修改框架代码 |
| **模块耦合** | 所有业务模块代码在 `src/components/` 下平级排列,无包边界,跨模块 import 混乱 |
| **无法按需裁剪** | 无法针对不同交付场景(如只交付编排中心,不交付注册中心)进行模块裁剪 |
| **扩展困难** | 新增模块(如未来的 Skill Center)需要修改 `App.jsx`、`Header`、`api.js`、`locales` 等多处文件 |
| **后端耦合** | 注册中心是独立服务(`:5000`),但前端 API 调用全部硬编码到编排中心后端(`:5001`)再转发 |
| **i18n 混杂** | 282 个 i18n key 混在两个大文件中,无法按模块拆分 |

### 1.2 目标

建立独立的 OpenAN Web 框架项目(`openan-website`),采用可插拔架构:

1. **独立框架仓库** — Portal Shell 作为独立 npm 包(`@openan/portal` + `@openan/portal-sdk`)发布,不含业务逻辑
2. **插件模型** — 每个子应用(注册中心、编排中心、执行中心等)作为独立插件,声明式注册路由、菜单、i18n
3. **配置驱动** — 通过 `plugins.config.js` 控制启用/禁用哪些插件,实现按需组合
4. **多后端支持** — 每个插件可声明自己的后端 gateway,Portal 自动创建独立 API 实例
5. **运行时管理** — 支持运行时启用/禁用插件,禁用后菜单和路由立即消失
6. **独立开发** — 每个插件支持 standalone 模式,脱离 Portal 独立运行开发

### 1.3 非目标

| 非目标 | 说明 |
|--------|------|
| 不做跨子应用 state 共享 / 事件总线 | 插件间通过后端 API 通信 |
| 不做独立版本管理 | 所有插件与 Portal 统一发布(构建时集成) |
| 不改后端 API 层 | 前端拆分不影响后端代码 |

---

## 2. 整体架构

### 2.1 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                        @openan/portal                        │
│                      (Portal Shell)                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  PortalApp({ pluginsConfig })                           │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────────────────────┐ │  │
│  │  │ Auth     │ │ Theme    │ │ i18n Base + Plugin      │ │  │
│  │  │ Login    │ │ Dark/Light│ │ Namespace Loader        │ │  │
│  │  │ Logout   │ │          │ │                        │ │  │
│  │  └──────────┘ └──────────┘ └────────────────────────┘ │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │ Dynamic Header (从插件 manifest 自动生成导航)    │  │  │
│  │  │ + Plugin Manager (运行时启用/禁用/查看配置)        │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │  │
│  │  │ Plugin A     │ │ Plugin B     │ │ Plugin C     │   │  │
│  │  │ /registry    │ │ /orchestrate │ │ /execution   │   │  │
│  │  │ <Suspense>   │ │ <Suspense>   │ │ <Suspense>   │   │  │
│  │  │ <ErrorBound> │ │ <ErrorBound> │ │ <ErrorBound> │   │  │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘   │  │
│  │         └───────────────┴─────────────────┘            │  │
│  │                 usePortalContext()                      │  │
│  │          (api, auth, theme, i18n, navigate)             │  │
│  └────────────────────────────────────────────────────────┘  │
│                         ↑                                    │
│                @openan/portal-sdk                            │
│         (Plugin Spec, PortalContext, Contracts)              │
└──────────────────────────────────────────────────────────────┘
                          ↑
              Consumer repo plugins.config.js
              (声明启用哪些插件 + 指向后端)
```

### 2.2 数据流

```
用户浏览器 (:3003 — Vite Dev / nginx)
    │
    ├── /api/registry/*  ──→  Registry Backend (:5000)
    │     ↑                        /rest/v1/registry/agent-cards
    │     │                              ↑
    │   registry-center 插件      registry-center 后端服务
    │   (manifest: backend.gateway
    │    = '/api/registry')
    │
    ├── /api/orchestrate/* ──→ Orchestrate Backend (:5001)
    │     ↑                        /rest/v1/orchestrate/workflows
    │     │                        /rest/v1/orchestrate/execute (SSE)
    │     │                        /rest/v1/orchestrate/auth/*
    │     │                              ↑
    │   orchestration-center 插件   orchestrate 后端服务
    │   execution-center 插件       (默认 gateway,无需声明 backend)
    │
    └── (无后端)              demo-showcase 插件 (纯前端)
```

### 2.3 仓库结构

本框架是一个**独立仓库**,不含业务逻辑。消费方仓库(如 `orchestration-center`)安装框架包,只保留自己的业务插件。

```
openan-website/                                    ← 框架仓库(独立)
│
├── packages/                                      ← 共享包 (发布为 npm 包)
│   ├── portal-sdk/          6 files               ← @openan/portal-sdk
│   │   └── src/
│   │       ├── index.js                            库入口
│   │       ├── plugin-context.jsx                  PortalContext + usePortalContext()
│   │       ├── plugin-manifest.js                  PluginManifest 接口 + 校验器
│   │       ├── config-loader.js                    loadEnabledPlugins()
│   │       └── standalone.jsx                      MockPortal (独立开发模式)
│   │
│   └── shared-workflow/     14 files               ← @openan/shared-workflow
│       └── src/                                     UnifiedWorkflow 画布组件
│           ├── index.jsx                            (编排+执行共用)
│           ├── utils/ transformWorkflowToReactFlow
│           └── CustomNodes/ CustomEdges/ toolbar/ ...
│
├── portal/                  20 files               ← @openan/portal
│   └── src/
│       ├── index.js                库入口: export { PortalApp }
│       ├── PortalApp.jsx           可复用壳 (接收 pluginsConfig prop)
│       ├── service/api.js          共享 axios + createApi(gateway)
│       ├── auth/                   AuthContext + Login
│       ├── theme/                  ThemeContext (dark/light)
│       ├── i18n/                   base-en/zh + loadPluginI18n()
│       ├── plugin/registry.jsx     PluginRegistry context
│       └── components/
│           ├── header/             动态导航 + 插件角标
│           ├── plugin_manager/     运行时启用/禁用/查看配置
│           ├── error_boundary/
│           └── common/             pop_confirm, tooltip_component
│
├── plugins/                                      ← 演示用插件 (消费方参考)
│   ├── registry-center/          ← 有独立后端 (:5000)
│   ├── orchestration-center/     ← 默认后端 (:5001)
│   ├── execution-center/        ← 默认后端 (:5001)
│   ├── demo-showcase/           ← 无后端
│   └── hello-portal/            ← Mock 验证插件
│
├── scripts/
│   ├── dev-all.js               ← 一键启动
│   └── mock-backend.mjs          ← 双后端 mock (:5000 + :5001)
│
├── package.json                  ← npm workspaces 根
├── README.md / README_zh.md
└── eslint.config.js
```

### 2.4 发布的包

| 包名 | 导出 | 用途 | peerDependencies |
|------|------|------|-------------------|
| `@openan/portal` | `PortalApp`, `style.css` | 可复用 Portal 壳 — 接收 `pluginsConfig` prop,内部处理 BrowserRouter、Auth、Theme、i18n、动态 Header、路由、错误边界、插件管理 | `react`, `react-dom`, `react-router-dom`, `react-i18next`, `i18next` |
| `@openan/portal-sdk` | `PortalContext`, `usePortalContext`, `PortalProvider`, `validateManifest`, `loadEnabledPlugins`, `MockPortal` | 插件规范 & 共享契约 | `react`, `react-dom` |
| `@openan/shared-workflow` | `UnifiedWorkflow`, `transformWorkflowToReactFlow` | 共享工作流画布组件 | `react`, `react-dom` |

---

## 3. 插件规范 (Plugin Spec)

### 3.1 插件清单格式

每个插件是一个 npm 包,导出 `plugin.manifest.js`:

```js
import { LayoutDashboard } from 'lucide-react';

export default {
    // ── 标识 ──
    id: 'registry-center',                          // 唯一插件 ID
    name: 'Registry Center',                        // 显示名
    version: '1.0.0',                               // 语义版本

    // ── 后端声明 ── (可选,有独立后端的插件声明)
    backend: {
        gateway: '/api/registry',                   // Vite/nginx 代理前缀
        // Portal 会为此插件创建独立的 axios 实例
        // 通过 usePortalContext().api 访问
    },

    // ── 菜单 ── 出现在 Portal 导航栏中
    menu: [{
        id: 'agents',                               // 唯一菜单项 ID
        labelKey: 'registry-center:registry.title',  // i18n key (namespace:key)
        icon: LayoutDashboard,                       // lucide-react 图标
        order: 1,                                   // 导航栏排序
        route: '/registry',                         // 路由路径
        permissions: [],                             // (预留) 权限
    }],

    // ── 路由 ── 注册到 React Router,组件懒加载
    routes: [{
        path: '/registry',                          // 路由路径
        component: () => import('./src/index.jsx'), // 懒加载
        menuId: 'agents',                           // 关联菜单项(高亮)
        permissions: [],                             // (预留) 权限
    }],

    // ── i18n ── 插件专属翻译,独立 namespace
    i18n: {
        namespace: 'registry-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },

    // ── 生命周期钩子 (可选) ──
    onInit: async (ctx) => { /* 注册后调用一次 */ },
    onActivate: () => { /* 插件变为活跃视图时 */ },
    onDeactivate: () => { /* 插件离开活跃视图时 */ },

    // ── 独立模式 (可选) ──
    standalone: {
        enabled: true,
        entry: './src/standalone.jsx',
    },
};
```

### 3.2 PortalContext — 共享服务

插件通过 `usePortalContext()` 访问 Portal 提供的共享服务:

```jsx
import { usePortalContext } from '@openan/portal-sdk';

function MyPlugin() {
    const { api, auth, theme, i18n, navigate } = usePortalContext();
    // ...
}
```

| 服务 | 类型 | 说明 |
|------|------|------|
| `api` | axios 实例 | 配置了 gateway baseURL、120s 超时、`withCredentials: true`、响应拦截器自动解包 `.data`、401 触发 `auth-expired` 事件。每个插件获得自己的实例(根据 `backend.gateway`) |
| `auth` | object | `user`(用户名)、`role`、`isAuthenticated`、`login(username, password)`、`logout()` |
| `theme` | object | `isDark`、`toggle()`、`setDark(boolean)` — 持久化到 localStorage,在 `<html>` 上应用 `dark` class |
| `i18n` | i18next | 使用 `useTranslation('your-namespace')` 访问;Portal 在启动时加载插件 locale |
| `navigate` | function | React Router 的 `navigate(path)` 编程式导航 |
| `router` | object | `{ location, navigate }` — 当前路由信息 |

### 3.3 插件 package.json

```json
{
  "name": "@openan-plugins/registry-center",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "exports": {
    ".": "./src/index.jsx",
    "./plugin.manifest": "./plugin.manifest.js",
    "./plugin.manifest.js": "./plugin.manifest.js"
  },
  "peerDependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0"
  }
}
```

### 3.4 插件配置文件

消费方仓库通过 `plugins.config.js` 声明启用哪些插件:

```js
export default {
    plugins: [
        {
            id: 'registry-center',
            enabled: true,
            manifest: () => import('@openan-plugins/registry-center/plugin.manifest.js'),
        },
        {
            id: 'orchestration-center',
            enabled: true,
            manifest: () => import('@openan-plugins/orchestration-center/plugin.manifest.js'),
        },
        {
            id: 'skill-center',
            enabled: false,  // 禁用 — tree-shake, 永不导入
            manifest: () => import('@openan-plugins/skill-center/plugin.manifest.js'),
        },
    ],
};
```

禁用的插件在构建时被 Vite tree-shake,不会出现在产物中。

---

## 4. Portal Shell 设计

### 4.1 PortalApp 组件

`PortalApp` 是 `@openan/portal` 包的主导出,消费方只需一行:

```jsx
import { PortalApp } from '@openan/portal';
import '@openan/portal/style.css';
import pluginsConfig from './plugins.config.js';

createRoot(document.getElementById('root')).render(
    <PortalApp pluginsConfig={pluginsConfig} />
);
```

### 4.2 PortalApp 内部职责

| 职责 | 实现方式 |
|------|----------|
| **路由** | 内置 `<BrowserRouter>`,从插件 manifest 收集 routes 注册到 `<Routes>` |
| **认证** | `AuthContext` — 启动时调 `/auth/check`,未认证显示 Login 页,401 触发 `auth-expired` 事件 |
| **主题** | `ThemeContext` — dark/light 切换,localStorage 持久化,`<html>` 上 `dark` class |
| **i18n** | 启动时初始化基础翻译 + 按插件 manifest 异步加载各 namespace |
| **动态导航** | `Header` 从已启用插件的 `menu[]` 生成导航按钮,支持运行时增减 |
| **插件管理** | `PluginManager` 弹窗 — 列出全部插件,支持启用/禁用(持久化 localStorage)、查看 manifest JSON |
| **错误隔离** | 每个插件路由包裹 `<ErrorBoundary>` + `<Suspense>`,插件崩溃不影响其他插件 |
| **懒加载** | 每个路由组件通过 `React.lazy()` 懒加载,独立 chunk |
| **API 注入** | 按插件 manifest 的 `backend.gateway` 创建独立 axios 实例,通过 `<PortalProvider>` 注入 |

### 4.3 运行时插件管理

Portal 支持**运行时启用/禁用**插件,无需重新构建:

- 点击 Header 右上角的拼图图标(带角标显示活跃数)打开 Plugin Manager
- 每个插件卡片有 Toggle 开关
- 禁用后:导航栏菜单消失、路由不可访问、自动重定向到第一个可用插件
- 状态持久化到 localStorage,刷新后保持
- 每个插件可展开查看完整 `plugin.manifest.js` JSON 配置

### 4.4 多后端支持

每个有独立后端的插件在 manifest 中声明 `backend.gateway`:

```js
// registry-center 的 manifest
{
    id: 'registry-center',
    backend: { gateway: '/api/registry' },  // ← 声明独立后端
    // ...
}
```

Portal 在渲染插件路由时,根据 `backend.gateway` 调用 `createApi(gateway)` 创建独立 axios 实例,通过 `<PortalProvider value={{ ...portalCtx, api: pluginApi }}>` 注入。

Vite/nginx 配置对应的代理:

```js
// vite.config.js
proxy: {
    '/api/orchestrate': { target: 'http://127.0.0.1:5001', rewrite: ... },
    '/api/registry':    { target: 'http://127.0.0.1:5000', rewrite: ... },
}
```

不需要独立后端的插件(如 demo-showcase)不声明 `backend`,默认用 orchestrate gateway。

---

## 5. 消费方仓库接入

### 5.1 接入步骤

消费方仓库(如 `orchestration-center`)接入 Portal 只需 4 步:

**Step 1: 安装**

```bash
npm install @openan/portal @openan/portal-sdk
npm install react react-dom react-router-dom react-i18next i18next i18next-browser-languagedetector
```

**Step 2: 创建 thin app**

```
your-repo/
├── openan-app/                     ← 薄应用层 (替代旧 workflow-designer)
│   ├── vite.config.js             ← React 插件 + 后端代理
│   ├── index.html
│   ├── tailwind.config.js         ← content 路径含 Portal + 插件源码
│   └── src/
│       ├── main.jsx               ← 4 行
│       └── plugins.config.js      ← 声明插件
├── plugins/                        ← 业务子应用
│   ├── registry-center/
│   ├── orchestration-center/
│   └── ...
└── (后端代码, 不变)
```

**Step 3: main.jsx (4 行)**

```jsx
import { createRoot } from 'react-dom/client';
import { PortalApp } from '@openan/portal';
import '@openan/portal/style.css';
import pluginsConfig from './plugins.config.js';
createRoot(document.getElementById('root')).render(<PortalApp pluginsConfig={pluginsConfig} />);
```

**Step 4: plugins.config.js**

```js
export default {
    plugins: [
        { id: 'registry-center', enabled: true, manifest: () => import('...') },
        { id: 'orchestration-center', enabled: true, manifest: () => import('...') },
    ],
};
```

### 5.2 Tailwind 配置

消费方 `tailwind.config.js` 必须包含 Portal 源码路径:

```js
content: [
    './src/**/*.{js,jsx}',
    './plugins/*/src/**/*.{js,jsx}',
    './node_modules/@openan/portal/src/**/*.{js,jsx}',  // ← 关键
],
```

### 5.3 Vite 代理配置

```js
proxy: {
    '/api/orchestrate': { target: 'http://127.0.0.1:5001', rewrite: (p) => p.replace(/^\/api\/orchestrate/, '') },
    '/api/registry':    { target: 'http://127.0.0.1:5000', rewrite: (p) => p.replace(/^\/api\/registry/, '') },
},
```

---

## 6. 迁移方案

### 6.1 迁移影响总览

从单体 `workflow-designer/` 迁移到 Portal 插件架构:

| 维度 | 影响 |
|------|------|
| **用户可见行为** | 零 — 同样的 UI、同样的功能 |
| **后端 API** | 零 — 后端不变 |
| **组件业务逻辑** | 零 — state/effect/数据处理不变 |
| **组件 prop 来源** | 微调 — `isDark`/`t` 从 props → context hooks (每模块 2-3 行) |
| **API 调用路径** | 微调 — import 路径变,函数签名不变 |
| **i18n key** | 中 — 282 个 key 拆分到 5 个 locale 文件,namespace 变化 |
| **跨模块依赖** | 需处理 — 提取 shared-workflow 共享包 |
| **文件位置** | 变化 — `components/` → `plugins/*/src/` |
| **路由** | 改善 — 从 state tab 变为 URL 路由,可分享/书签 |
| **构建** | 变化 — 从单项目变为 monorepo workspace |

### 6.2 迁移步骤(以 registry-center 为例)

| 步骤 | 改动 | 工作量 |
|------|------|--------|
| **1. 建插件目录** | `plugins/registry-center/` + `package.json` + `plugin.manifest.js` | 新建文件 |
| **2. 搬组件代码** | `components/registry_center/*` → `plugins/registry-center/src/*` | 文件移动 |
| **3. 改组件签名** | `({ isDark, t })` → `() + usePortalContext() + useTranslation('namespace')` | 2-3 行 |
| **4. 改 API 调用** | `import { getAgentCards } from "@/service/api.js"` → `api.get('/rest/v1/registry/agent-cards')` | import 路径 |
| **5. 声明后端** | manifest 加 `backend: { gateway: '/api/registry' }` | 1 行 |
| **6. 拆 i18n** | 从 `locales/en.json` 提取 `registry.*` + `agent_profile.*` → 插件 locale | 按组拆分 |
| **7. 注册插件** | `plugins.config.js` 加一行 | 1 行 |

**子组件零改动** — `isDark` 仍是父组件 prop 传入,子组件代码不变。

### 6.3 实际改动量(以 registry-center 为例)

```
原始文件: index.jsx (395 行)
改动行数: 5 处, 约 8 行

  1. 去掉 import { getAgentCards } from "@/service/api.js"
  2. 加   import { usePortalContext } from '@openan/portal-sdk'
  3. 签名 ({ isDark, t }) → () + 3 行 hook
  4. API  getAgentCards() → api.get('/rest/v1/registry/agent-cards')
  5. 新增 plugin.manifest.js (43 行声明文件)

业务逻辑: 395 行 → 395 行 (不变)
```

### 6.4 跨模块依赖处理

执行中心原来硬依赖编排中心的工作流组件:

```jsx
// 迁移前
import { transformWorkflowToReactFlow } from '@/components/orchestration_center/workflow/utils';
import UnifiedWorkflow from '../orchestration_center/workflow/index.jsx';
```

**解决方案**: 提取为 `@openan/shared-workflow` 共享包,两个插件都依赖:

```jsx
// 迁移后
import { transformWorkflowToReactFlow, UnifiedWorkflow } from '@openan/shared-workflow';
```

### 6.5 API 函数分配

| 函数 | 使用方 | 迁入位置 |
|------|--------|----------|
| `authCheck`, `login`, `logout` | Portal Shell | `@openan/portal` (已内置) |
| `getAgentCards` | registry-center | 插件内 `api.get('/rest/v1/registry/agent-cards')` |
| `getWorkflows`, `parsePdf`, `handlePlan`, ... | orchestration-center | 插件内 `api.get('/rest/v1/orchestrate/...')` |
| `matchWorkflows`, `getStartProcessStreamUrl`, ... | execution-center | 插件内 |
| `createWorkflow` | shared-workflow (toolbar) | `@/service/api.js` (Portal 提供) |

### 6.6 i18n Key 分配(282 keys)

| Key 组 | 数量 | 目标 |
|--------|------|------|
| `nav`, `login`, `common`, `settings`, `error`, `error_boundary` | 48 | `@openan/portal` 基座 |
| `registry`, `agent_profile` | 43 | `plugins/registry-center/src/locales/` |
| `orchestration`, `workflow`, `workflow_empty`, `node_label` | 76 | `plugins/orchestration-center/src/locales/` |
| `execution` | 91 | `plugins/execution-center/src/locales/` |
| `skills` | 22 | `plugins/skill-center/src/locales/` (未来) |

---

## 7. 设计决策

### 7.1 构建时集成 vs 运行时集成

**选择**: 构建时集成(workspace aliases + 动态 import)

**理由**: Issue #77 明确"所有子应用统一发布"。禁用插件通过 `plugins.config.js` 中的动态 `import()` 控制,Vite 在生产构建时 tree-shake。未来可演进到 Module Federation 实现运行时加载。

### 7.2 路由驱动 vs 状态驱动

**选择**: 路由驱动(React Router)

**理由**: 迁移前用 `activeTab` state 切换,URL 始终 `/`。迁移后用 URL 路由(`/registry`, `/orchestration`),URL 可分享、可收藏。

### 7.3 插件隔离

**选择**: 通过后端 API 隔离,不共享前端 state

**理由**: 符合 Issue #77 非目标"不做跨子应用 state 共享 / 事件总线"。插件间通信通过后端 API。

### 7.4 多后端架构

**选择**: 每个插件在 manifest 声明 `backend.gateway`,Portal 创建独立 axios 实例

**理由**: 注册中心是独立服务(`:5000`),不应通过编排中心(`:5001`)转发。每个插件直连自己的后端。

### 7.5 peerDependencies

**选择**: React 等声明为 `peerDependencies`

**理由**: 消费方提供单一 React 实例,防止因 React 重复导致 hooks 崩溃。

### 7.6 运行时插件管理

**选择**: localStorage 持久化禁用状态,不重新构建

**理由**: 运维场景需要临时禁用某插件(如某插件故障),不需要重新部署。状态持久化到 localStorage,刷新后保持。

---

## 8. 部署方案

### 8.1 开发环境

```bash
# 框架仓库 (开发 Portal 本身)
cd openan-website
npm install
npm run dev                    # Vite :3003 + mock-backend (:5000 + :5001)

# 消费方仓库 (开发业务插件)
cd your-repo
npm link @openan/portal @openan/portal-sdk   # 链接到本地框架
npm run dev                    # Vite :3003 + 真实后端
```

### 8.2 生产部署

```dockerfile
# Dockerfile (消费方)
FROM node:20-slim AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build              # Vite 构建 → dist/

FROM nginx:1.27-alpine
COPY --from=builder /app/openan-app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
ENV BACKEND_HOST=orchestration-center
ENV BACKEND_PORT=5001
ENV REGISTRY_HOST=registry-center
ENV REGISTRY_PORT=5000
EXPOSE 80
```

```nginx
# nginx.conf.template — 多后端代理
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    location / { try_files $uri $uri/ /index.html; }

    # Registry backend
    location /api/registry/ {
        proxy_pass ${REGISTRY_SCHEME}://${REGISTRY_HOST}:${REGISTRY_PORT}/;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }

    # Orchestrate backend
    location /api/orchestrate/ {
        proxy_pass ${BACKEND_SCHEME}://${BACKEND_HOST}:${BACKEND_PORT}/;
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

### 8.3 docker-compose

```yaml
services:
  orchestration-center:
    build: .
    ports: ["127.0.0.1:5001:5001"]
    environment:
      - AGENT_REGISTRY_URL=https://openan-registry-center:5000
    networks: [openan-net]

  registry-center:
    build: ./registry-center
    ports: ["127.0.0.1:5000:5000"]
    networks: [openan-net]

  portal:
    build: ./openan-app
    ports: ["3003:80"]
    environment:
      - BACKEND_HOST=orchestration-center
      - BACKEND_PORT=5001
      - REGISTRY_HOST=registry-center
      - REGISTRY_PORT=5000
    depends_on: [orchestration-center, registry-center]
    networks: [openan-net]
```

---

## 9. 验证结果

### 9.1 构建验证

```
npm install    ✓  400+ packages installed
npm run build  ✓  1838 modules transformed, ~1s
npm run lint   ✓  0 errors (warnings are JSX false positives)
npm run dev    ✓  Vite ready at http://localhost:3003 in ~280ms
```

构建产物展示了插件架构正常工作:
- `plugin.manifest-*.js` — 插件 manifest 独立 chunk(动态加载)
- `src-*.js` — 插件组件懒加载 chunk
- `en-*.js`, `zh-*.js` — 插件 i18n locale 按需 chunk
- `index-*.js` — Portal 主 bundle

### 9.2 功能验证

| 功能 | 状态 | 验证方式 |
|------|------|----------|
| Portal Shell 加载 | ✅ | http://localhost:3003 显示暗色主题页面 |
| 动态导航栏 | ✅ | 4 个插件按钮从 manifest 自动生成 |
| 路由驱动 | ✅ | `/registry`, `/orchestration`, `/execution`, `/demos` URL 可直接访问 |
| 认证门控 | ✅ | `auth_required: false` 时自动跳过登录 |
| 主题切换 | ✅ | 右上角太阳/月亮按钮实时切换 |
| 语言切换 | ✅ | 中/EN 按钮实时切换翻译 |
| 插件懒加载 | ✅ | 每个路由独立 chunk,Suspense fallback 显示 Loading |
| 错误隔离 | ✅ | ErrorBoundary 包裹每个插件路由 |
| 插件管理 | ✅ | 运行时启用/禁用,导航栏实时增减,localStorage 持久化 |
| 配置查看 | ✅ | Plugin Manager 展开查看 manifest JSON |
| 多后端代理 | ✅ | `/api/registry` → :5000, `/api/orchestrate` → :5001 |
| 插件 i18n | ✅ | 每个插件独立 namespace,按需加载 locale |

### 9.3 代码统计

| 部分 | 文件数 | 说明 |
|------|--------|------|
| Portal SDK (插件规范) | 6 | `@openan/portal-sdk` |
| Shared Workflow (共享组件) | 14 | `@openan/shared-workflow` |
| Portal Shell (框架壳) | 20 | `@openan/portal` |
| Registry Center 插件 | 5 | 有独立后端 |
| Orchestration Center 插件 | 4 | 默认后端 |
| Execution Center 插件 | 5 | 默认后端 |
| Demo Showcase 插件 | 10 | 无后端,7 个 Demo |
| Hello Portal (mock) | 4 | 框架验证用 |
| **合计** | **68** | (原 workflow-designer: 40 文件单体) |

---

## 10. Issue #77 合规性

| 目标 | 状态 | 实现 |
|------|------|------|
| 独立的 `openan-website` 前端框架项目 | ✅ | 独立仓库,可发布为 npm 包 |
| 可插拔架构: 导航、认证、主题、i18n、插件注册 | ✅ | PortalApp 内置全部能力 |
| 插件集成规范(路由、菜单、权限) | ✅ | `plugin.manifest.js` 声明式 |
| 每个子应用作为独立插件 | ✅ | registry-center, orchestration-center, execution-center |
| 配置文件实现按需组合 | ✅ | `plugins.config.js` + 运行时启用/禁用 |
| 为未来扩展(Skill Center)提供标准规范 | ✅ | 写 manifest + 注册即可 |
| 每个子项目支持独立运行模式 | ✅ | `MockPortal` standalone 模式 |
| 一键启动开发脚本 | ✅ | `scripts/dev-all.js` + `mock-backend.mjs` |

| 非目标 | 合规 | 说明 |
|--------|------|------|
| 不做跨子应用 state 共享 / 事件总线 | ✅ | 插件通过后端 API 通信 |
| 不做独立版本管理 | ✅ | 构建时集成,统一发布 |
| 不改后端 API 层 | ✅ | 后端完全不变 |

---

## 11. 未来演进

| 方向 | 当前 | 未来 |
|------|------|------|
| 插件加载 | 构建时(workspace aliases + 动态 import) | Module Federation 运行时加载,无需重新构建 |
| 版本管理 | 统一发布 | 插件独立版本,支持灰度 |
| 插件市场 | 手动注册 | `create-openan-app` CLI 脚手架 + 插件模板 |
| 权限 | manifest 预留 `permissions` 字段 | 按角色/权限动态显示/隐藏插件菜单 |
| 跨插件通信 | 后端 API | 可选的事件总线(shared state for read-only data) |
| 微前端 | 构建时打包 | 支持远程插件(独立部署 + 运行时加载) |
