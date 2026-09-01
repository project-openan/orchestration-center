# OpenAN Portal — 独立部署与运行时插件加载方案

> **基于**: OpenAN-Portal-Design.md (构建时集成方案)
> **变更**: 从构建时集成 → 运行时集成 (Module Federation)
> **日期**: 2026-08-26

---

## 1. 需求

注册中心和编排中心需要:
- **独立部署** — 各自的容器/服务器,独立运行
- **独立发布版本** — 各自有版本号,独立更新,不影响 Portal
- **独立仓库** — 前端插件代码放在各自的业务仓库中

---

## 2. 架构对比

### 2.1 当前(构建时集成)

```
开发:  插件源码在 openan-website/workspace → Vite 统一编译
构建:  Portal + 所有插件 → 一个 dist/
部署:  一个 nginx 容器
加载:  浏览器加载 Portal,插件 chunk 已在 bundle 中

问题:  插件和 Portal 绑定发布,无法独立部署/独立版本
```

### 2.2 目标(运行时集成)

```
开发:  每个插件在各自仓库,独立 Vite 构建
构建:  Portal 单独构建 → dist/
       编排中心插件单独构建 → remoteEntry.js
       注册中心插件单独构建 → remoteEntry.js
部署:  Portal → nginx :3003
       编排中心 → nginx :5001 (后端 API + 静态插件 JS)
       注册中心 → nginx :5000 (后端 API + 静态插件 JS)
加载:  浏览器加载 Portal (:3003)
         → Portal 从 :5001 远程加载编排中心 remoteEntry.js
         → Portal 从 :5000 远程加载注册中心 remoteEntry.js
         → 插件各自独立版本,独立更新
```

### 2.3 架构图

```
                     浏览器 (:3003)
                         │
                    Portal Shell
                   (nginx: 框架 HTML + JS)
                         │
              ┌──────────┼──────────┐
              │          │          │
         动态加载     动态加载     (无远程)
              ↓          ↓          ↓
     :5001/remote    :5000/remote    demo-showcase
     Entry.js        Entry.js        (构建在Portal中)
         ↑              ↑
    编排中心插件     注册中心插件
    (独立构建)       (独立构建)
    v1.2.0           v0.3.1
         ↑              ↑
    编排中心后端     注册中心后端
    /api/orchestrate  /api/registry
    /rest/v1/...      /rest/v1/...
```

---

## 3. 仓库结构

### 3.1 openan-website (Portal 框架仓库)

不再包含业务插件,只保留框架 + Demo:

```
openan-website/
├── packages/
│   ├── portal-sdk/              ← @openan/portal-sdk (不变)
│   └── shared-workflow/         ← @openan/shared-workflow (发布为 npm 包)
│
├── portal/                      ← @openan/portal (不变,但加远程加载器)
│   └── src/
│       ├── PortalApp.jsx        ← 加远程插件加载逻辑
│       ├── plugins.config.js    ← 改为声明远程 URL
│       └── ... (auth/theme/i18n/header/...)
│
├── plugins/
│   ├── demo-showcase/           ← 构建在 Portal 中(纯前端 Demo)
│   └── hello-portal/            ← 构建在 Portal 中(mock)
│
└── scripts/dev-all.js
```

### 3.2 orchestration-center (编排中心仓库)

```
orchestration-center/
├── orchestrate/                 ← 后端 (不变)
├── openan-plugin/               ← 前端插件 (新增)
│   ├── package.json
│   ├── vite.config.js           ← Module Federation 配置
│   ├── plugin.manifest.js       ← 插件声明 (不变)
│   └── src/
│       ├── index.jsx            ← 主组件 (不变)
│       ├── packages/
│       └── locales/
│
├── Dockerfile                   ← 后端 + 前端插件 (多阶段构建)
└── docker-compose.yml
```

### 3.3 registry-center (注册中心仓库)

