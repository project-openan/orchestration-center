# OpenAN Portal — 统一 Web 框架(可插拔门户)方案汇报

---

## 第 1 页 · 封面

### OpenAN Portal
### 统一 Web 框架 — 可插拔门户架构

**Issue #77**: Provide a Unified Web Framework (Pluggable Portal)

汇报人：OpenAN 团队
日期：2026-08-26

---

## 第 2 页 · 背景与问题

### 现状：单体前端，模块耦合

- 前端代码集中在 `workflow-designer/` 单体 React SPA 中（40 个文件）
- 4 个业务模块（注册中心、编排中心、执行中心、技能中心）**硬编码**在 `App.jsx` 和 `Header` 中
- 导航按钮写死，新增模块需侵入式修改框架代码
- 无法按需裁剪（如某交付场景只交付编排中心）
- 注册中心是独立后端服务（:5000），但前端 API 全部走编排中心后端（:5001）转发
- 282 个 i18n key 混在两个大文件中，无法按模块拆分

**核心痛点**：扩展困难、无法独立部署、模块间耦合严重

---

## 第 3 页 · 目标架构

### 核心理念：框架是壳，业务是插件

```
┌────────────────────────────────────────────────────────┐
│                    @openan/portal                       │
│                 (Portal Shell)                          │
│                                                        │
│  ┌──────────┐ ┌──────────┐ ┌────────────────────────┐│
│  │ 认证     │ │ 主题     │ │ 国际化基座 + 插件加载   ││
│  │ 登录/登出 │ │ 暗色/亮色│ │                        ││
│  └──────────┘ └──────────┘ └────────────────────────┘│
│  ┌────────────────────────────────────────────────────┐│
│  │ 动态导航栏 — 从插件清单自动生成菜单按钮              ││
│  │ 插件管理器 — 运行时启用/禁用/查看配置               ││
│  └────────────────────────────────────────────────────┘│
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ 注册中心插件  │ │ 编排中心插件  │ │ 执行中心插件  │  │
│  │ /registry    │ │ /orchestrate │ │ /execution    │  │
│  │ 后端 :5000   │ │ 后端 :5001   │ │ 后端 :5001   │  │
│  └──────────────┘ └──────────────┘ └──────────────┘  │
│         ↕                ↕                ↕           │
│     usePortalContext() — api, auth, theme, i18n        │
└────────────────────────────────────────────────────────┘
```

**框架不含业务逻辑，消费方写插件即可集成**

---

## 第 4 页 · 插件规范

### 一个插件 = 一个 `plugin.manifest.js`

```js
export default {
    id: 'registry-center',
    name: 'Registry Center',
    version: '0.1.0',
    backend: { gateway: '/api/registry' },    // 独立后端声明
    menu: [{
        id: 'agents',
        labelKey: 'registry-center:registry.title',
        icon: LayoutDashboard,
        order: 1,
        route: '/registry',
    }],
    routes: [{
        path: '/registry',
        component: () => import('./src/index.jsx'),   // 懒加载
        menuId: 'agents',
    }],
    i18n: {
        namespace: 'registry-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },
};
```

### PortalContext — 插件访问框架服务

| 服务 | 说明 |
|------|------|
| `api` | 独立 axios 实例（按插件 backend.gateway 创建） |
| `auth` | 用户名、角色、认证状态、登录/登出 |
| `theme` | 暗色/亮色切换 |
| `i18n` | 国际化实例（插件用独立 namespace） |
| `navigate` | 编程式路由导航 |

---

## 第 5 页 · 仓库结构

### 独立框架仓库 + 业务插件

```
openan-website/                         ← 框架仓库（独立）
├── packages/
│   ├── portal-sdk/                     ← 插件规范 & 共享契约
│   └── shared-workflow/                ← 共享工作流画布组件
├── portal/                              ← Portal Shell
│   └── src/
│       ├── PortalApp.jsx               ← 可复用壳（接收 pluginsConfig）
│       ├── auth/ theme/ i18n/          ← 认证、主题、国际化
│       ├── service/api.js              ← 共享 API + createApi(gateway)
│       └── components/
│           ├── header/                 ← 动态导航
│           └── plugin_manager/          ← 运行时插件管理
├── plugins/                            ← 业务插件
│   ├── registry-center/                ← 独立后端 (:5000)
│   ├── orchestration-center/           ← 默认后端 (:5001)
│   ├── execution-center/               ← 默认后端 (:5001)
│   └── demo-showcase/                  ← 无后端 Demo
└── scripts/mock-backend.mjs            ← 双后端 Mock
```

| 部分 | 文件数 | 职责 |
|------|--------|------|
| Portal SDK | 6 | 插件规范、PortalContext、配置加载器 |
| Portal Shell | 20 | 认证、主题、i18n、动态导航、插件管理 |
| Shared Workflow | 14 | UnifiedWorkflow 画布（编排+执行共用） |
| 业务插件 ×4 | 24 | 注册中心、编排中心、执行中心、Demo |
| **合计** | **68** | （原单体：40 文件） |

---

## 第 6 页 · 消费方接入（4 步）

### 接入 Portal 只需 4 步

**Step 1：安装**
```bash
npm install @openan/portal @openan/portal-sdk
npm install react react-dom react-router-dom react-i18next i18next
```

