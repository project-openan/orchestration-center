# OpenAN Website — 统一 Web 框架(可插拔 Portal)

[English](./README.md) | [中文](./README_zh.md)

> **Issue**: [#77 — Provide a Unified Web Framework (Pluggable Portal)](https://github.com/project-openan/orchestration-center/issues/77)

一个独立、可复用的前端框架。它提供 Portal 壳(导航、认证、主题、国际化、路由),
任意 Web 页面都可以作为**插件**集成进来 —— 写一个 `plugin.manifest.js`,
在 `plugins.config.js` 里加一行,页面就出现在 Portal 中。

## 工作原理

```
┌──────────────────────────────────────────────────────────┐
│                     @openan/portal                        │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│ │  Portal 壳 (PortalApp)                              │  │
│ │                                                     │  │
│ │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │  │
│ │  │ 认证     │  │ 主题     │  │ i18n 基座         │ │  │
│ │  │ 登录/登出 │  │ 暗色/亮色│  │ + 插件加载器      │  │
│ │  └──────────┘  └──────────┘  └──────────────────┘ │  │
│ │                                                     │  │
│ │  ┌────────────────────────────────────────────────┐ │  │
│ │  │ 动态导航栏 (从插件清单生成菜单按钮)            │ │  │
│ │  └────────────────────────────────────────────────┘ │  │
│ │                                                     │  │
│ │  ┌─────────────────┐ ┌─────────────────┐            │  │
│ │  │ 插件 A (路由)     │ │ 插件 B (路由)    │ ...        │  │
│ │  │ <Suspense+Error>│ │ <Suspense+Error>│            │  │
│ │  └─────────────────┘ └─────────────────┘            │  │
│ │          ↑               ↑                            │  │
│ │          └───────────────┴── usePortalContext()      │  │
│ │             (api, auth, theme, i18n, navigate)        │  │
│ └─────────────────────────────────────────────────────┘  │
│                         ↑                                │
│                @openan/portal-sdk                         │
│         (插件规范, PortalContext, 契约)                    │
└──────────────────────────────────────────────────────────┘
                          ↑
              消费方仓库 plugins.config.js
              (声明加载哪些插件)
```

**核心理念**: 框架是一个不含业务逻辑的壳。消费方仓库安装框架,把自己的
Web 页面写成插件(每个插件带一个清单文件,声明菜单按钮、路由、i18n),通过
`plugins.config.js` 注册。Portal 自动生成导航、处理认证/主题/国际化、用懒加载
和错误边界渲染插件路由。

## 发布的包

| 包名 | 导出 | 用途 |
|------|------|------|
| `@openan/portal` | `PortalApp`, `style.css` | 可复用 Portal 壳 —— 接收 `pluginsConfig` prop,内部处理 BrowserRouter、认证、主题、i18n、动态 Header、路由、错误边界 |
| `@openan/portal-sdk` | `PortalContext`, `usePortalContext`, `PortalProvider`, `validateManifest`, `loadEnabledPlugins`, `MockPortal` | 插件规范 & 共享契约 —— 插件通过 `usePortalContext()` 访问框架服务 |

**Peer dependencies**(消费方需自行安装):
`react`, `react-dom`, `react-router-dom`, `react-i18next`, `i18next`,
`i18next-browser-languagedetector`

## 仓库结构

```
openan-website/                             ← 本仓库(仅框架)
├── package.json                            ← npm workspaces 根
├── eslint.config.js
├── scripts/
│   └── dev-all.js                          ← 一键启动
│
├── packages/
│   └── portal-sdk/                         ← @openan/portal-sdk
│       ├── package.json
│       └── src/
│           ├── index.js                    ← 公开 API 再导出
│           ├── plugin-manifest.js          ← PluginManifest 接口 + 校验器
│           ├── plugin-context.jsx          ← PortalContext (React Context) + usePortalContext()
│           ├── plugin-context.js           ← .js 垫片再导出(无 JSX)
│           ├── config-loader.js            ← loadEnabledPlugins() — 异步, 禁用插件被 tree-shake
│           └── standalone.jsx              ← MockPortal 用于插件独立开发
│
├── portal/                                 ← @openan/portal
│   ├── package.json                        ← exports: PortalApp + style.css
│   ├── index.html                          ← 开发入口 HTML
│   ├── vite.config.js                      ← 开发服务器 + 后端代理
│   ├── tailwind.config.js                  ← content 路径含插件源码
│   ├── postcss.config.js
│   ├── eslint.config.js
│   └── src/
│       ├── index.js                        ← 库入口: export { PortalApp }
│       ├── PortalApp.jsx                   ← 可复用壳(接收 pluginsConfig prop)
│       ├── App.jsx                          ← 仅开发用包装(加载 mock 插件)
│       ├── main.jsx                         ← 开发入口
│       ├── plugins.config.js               ← 开发用插件配置(仅 hello-portal)
│       ├── auth/
│       │   ├── AuthContext.jsx             ← 认证状态: check/login/logout
│       │   └── Login.jsx                   ← 登录页
│       ├── theme/
│       │   └── ThemeContext.jsx            ← 暗色/亮色, localStorage 持久化
│       ├── i18n/
│       │   ├── index.js                    ← i18n 初始化 + loadPluginI18n()
│       │   ├── base-en.json               ← Portal 基础翻译
│       │   └── base-zh.json
│       ├── service/
│       │   └── api.js                      ← 共享 axios (gateway 模式, httpOnly cookie)
│       ├── plugin/
│       │   └── registry.jsx               ← PluginRegistry context
│       └── components/
│           ├── header/index.jsx            ← 从插件清单动态生成导航
│           ├── error_boundary/index.jsx    ← 插件路由错误隔离
│           └── loading.jsx
│
└── plugins/
    └── hello-portal/                       ← Mock 插件(框架验证用)
        ├── package.json                    ← @openan-plugins/hello-portal
        ├── plugin.manifest.js
        └── src/
            ├── index.jsx                   ← 使用 usePortalContext() (auth/theme/i18n/api)
            ├── standalone.jsx              ← 独立模式入口
            └── locales/
                ├── en.json
                └── zh.json
```

## 插件规范

插件是任意导出 `plugin.manifest.js` 清单的 npm 包。清单声明插件的标识、菜单项、
路由和 i18n 资源。

### 清单字段

```js
import { Share2 } from 'lucide-react';

export default {
    // ── 标识 ──
    id: 'orchestration-center',      // 唯一插件 id
    name: 'Orchestration Center',     // 显示名
    version: '1.0.0',                 // 语义版本

    // ── 菜单 ── 菜单项出现在 Portal 导航栏中,允许多个(如子菜单)
    menu: [{
        id: 'orchestration',          // 唯一菜单项 id
        labelKey: 'orchestration-center:nav.orchestration', // i18n key
        icon: Share2,                 // lucide-react 图标组件
        order: 2,                    // 导航栏排序位置
        route: '/orchestration',     // 激活此项的路由路径
        permissions: [],             // (未来)所需权限
    }],

    // ── 路由 ── 在 Portal 内部注册到 React Router,组件懒加载(独立 chunk)
    routes: [{
        path: '/orchestration',      // 路由路径
        component: () => import('./src/index.jsx'),  // 懒加载导入
        menuId: 'orchestration',     // 关联菜单项(用于高亮当前项)
        permissions: [],             // (未来)所需权限
    }],

    // ── i18n ── 插件专属翻译,在 Portal 启动时加载,使用独立 namespace 避免冲突
    i18n: {
        namespace: 'orchestration-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },

    // ── 生命周期钩子(可选) ──
    onInit: async (ctx) => { /* 注册后调用一次 */ },
    onActivate: () => { /* 插件变为活跃视图时调用 */ },
    onDeactivate: () => { /* 插件离开活跃视图时调用 */ },

    // ── 独立模式(可选) ──
    standalone: {
        enabled: true,
        entry: './src/standalone.jsx',
    },
};
```

### PortalContext — 共享服务

插件通过 `usePortalContext()` 访问框架提供的服务:

```jsx
import { usePortalContext } from '@openan/portal-sdk';
import { useTranslation } from 'react-i18next';

function MyPlugin() {
    const { api, auth, theme, i18n, navigate } = usePortalContext();
    const { t } = useTranslation('my-plugin-namespace');

    // api      — 共享 axios 实例(gateway 模式, httpOnly cookie 自动附带)
    // auth     — { user, role, isAuthenticated, login, logout }
    // theme    — { isDark, toggle, setDark }
    // i18n     — react-i18next 实例
    // navigate — React Router 导航函数

    const handleClick = () => {
        api.get('/rest/v1/orchestrate/workflows')
           .then(data => console.log(data));
    };

    return (
        <button onClick={handleClick} className={theme.isDark ? 'dark' : ''}>
            {t('title')} — {auth.user}
        </button>
    );
}
```

| 服务 | 类型 | 提供内容 |
|------|------|----------|
| `api` | axios 实例 | 配置 gateway 基础 URL(`/api/orchestrate`)、120s 超时、`withCredentials: true`、响应拦截器自动解包 `.data`、401 → 触发 `auth-expired` 事件 |
| `auth` | object | `user`(当前用户名)、`role`、`isAuthenticated`(布尔)、`login(username, password)`、`logout()`、`checkAuth()` |
| `theme` | object | `isDark`(布尔)、`toggle()`、`setDark(布尔)` — 持久化到 localStorage,在 `<html>` 上应用 `dark` class |
| `i18n` | i18next 实例 | 在组件中用 `useTranslation('your-namespace')`;Portal 在启动时加载插件 locale |
| `navigate` | function | React Router 的 `navigate(path)`,用于编程式导航 |
| `router` | object | `{ location, navigate }` — 当前位置 + 导航函数 |

## 消费方仓库接入

### 概览

消费方仓库(如 `orchestration-center`)需要:
1. 一个 Vite + React + Tailwind 项目(一次性搭建)
2. 安装 `@openan/portal` 和 `@openan/portal-sdk` 包
3. 一个 4 行的 `main.jsx`,渲染 `PortalApp`
4. 一个 `plugins.config.js`,声明启用的插件
5. 插件包(实际的业务子应用)

一次性搭建后,新增/删除/禁用插件只需编辑 `plugins.config.js` —— 无需改动框架代码。

### 步骤 1: 安装

```bash
# 已发布包(未来):
npm install @openan/portal @openan/portal-sdk
npm install react react-dom react-router-dom react-i18next i18next i18next-browser-languagedetector

# 本地开发(npm link):
cd openan-website/portal && npm link
cd openan-website/packages/portal-sdk && npm link
cd your-consumer-repo
npm link @openan/portal @openan/portal-sdk
```

### 步骤 2: 消费方仓库结构

```
your-repo/
├── openan-app/                         ← 薄应用层(替代旧 workflow-designer)
│   ├── package.json                    ← 依赖 @openan/portal
│   ├── vite.config.js                 ← React 插件 + 后端代理
│   ├── index.html
│   ├── tailwind.config.js             ← content 路径包含 Portal + 插件源码
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx                    ← 4 行: 导入 PortalApp + 渲染
│       └── plugins.config.js          ← 声明启用的插件
│
├── plugins/                            ← 业务子应用
│   ├── registry-center/
│   │   ├── package.json
│   │   ├── plugin.manifest.js          ← 声明菜单、路由、i18n
│   │   └── src/
│   │       ├── index.jsx               ← 插件组件
│   │       └── locales/
│   │           ├── en.json
│   │           └── zh.json
│   ├── orchestration-center/
│   │   └── ...
│   └── ...
│
└── (后端代码, 不变)
```

### 步骤 3: 消费方 `main.jsx`

```jsx
import { createRoot } from 'react-dom/client';
import { PortalApp } from '@openan/portal';
import '@openan/portal/style.css';
import pluginsConfig from './plugins.config.js';

createRoot(document.getElementById('root')).render(
    <PortalApp pluginsConfig={pluginsConfig} />
);
```

`PortalApp` 内部已包含:
- `<BrowserRouter>`(React Router)
- `<ThemeProvider>`(暗色/亮色, localStorage)
- `<AuthProvider>`(通过后端 cookie 进行登录/登出/认证检查)
- `<PortalShell>`(插件加载、动态 Header、路由渲染,含 `<Suspense>` + `<ErrorBoundary>`)
- i18n 初始化(基础翻译 + 插件 namespace 加载)

### 步骤 4: 消费方 `plugins.config.js`

```js
export default {
    plugins: [
        {
            id: 'registry-center',
            enabled: true,
            manifest: () => import('./plugins/registry-center/plugin.manifest.js'),
        },
        {
            id: 'orchestration-center',
            enabled: true,
            manifest: () => import('./plugins/orchestration-center/plugin.manifest.js'),
        },
        {
            id: 'skill-center',
            enabled: false,  // 禁用 — tree-shake, 永不导入
            manifest: () => import('./plugins/skill-center/plugin.manifest.js'),
        },
    ],
};
```

禁用的插件永远不会被导入(Vite 在生产构建中 tree-shake 掉),实现按需组合不同交付场景。

### 步骤 5: 消费方 `vite.config.js`

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    server: {
        port: 3003,
        // Gateway 代理 — 去掉 /api/orchestrate 前缀后转发到后端
        // Portal 的 API 客户端默认使用 gateway 模式
        proxy: {
            '/api/orchestrate': {
                target: 'http://127.0.0.1:5001',
                changeOrigin: true,
                secure: false,
                rewrite: (p) => p.replace(/^\/api\/orchestrate/, ''),
            },
        },
    },
    plugins: [react()],
});
```

### 步骤 6: 消费方 `tailwind.config.js`

```js
export default {
    darkMode: 'class',
    content: [
        './index.html',
        './src/**/*.{js,jsx}',
        './plugins/*/src/**/*.{js,jsx}',
        // ── 关键: 包含 Portal 源码, 让 Tailwind 生成
        //    Portal 组件(Header, Login 等)使用的 class ──
        './node_modules/@openan/portal/src/**/*.{js,jsx}',
    ],
    theme: { extend: {} },
    plugins: [],
};
```

## PortalApp 管什么 vs 插件管什么

| 关注点 | 处理方 | 方式 |
|--------|--------|------|
| 路由(URL → 插件视图) | PortalApp | React Router, 懒加载 `<Route>` |
| 导航栏(菜单按钮) | PortalApp | 从插件清单 `menu[]` 自动生成 |
| 认证(登录/登出) | PortalApp | `AuthContext` → 后端 `/auth/*` 端点, httpOnly cookie |
| 主题(暗色/亮色) | PortalApp | `ThemeContext`, `localStorage`, `<html>` 上的 `dark` class |
| i18n 基座(导航、登录、通用) | PortalApp | `portal/src/i18n/` 中的基础翻译 |
| 插件 i18n 加载 | PortalApp | 启动时 `loadPluginI18n()`, 每插件独立 namespace |
| API 客户端(gateway, cookie) | PortalApp | 共享 axios 实例, 通过 `usePortalContext().api` |
| 错误隔离 | PortalApp | 每个插件路由的 `<ErrorBoundary>` |
| 懒加载 | PortalApp | 每路由 `React.lazy()`, `<Suspense>` 回退 |
| **插件业务逻辑** | **插件** | 组件内部(state, effect, 数据处理) |
| **插件专属 API 调用** | **插件** | 使用 `usePortalContext().api` 调用自己的端点 |
| **插件专属 i18n** | **插件** | 自己的 locale 文件, 自己的 namespace |
| **插件 UI/组件** | **插件** | 自己的 JSX, Tailwind class, 子组件 |

## 新增 / 删除 / 启用 / 禁用插件

全部由 `plugins.config.js` 控制 —— 无需改 PortalApp 代码:

```js
// 新增插件 — 加一条:
{
    id: 'analytics-dashboard',
    enabled: true,
    manifest: () => import('./plugins/analytics-dashboard/plugin.manifest.js'),
}

// 某交付场景裁掉 — enabled 设 false:
{
    id: 'skill-center',
    enabled: false,
    manifest: () => import('./plugins/skill-center/plugin.manifest.js'),
}
```

Portal 导航栏自动更新 —— 菜单按钮从已启用插件的清单中生成。

## 插件独立模式

每个插件可以脱离完整 Portal 壳独立运行开发,使用 `@openan/portal-sdk/standalone`
中的 `MockPortal`:

```jsx
// plugins/my-plugin/src/standalone.jsx
import { createRoot } from 'react-dom/client';
import { MockPortal } from '@openan/portal-sdk/standalone';
import MyPlugin from './index.jsx';

createRoot(document.getElementById('root')).render(
    <MockPortal>
        <MyPlugin />
    </MockPortal>
);
```

`MockPortal` 提供最小化的 `PortalContext`(mock 值:admin 用户、暗色主题等),
让插件可以渲染并独立开发。

## 框架开发

```bash
# 安装所有 workspace 包
npm install

# 启动 Portal 开发服务器(加载 mock hello-portal 插件)
npm run dev

# 生产构建
npm run build

# 代码检查
npm run lint
```

Portal 开发服务器运行在 http://localhost:3003,代理 `/api/orchestrate/`
到后端 http://127.0.0.1:5001。

### 验证结果

```
npm install    ✓  400+ 个包
npm run build  ✓  1838 个模块转换, 约 1s
npm run lint   ✓  0 错误
npm run dev    ✓  Vite 在 ~280ms 内就绪, 运行于 http://localhost:3003
```

构建输出展示了插件架构正常工作:
- `plugin.manifest-*.js` — 插件清单作为独立 chunk(动态加载)
- `src-*.js` — 插件组件作为懒加载 chunk
- `en-*.js`, `zh-*.js` — 插件 i18n locale 作为按需 chunk
- `index-*.js` — Portal 主 bundle

## 设计决策

### 1. 构建时集成(workspace 别名)而非运行时(Module Federation)

禁用插件通过 `plugins.config.js` 中的动态 `import()` 控制 —— Vite 在生产构建中
tree-shake 掉。所有插件与 Portal 统一发布(符合 issue #77 No-Goal: 无独立版本管理)。

未来演进: 切换到 Module Federation 实现运行时插件加载,无需重新构建 Portal。

### 2. 路由驱动导航而非状态驱动 tab 切换

之前: `App.jsx` 中的 `activeTab` state,URL 始终为 `/`。
之后: React Router 路由(`/registry`, `/orchestration` 等)—— URL 可分享、可收藏。

### 3. 插件通过后端 API 隔离

插件间不共享前端 state 或事件总线(符合 issue #77 No-Goal)。
跨插件通信通过后端 API 完成。

### 4. JSX 放 `.jsx`,纯 JS 放 `.js`

遵循现有项目约定(`AGENTS.md`: "Frontend is JS/JSX, not TypeScript")。
含 JSX 的文件用 `.jsx` 扩展名;portal-sdk 的 `plugin-context.js` 是 `.js` 垫片,
从 `.jsx` 再导出。

### 5. 可发布包使用 peerDependencies

`react`, `react-dom`, `react-router-dom`, `react-i18next`, `i18next` 在
`@openan/portal` 中声明为 `peerDependencies` —— 消费方提供单一 React 实例,
防止因 React 重复导致的 hooks 崩溃。

## 迁移影响(P3: 现有业务模块 → 插件)

将现有模块从单体 `workflow-designer/` 迁移为插件时,影响如下:

### 零影响(不变)

- **后端 API** — 所有端点、认证、SSE 不变
- **业务逻辑** — 组件内部(state、effect、数据处理)不变
- **UI/UX** — 同样的 Tailwind class、同样的布局、同样的交互
- **React Flow** — 工作流画布 DAG 不变
- **SSE 流** — 执行中心 EventSource 不变

### 微调(代码组织变化, 非功能变化)

| 变化 | 之前 | 之后 | 工作量 |
|------|------|------|--------|
| 组件 prop 来源 | `isDark`, `t` 来自 props | `usePortalContext()` + `useTranslation('namespace')` | 每个根组件 2-3 行 |
| 子组件 prop 透传 | 父组件传 `isDark` 给子组件 | **不变** — 父组件从 context 获取后照常透传 | 零 |
| API 导入路径 | `import { fn } from '@/service/api.js'` | `import { fn } from './service/api.js'`(插件内) | 仅路径 |
| API 函数签名 | `getWorkflows()` | `getWorkflows()`(完全一致) | 零 |
| i18n key | `t('registry.title')`(全局) | `t('title')`(namespace) | 去掉前缀 |
| 文件位置 | `components/registry_center/` | `plugins/registry-center/src/` | 移动文件 |
| 导航 | 状态驱动 tab(`activeTab`) | URL 路由(`/registry`) | 改善 — URL 可分享 |
| 构建 | 单项目 | Monorepo workspace | Dockerfile 路径变 |

### 跨模块依赖

执行中心当前从编排中心导入:
```jsx
import { transformWorkflowToReactFlow } from '@/components/orchestration_center/workflow/utils/index.jsx';
import UnifiedWorkflow from '../orchestration_center/workflow/index.jsx';
```

**解决方案**: 将共享工作流组件提取为 `@openan/shared-workflow` 包,
两个插件都依赖它。

### API 函数分配

| 函数 | 使用方 | 包 |
|------|--------|-----|
| `authCheck`, `login`, `logout`, `register`, `changePassword` | Portal 壳 | `@openan/portal`(已包含) |
| `getAgentCards` | 3 个插件 | `@openan/shared-api`(共享) |
| `getWorkflows`, `parsePdf`, `handlePlan`, `generateWorkflowFromIntent` 等 | 编排中心 | 插件内 |
| `matchWorkflows`, `getStartProcessStreamUrl`, `getExecutionRecords` 等 | 执行中心 | 插件内 |

### i18n Key 分配(共 282 个 key)

| Key 组 | 数量 | 目标 |
|--------|------|------|
| `nav`, `login`, `common`, `settings`, `error`, `error_boundary` | 48 | `@openan/portal` 基座 |
| `registry`, `agent_profile` | 43 | `plugins/registry-center/src/locales/` |
| `orchestration`, `workflow`, `workflow_empty`, `node_label` | 76 | `plugins/orchestration-center/src/locales/` |
| `execution` | 91 | `plugins/execution-center/src/locales/` |
| `skills` | 22 | `plugins/skill-center/src/locales/` |

## Issue #77 合规性

| 目标 | 状态 |
|------|------|
| 独立的 `openan-website` 前端框架项目 | ✅ 本仓库 |
| 可插拔架构: 导航、认证、主题、i18n、插件注册机制 | ✅ PortalApp |
| 插件集成规范(路由、菜单、权限) | ✅ plugin.manifest.js |
| 每个子应用作为独立插件 | ✅ 插件规范 + 配置 |
| 配置文件实现按需组合 | ✅ plugins.config.js |
| 为未来扩展(Skill Center)提供标准集成规范 | ✅ 插件规范 |
| 每个子项目支持独立运行模式 | ✅ MockPortal |
| 一键启动开发脚本 | ✅ `scripts/dev-all.js` |

| 非目标 | 合规 |
|--------|------|
| 不做跨子应用 state 共享 / 事件总线 | ✅ 插件通过后端 API 通信 |
| 不做独立版本管理 | ✅ 构建时集成, 统一发布 |
| 不改后端 API 层 | ✅ 后端不变 |