```
registry-center/
├── (后端代码)
├── openan-plugin/               ← 前端插件
│   ├── package.json
│   ├── vite.config.js           ← Module Federation 配置
│   ├── plugin.manifest.js
│   └── src/
│       ├── index.jsx
│       ├── agentcard_visualization/
│       ├── code_inspector/
│       └── locales/
│
├── Dockerfile
└── docker-compose.yml
```

---

## 4. Module Federation 配置

### 4.1 插件端 (以 orchestration-center 为例)

`openan-plugin/vite.config.js`:

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { federation } from '@module-federation/vite';

export default defineConfig({
    plugins: [
        react(),
        federation({
            name: 'orchestration_center',
            filename: 'remoteEntry.js',
            exposes: {
                './plugin.manifest': './plugin.manifest.js',
                './src/index': './src/index.jsx',
            },
            shared: {
                react: { singleton: true },
                'react-dom': { singleton: true },
                'react-router-dom': { singleton: true },
                'react-i18next': { singleton: true },
                i18next: { singleton: true },
            },
        }),
    ],
    build: {
        target: 'esnext',
        minify: true,
    },
});
```

构建产出:
```
openan-plugin/dist/
├── remoteEntry.js              ← Portal 远程加载的入口
├── assets/
│   ├── index-xxxxx.js          ← 插件组件 chunk
│   ├── en-xxxxx.js             ← i18n locale chunk
│   └── zh-xxxxx.js
└── ...
```

### 4.2 Portal 端

`portal/vite.config.js` 加 Federation 消费方配置:

```js
federation({
    name: 'portal',
    remotes: {
        // 远程插件 — 运行时从各自的服务器加载
        orchestration_center: 'http://localhost:5001/remoteEntry.js',
        registry_center: 'http://localhost:5000/remoteEntry.js',
    },
    shared: {
        react: { singleton: true },
        'react-dom': { singleton: true },
        'react-router-dom': { singleton: true },
        'react-i18next': { singleton: true },
        i18next: { singleton: true },
    },
}),
```

### 4.3 plugins.config.js 改为远程声明

```js
export default {
    plugins: [
        // 远程插件 — 运行时从独立部署的服务器加载
        {
            id: 'registry-center',
            enabled: true,
            remote: {
                name: 'registry_center',
                url: 'http://localhost:5000/remoteEntry.js',
                manifest: './plugin.manifest',
                component: './src/index',
            },
        },
        {
            id: 'orchestration-center',
            enabled: true,
            remote: {
                name: 'orchestration_center',
                url: 'http://localhost:5001/remoteEntry.js',
                manifest: './plugin.manifest',
                component: './src/index',
            },
        },
        // 本地插件 — 构建在 Portal 中 (Demo 等)
        {
            id: 'demo-showcase',
            enabled: true,
            manifest: () => import('@openan-plugins/demo-showcase/plugin.manifest.js'),
        },
    ],
};
```

### 4.4 Portal 远程加载器

Portal 的 `PortalApp.jsx` 需要加远程插件加载逻辑:

```jsx
// 伪代码 — 实际实现用 Module Federation 的 loadRemote
async function loadRemotePlugin(remoteConfig) {
    // 1. 加载 remoteEntry.js (Module Federation 处理)
    const manifest = await loadRemote(`${remoteConfig.name}${remoteConfig.manifest}`);
    const component = await loadRemote(`${remoteConfig.name}${remoteConfig.component}`);

    // 2. 合并到插件列表
    return {
        ...manifest.default,
        routes: manifest.default.routes.map(r => ({
            ...r,
            component: () => loadRemote(`${remoteConfig.name}${remoteConfig.component}`),
        })),
    };
}
```

---

## 5. 部署方案

### 5.1 每个插件仓库的 Dockerfile

```dockerfile
# orchestration-center/Dockerfile
FROM node:20-slim AS plugin-builder
WORKDIR /app/plugin
COPY openan-plugin/package.json package-lock.json ./
RUN npm ci
COPY openan-plugin/ .
RUN npm run build              # → dist/remoteEntry.js