**Step 2：`main.jsx`（4 行）**
```jsx
import { createRoot } from 'react-dom/client';
import { PortalApp } from '@openan/portal';
import '@openan/portal/style.css';
import pluginsConfig from './plugins.config.js';
createRoot(document.getElementById('root')).render(
    <PortalApp pluginsConfig={pluginsConfig} />
);
```

**Step 3：`plugins.config.js`**
```js
export default {
    plugins: [
        { id: 'registry-center', enabled: true,
          manifest: () => import('@openan-plugins/registry-center/plugin.manifest.js') },
        { id: 'skill-center', enabled: false,  // 裁掉，tree-shake
          manifest: () => import('@openan-plugins/skill-center/plugin.manifest.js') },
    ],
};
```

**Step 4：Vite 代理 + Tailwind 配置**

### 之后增删插件只需改 `plugins.config.js`，不动框架代码

---

## 第 7 页 · 迁移影响

### 以 registry-center 为例：5 处改动，业务逻辑零修改

| 改动 | 之前 | 之后 | 工作量 |
|------|------|------|--------|
| 组件签名 | `({ isDark, t })` | `() + usePortalContext()` | 2 行 |
| API 导入 | `from "@/service/api.js"` | `api.get('/rest/v1/registry/...')` | 1 行 |
| i18n | `useTranslation()` 全局 | `useTranslation('registry-center')` | 1 行 |
| 后端声明 | 无 | `backend: { gateway: '/api/registry' }` | 1 行 |
| 清单文件 | 无 | `plugin.manifest.js` | 新建 |

**原始 395 行 → 改后 395 行（业务逻辑不变，只改 5 处接口来源）**

### 零影响项

| 维度 | 影响 |
|------|------|
| 后端 API | 零 — 端点不变 |
| 组件业务逻辑 | 零 — state/effect/数据处理不变 |
| UI/UX | 零 — 同样的 Tailwind class、布局 |
| 子组件 | 零 — `isDark` 仍由父组件 prop 传入 |

---

## 第 8 页 · 运行时插件管理

### 可视化管理：启用 / 禁用 / 查看配置

- 导航栏右上角**拼图图标**（带角标显示活跃插件数）
- 点击打开 **Plugin Manager** 弹窗：
  - 列出全部插件，显示名称、版本、路由、ID
  - Toggle 开关运行时启用/禁用
  - 禁用后：菜单消失、路由不可访问、自动重定向
  - 状态持久化到 localStorage
  - 展开查看完整 `plugin.manifest.js` JSON 配置

### 按需组合

```js
// 某交付场景：只交付编排中心
{ id: 'registry-center', enabled: false, ... }
{ id: 'orchestration-center', enabled: true, ... }
{ id: 'execution-center', enabled: false, ... }
```

---

## 第 9 页 · 多后端架构 & 部署方案

### 每个插件可声明独立后端

```
浏览器 (:3003)
    ├── /api/registry    →  注册中心后端 (:5000)  ← registry-center 插件
    ├── /api/orchestrate →  编排中心后端 (:5001)  ← orchestration/execution 插件
    └── (无后端)          →  demo-showcase 插件
```

### 生产部署

```yaml
services:
  portal:
    build: ./openan-website/portal
    ports: ["3003:80"]
    environment:
      - REGISTRY_URL=http://registry-center:5000
      - BACKEND_URL=http://orchestration-center:5001
  orchestration-center:
    build: ./orchestration-center       # 后端 + 插件静态资源
    ports: ["5001:5001"]
  registry-center:
    build: ./registry-center            # 独立后端服务
    ports: ["5000:5000"]
```

### 独立部署演进路径

| 阶段 | 集成方式 | 插件部署 |
|------|----------|----------|
| 当前 | 构建时集成（workspace） | 与 Portal 一起构建 |
| 未来 | 独立构建 + nginx 分发 | 各自构建、各自部署 |
| 远期 | Module Federation | 运行时远程加载 |

---

## 第 10 页 · 验证结果 & Issue #77 合规

### 验证通过

```
npm install    ✓  400+ packages
npm run build  ✓  1838 modules, ~1s
npm run dev    ✓  6 个服务全部运行
```

### 功能验证

| 功能 | 状态 |
|------|------|
| Portal Shell 加载 | ✅ |
| 动态导航栏（从清单生成） | ✅ |
| 4 个插件全部加载 | ✅ |
| 路由驱动（URL 可分享） | ✅ |
| 认证门控 | ✅ |
| 主题切换 | ✅ |
| 语言切换 | ✅ |
| 运行时插件启用/禁用 | ✅ |
| 插件配置查看 | ✅ |
| 多后端代理 | ✅ |
| 插件 i18n 独立 namespace | ✅ |
| 错误隔离（ErrorBoundary） | ✅ |

### Issue #77 目标达成

| 目标 | 状态 |
|------|------|
| 独立 `openan-website` 框架项目 | ✅ |
| 可插拔架构（导航/认证/主题/i18n/注册） | ✅ |
| 插件集成规范（路由/菜单/权限） | ✅ |
| 配置文件按需组合 | ✅ |
| 标准集成规范（Skill Center 可扩展） | ✅ |
| 独立运行模式（MockPortal） | ✅ |
| 一键启动脚本 | ✅ |
| 不做跨插件 state 共享 | ✅ |
| 不改后端 API 层 | ✅ |