FROM node:20-slim AS backend
WORKDIR /app
COPY orchestrate/ .
COPY requirements.txt .
RUN pip install -r requirements.txt

# 后端 API (:5001) + 静态插件 JS
# FastAPI 同时 serve /remoteEntry.js 和 /assets/*
FROM nginx:1.27-alpine
# 前端插件静态文件
COPY --from=plugin-builder /app/plugin/dist /usr/share/nginx/html/plugin
# 后端由 FastAPI 提供,nginx 代理
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

### 5.2 编排中心 nginx.conf

```nginx
server {
    listen 5001;

    # 插件静态资源 — Portal 远程加载
    location /remoteEntry.js {
        root /usr/share/nginx/html/plugin;
        add_header Access-Control-Allow-Origin *;
    }
    location /assets/ {
        root /usr/share/nginx/html/plugin;
        add_header Access-Control-Allow-Origin *;
    }

    # 后端 API
    location /rest/v1/ {
        proxy_pass http://127.0.0.1:15001;  # FastAPI uvicorn
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

### 5.3 docker-compose (全栈)

```yaml
services:
  portal:
    build: ./openan-website/portal
    ports: ["3003:80"]
    environment:
      - REGISTRY_PLUGIN_URL=http://registry-center:5000/remoteEntry.js
      - ORCHESTRATION_PLUGIN_URL=http://orchestration-center:5001/remoteEntry.js
    depends_on: [orchestration-center, registry-center]

  orchestration-center:
    build: ./orchestration-center
    ports: ["5001:5001"]
    # 同时提供: 后端 API + 插件 remoteEntry.js

  registry-center:
    build: ./registry-center
    ports: ["5000:5000"]
    # 同时提供: 后端 API + 插件 remoteEntry.js
```

### 5.4 独立更新流程

```bash
# 编排中心发新版本 — 不影响 Portal 和注册中心
cd orchestration-center
git tag v1.2.0
# CI/CD: 构建插件 → 构建后端 → 部署到 :5001
# Portal 运行时自动加载新版本的 remoteEntry.js

# Portal 发新版本 — 不影响插件
cd openan-website
git tag v0.3.0
# CI/CD: 构建 Portal → 部署到 :3003
# 插件 remoteEntry.js URL 不变,继续正常加载
```

---

## 6. 关键技术问题

### 6.1 Shared Dependencies (单例)

React、react-dom、react-router-dom 等必须 singleton — Portal 和所有插件共享同一份:

```js
// 每个插件的 vite.config.js
shared: {
    react: { singleton: true, requiredVersion: '^18.0.0' },
    'react-dom': { singleton: true, requiredVersion: '^18.0.0' },
    'react-router-dom': { singleton: true },
    'react-i18next': { singleton: true },
    i18next: { singleton: true },
}
```

Portal 加载时会提供这些依赖,插件加载时复用,不会重复加载 React。

### 6.2 CORS

插件 JS 部署在不同端口/域名,需要 CORS 头:

```nginx
location /remoteEntry.js {
    add_header Access-Control-Allow-Origin *;
}
location /assets/ {
    add_header Access-Control-Allow-Origin *;
}
```

### 6.3 i18n Namespace

插件的 i18n locale 文件需要远程加载。两种方案:

**方案 A**: locale 打包在插件的 remoteEntry.js 中(简单,但增大 bundle)
**方案 B**: locale 作为独立 JSON 文件,Portal 运行时 fetch

推荐方案 B — locale 文件小(几 KB),独立加载更灵活:

```js
// plugin.manifest.js 中声明远程 locale URL
i18n: {
    namespace: 'orchestration-center',
    resources: {
        en: () => fetch(`${remoteBaseUrl}/locales/en.json`).then(r => r.json()),
        zh: () => fetch(`${remoteBaseUrl}/locales/zh.json`).then(r => r.json()),
    },
}
```

### 6.4 插件不可用时的降级

远程插件可能因为网络问题或服务宕机而无法加载。Portal 需要:

```jsx
// PortalApp.jsx — 远程加载失败时显示降级 UI
<Suspense fallback={<Loading />}>
    <ErrorBoundary
        fallback={<PluginUnavailable pluginId={r.pluginId} />}
    >
        <RemoteComponent />
    </ErrorBoundary>
</Suspense>
```

导航栏中加载失败的插件显示灰色不可点击状态,其他插件正常使用。

### 6.5 开发联调

本地开发时,插件可以独立运行(standalone 模式),也可以联调:

```bash
# 方式 1: 插件独立开发 (standalone)
cd orchestration-center/openan-plugin
npm run dev:standalone          # Vite dev, 用 MockPortal

# 方式 2: 联调 — Portal + 远程插件同时运行
# Terminal 1: Portal
cd openan-website
npm run dev                     # :3003

# Terminal 2: 编排中心插件
cd orchestration-center/openan-plugin
npm run dev                     # :5001 (Vite dev + 后端)

# Terminal 3: 注册中心插件
cd registry-center/openan-plugin
npm run dev                     # :5000 (Vite dev + 后端)

# Portal 的 plugins.config.js 指向 localhost:5001 和 :5000
```

---

## 7. 与构建时方案的对比

| 维度 | 构建时集成(当前) | 运行时集成(Module Federation) |
|------|-------------------|-------------------------------|
| 插件位置 | workspace 包,源码在一起 | 独立仓库,各自构建 |
| 构建 | Portal + 插件一起编译 | 各自独立构建 |
| 产物 | 一个 dist/ | Portal dist/ + 每个插件 remoteEntry.js |
| 部署 | 一个 nginx 容器 | Portal 容器 + 每个插件容器 |
| 版本管理 | 统一版本 | 独立版本 |
| 更新 | 需重新构建 Portal | 插件独立更新,Portal 不变 |
| 加载方式 | import() (构建时解析) | 远程加载 remoteEntry.js (运行时) |
| 禁用插件 | tree-shake | 运行时不加载 |
| 共享依赖 | 自动(npm hoist) | singleton 声明 |
| 复杂度 | 低 | 中(Module Federation 配置 + CORS + 降级) |
| Issue #77 合规 | "不做独立版本管理" | 需要更新 Issue 目标 |

---

## 8. 实施步骤

| 阶段 | 内容 | 依赖 |
|------|------|------|
| **P1** | 安装 `@module-federation/vite` 到 Portal 和各插件 | 无 |
| **P2** | 给 orchestration-center 插件加 Vite Federation 配置,独立构建出 remoteEntry.js | P1 |
| **P3** | 给 registry-center 插件加同样配置 | P1 |
| **P4** | Portal 加远程加载器,改造 plugins.config.js 支持远程声明 | P1 |
| **P5** | Portal vite.config.js 加 remotes 配置 | P1, P2, P3 |
| **P6** | nginx CORS 配置 + 降级 UI | P2-P5 |
| **P7** | docker-compose 全栈部署验证 | P2-P6 |
| **P8** | 开发联调验证(standalone + 联调模式) | P2-P6 |

---

## 9. 风险与缓解

| 风险 | 可能性 | 影响 | 缓解 |
|------|--------|------|------|
| Module Federation Vite 插件兼容性 | 中 | 高 (构建失败) | 先在 mock 环境验证 |
| React 版本不一致导致运行时错误 | 中 | 高 (白屏) | peerDependencies + singleton 约束 |
| 远程加载延迟 | 低 | 低 (首次加载慢) | 预加载 + Loading 动画 |
| CORS 配置遗漏 | 中 | 中 (加载失败) | nginx 模板统一配置 |
| 插件服务宕机 | 低 | 中 (插件不可用) | 降级 UI + 健康检查 |
| shared-workflow 包跨远程共享 | 中 | 中 | 发布为 npm 包,各插件安装 |
