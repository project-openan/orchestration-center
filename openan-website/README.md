# OpenAN Website — Unified Web Framework (Pluggable Portal)

[English](./README.md) | [中文](./README_zh.md)

> **Issue**: [#77 — Provide a Unified Web Framework (Pluggable Portal)](https://github.com/project-openan/orchestration-center/issues/77)

An independent, reusable frontend framework. It provides a Portal shell
(navigation, authentication, theme, i18n, routing) into which any web page
can be integrated as a **plugin** — write a `plugin.manifest.js`, add one line
to `plugins.config.js`, and the page appears in the Portal.

## How It Works

```
┌──────────────────────────────────────────────────────────┐
│                     @openan/portal                        │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│ │  Portal Shell (PortalApp)                           │  │
│ │                                                     │  │
│ │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐ │  │
│ │  │ Auth     │  │ Theme    │  │ i18n Base         │ │  │
│ │  │ Login    │  │ Dark/Light│  │ + Plugin Loader   │  │
│ │  │ Logout   │  │          │  │                   │  │
│ │  └──────────┘  └──────────┘  └──────────────────┘ │  │
│ │                                                     │  │
│ │  ┌────────────────────────────────────────────────┐ │  │
│ │  │ Dynamic Header (renders nav from plugin menus) │ │  │
│ │  └────────────────────────────────────────────────┘ │  │
│ │                                                     │  │
│ │  ┌─────────────────┐ ┌─────────────────┐            │  │
│ │  │ Plugin A (Route) │ │ Plugin B (Route)│ ...        │  │
│ │  │ <Suspense+Error>│ │ <Suspense+Error>│            │  │
│ │  └─────────────────┘ └─────────────────┘            │  │
│ │          ↑               ↑                            │  │
│ │          └───────────────┴── usePortalContext()      │  │
│ │             (api, auth, theme, i18n, navigate)        │  │
│ └─────────────────────────────────────────────────────┘  │
│                         ↑                                │
│                @openan/portal-sdk                         │
│         (Plugin spec, PortalContext, contracts)           │
└──────────────────────────────────────────────────────────┘
                          ↑
              Consumer repo plugins.config.js
         (declares which plugins to load)
```

**Core idea**: The framework is a shell with no business logic. Consumer repos
install it, write their web pages as plugins (each with a manifest declaring
its menu button, route, and i18n), and register them via `plugins.config.js`.
The Portal auto-generates navigation, handles auth/theme/i18n, and renders
plugin routes with lazy loading and error boundaries.

## Published Packages

| Package | Exports | Purpose |
|---------|---------|---------|
| `@openan/portal` | `PortalApp`, `style.css` | The reusable Portal shell — accepts `pluginsConfig` prop, internally handles BrowserRouter, Auth, Theme, i18n, dynamic Header, routing, error boundaries |
| `@openan/portal-sdk` | `PortalContext`, `usePortalContext`, `PortalProvider`, `validateManifest`, `loadEnabledPlugins`, `MockPortal` | Plugin spec & shared contracts — plugins use `usePortalContext()` to access framework services |

**Peer dependencies** (consumer must install):
`react`, `react-dom`, `react-router-dom`, `react-i18next`, `i18next`,
`i18next-browser-languagedetector`

## Repository Structure

```
openan-website/                             ← THIS REPO (framework only)
├── package.json                            ← npm workspaces root
├── eslint.config.js
├── scripts/
│   └── dev-all.js                          ← One-click dev startup
│
├── packages/
│   └── portal-sdk/                         ← @openan/portal-sdk
│       ├── package.json
│       └── src/
│           ├── index.js                    ← Re-exports public API
│           ├── plugin-manifest.js          ← PluginManifest interface + validator
│           ├── plugin-context.jsx          ← PortalContext (React Context) + usePortalContext()
│           ├── plugin-context.js           ← .js shim re-export (no JSX)
│           ├── config-loader.js            ← loadEnabledPlugins() — async, tree-shakes disabled
│           └── standalone.jsx              ← MockPortal for standalone plugin dev
│
├── portal/                                 ← @openan/portal
│   ├── package.json                        ← exports: PortalApp + style.css
│   ├── index.html                          ← Dev entry HTML
│   ├── vite.config.js                      ← Dev server + backend proxy
│   ├── tailwind.config.js                  ← Content paths include plugin sources
│   ├── postcss.config.js
│   ├── eslint.config.js
│   └── src/
│       ├── index.js                        ← Library entry: export { PortalApp }
│       ├── PortalApp.jsx                   ← Reusable shell (accepts pluginsConfig prop)
│       ├── App.jsx                          ← Dev-only wrapper (loads mock plugin)
│       ├── main.jsx                         ← Dev entry point
│       ├── plugins.config.js               ← Dev plugin config (hello-portal only)
│       ├── auth/
│       │   ├── AuthContext.jsx             ← Auth state: check/login/logout
│       │   └── Login.jsx                   ← Login screen
│       ├── theme/
│       │   └── ThemeContext.jsx            ← Dark/light, localStorage persistence
│       ├── i18n/
│       │   ├── index.js                    ← i18n init + loadPluginI18n()
│       │   ├── base-en.json               ← Portal base translations
│       │   └── base-zh.json
│       ├── service/
│       │   └── api.js                      ← Shared axios (gateway mode, httpOnly cookie)
│       ├── plugin/
│       │   └── registry.jsx               ← PluginRegistry context
│       └── components/
│           ├── header/index.jsx            ← Dynamic nav from plugin manifests
│           ├── error_boundary/index.jsx    ← Plugin route error isolation
│           └── loading.jsx
│
└── plugins/
    └── hello-portal/                       ← Mock plugin (framework validation)
        ├── package.json                    ← @openan-plugins/hello-portal
        ├── plugin.manifest.js
        └── src/
            ├── index.jsx                   ← Uses usePortalContext() (auth/theme/i18n/api)
            ├── standalone.jsx              ← Standalone mode entry
            └── locales/
                ├── en.json
                └── zh.json
```

## Plugin Spec

A plugin is any npm package that exports a manifest from
`plugin.manifest.js`. The manifest declares the plugin's identity, menu
items, routes, and i18n resources.

### Manifest Fields

```js
import { Share2 } from 'lucide-react';

export default {
    // ── Identity ──
    id: 'orchestration-center',      // Unique plugin id
    name: 'Orchestration Center',     // Display name
    version: '1.0.0',                 // Semantic version

    // ── Menu ── Items appear in the Portal's navigation bar.
    //            Multiple items allowed (e.g. sub-menus).
    menu: [{
        id: 'orchestration',          // Unique menu item id
        labelKey: 'orchestration-center:nav.orchestration', // i18n key
        icon: Share2,                 // lucide-react icon component
        order: 2,                    // Sort position in nav bar
        route: '/orchestration',     // Route path that activates this item
        permissions: [],             // (future) required permissions
    }],

    // ── Routes ── Registered with React Router inside the Portal.
    //              Components are lazy-loaded (separate chunks).
    routes: [{
        path: '/orchestration',      // Route path
        component: () => import('./src/index.jsx'),  // Lazy import
        menuId: 'orchestration',     // Associated menu item (for active highlighting)
        permissions: [],             // (future) required permissions
    }],

    // ── i18n ── Plugin-specific translations, loaded at Portal startup.
    //            Uses a dedicated namespace to avoid key collisions.
    i18n: {
        namespace: 'orchestration-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },

    // ── Lifecycle hooks (optional) ──
    onInit: async (ctx) => { /* called once after registration */ },
    onActivate: () => { /* called when plugin becomes the active view */ },
    onDeactivate: () => { /* called when plugin leaves the active view */ },

    // ── Standalone mode (optional) ──
    standalone: {
        enabled: true,
        entry: './src/standalone.jsx',
    },
};
```

### PortalContext — Shared Services

Plugins access framework-provided services via `usePortalContext()`:

```jsx
import { usePortalContext } from '@openan/portal-sdk';
import { useTranslation } from 'react-i18next';

function MyPlugin() {
    const { api, auth, theme, i18n, navigate } = usePortalContext();
    const { t } = useTranslation('my-plugin-namespace');

    // api      — Shared axios instance (gateway mode, httpOnly cookie auto-attached)
    // auth     — { user, role, isAuthenticated, login, logout }
    // theme    — { isDark, toggle, setDark }
    // i18n     — react-i18next instance
    // navigate — React Router navigate function

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

| Service | Type | What it provides |
|---------|------|-------------------|
| `api` | axios instance | Configured with gateway base URL (`/api/orchestrate`), 120s timeout, `withCredentials: true`, response interceptor auto-unwraps `.data`, 401 → `auth-expired` event |
| `auth` | object | `user` (current username), `role`, `isAuthenticated` (boolean), `login(username, password)`, `logout()`, `checkAuth()` |
| `theme` | object | `isDark` (boolean), `toggle()`, `setDark(boolean)` — persisted to localStorage, applies `dark` class on `<html>` |
| `i18n` | i18next instance | Use `useTranslation('your-namespace')` in components; Portal loads plugin locales at startup |
| `navigate` | function | React Router's `navigate(path)` for programmatic navigation |
| `router` | object | `{ location, navigate }` — current location + navigate function |

## Consumer Repo Integration

### Overview

A consumer repo (e.g. `orchestration-center`) needs:
1. A Vite + React + Tailwind project (one-time setup)
2. The `@openan/portal` and `@openan/portal-sdk` packages installed
3. A thin `main.jsx` (4 lines) that renders `PortalApp`
4. A `plugins.config.js` declaring which plugins are enabled
5. Plugin packages (the actual business sub-applications)

After the one-time setup, adding/removing/disabling plugins is just
editing `plugins.config.js` — no framework code changes needed.

### Step 1: Install

```bash
# Published packages (future):
npm install @openan/portal @openan/portal-sdk
npm install react react-dom react-router-dom react-i18next i18next i18next-browser-languagedetector

# Development (local link):
cd openan-website/portal && npm link
cd openan-website/packages/portal-sdk && npm link
cd your-consumer-repo
npm link @openan/portal @openan/portal-sdk
```

### Step 2: Consumer repo structure

```
your-repo/
├── openan-app/                         ← Thin app (replaces old workflow-designer)
│   ├── package.json                    ← Depends on @openan/portal
│   ├── vite.config.js                 ← React plugin + backend proxy
│   ├── index.html
│   ├── tailwind.config.js             ← Content paths include Portal + plugin sources
│   ├── postcss.config.js
│   └── src/
│       ├── main.jsx                    ← 4 lines: import PortalApp + render
│       └── plugins.config.js          ← Declare which plugins are enabled
│
├── plugins/                            ← Your business sub-applications
│   ├── registry-center/
│   │   ├── package.json
│   │   ├── plugin.manifest.js          ← Declare menu, routes, i18n
│   │   └── src/
│   │       ├── index.jsx               ← Plugin component
│   │       └── locales/
│   │           ├── en.json
│   │           └── zh.json
│   ├── orchestration-center/
│   │   └── ...
│   └── ...
│
└── (backend code, unchanged)
```

### Step 3: Consumer `main.jsx`

```jsx
import { createRoot } from 'react-dom/client';
import { PortalApp } from '@openan/portal';
import '@openan/portal/style.css';
import pluginsConfig from './plugins.config.js';

createRoot(document.getElementById('root')).render(
    <PortalApp pluginsConfig={pluginsConfig} />
);
```

`PortalApp` internally includes:
- `<BrowserRouter>` (React Router)
- `<ThemeProvider>` (dark/light, localStorage)
- `<AuthProvider>` (login/logout/auth-check via backend cookie)
- `<PortalShell>` (plugin loading, dynamic Header, route rendering with
  `<Suspense>` + `<ErrorBoundary>`)
- i18n initialization (base translations + plugin namespace loading)

### Step 4: Consumer `plugins.config.js`

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
            enabled: false,  // Disabled — tree-shaken, never imported
            manifest: () => import('./plugins/skill-center/plugin.manifest.js'),
        },
    ],
};
```

Disabled plugins are never imported (Vite tree-shakes them in production
builds). This enables on-demand composition for different delivery scenarios.

### Step 5: Consumer `vite.config.js`

```js
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    server: {
        port: 3003,
        // Gateway proxy — strips /api/orchestrate prefix and forwards to backend.
        // The Portal's API client uses gateway mode by default.
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

### Step 6: Consumer `tailwind.config.js`

```js
export default {
    darkMode: 'class',
    content: [
        './index.html',
        './src/**/*.{js,jsx}',
        './plugins/*/src/**/*.{js,jsx}',
        // ── Critical: include Portal source so Tailwind generates
        //    classes used by Portal components (Header, Login, etc.) ──
        './node_modules/@openan/portal/src/**/*.{js,jsx}',
    ],
    theme: { extend: {} },
    plugins: [],
};
```

## What PortalApp Handles (vs. What Plugins Handle)

| Concern | Handled by | How |
|---------|-----------|-----|
| Routing (URL → plugin view) | PortalApp | React Router, lazy-loaded `<Route>` |
| Navigation bar (menu buttons) | PortalApp | Auto-generated from plugin manifests (`menu[]`) |
| Authentication (login/logout) | PortalApp | `AuthContext` → backend `/auth/*` endpoints, httpOnly cookie |
| Theme (dark/light) | PortalApp | `ThemeContext`, `localStorage`, `dark` class on `<html>` |
| i18n base (nav, login, common) | PortalApp | Base translations in `portal/src/i18n/` |
| Plugin i18n loading | PortalApp | `loadPluginI18n()` at startup, per-plugin namespace |
| API client (gateway, cookie) | PortalApp | Shared axios instance via `usePortalContext().api` |
| Error isolation | PortalApp | `<ErrorBoundary>` per plugin route |
| Lazy loading | PortalApp | `React.lazy()` per route, `<Suspense>` fallback |
| **Plugin business logic** | **Plugin** | Component internals (state, effects, data processing) |
| **Plugin-specific API calls** | **Plugin** | Uses `usePortalContext().api` with own endpoints |
| **Plugin-specific i18n** | **Plugin** | Own locale files, own namespace |
| **Plugin UI/components** | **Plugin** | Own JSX, Tailwind classes, sub-components |

## Enable / Disable / Add / Remove Plugins

All controlled by `plugins.config.js` — no code changes to PortalApp:

```js
// Add a new plugin — add one entry:
{
    id: 'analytics-dashboard',
    enabled: true,
    manifest: () => import('./plugins/analytics-dashboard/plugin.manifest.js'),
}

// Remove for a specific delivery — set enabled: false:
{
    id: 'skill-center',
    enabled: false,
    manifest: () => import('./plugins/skill-center/plugin.manifest.js'),
}
```

The Portal's navigation bar updates automatically — menu buttons are
generated from the enabled plugins' manifests.

## Standalone Plugin Mode

Each plugin can run in isolation for development, without the full Portal
shell. Uses `MockPortal` from `@openan/portal-sdk/standalone`:

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

`MockPortal` provides a minimal `PortalContext` with mock values (admin
user, dark theme, etc.) so the plugin can render and be developed
independently.

## Framework Development

```bash
# Install all workspace packages
npm install

# Start the Portal dev server (loads mock hello-portal plugin)
npm run dev

# Build for production
npm run build

# Lint
npm run lint
```

The Portal dev server runs at http://localhost:3003 and proxies
`/api/orchestrate/` to the backend at http://127.0.0.1:5001.

### Verification Results

```
npm install    ✓  400+ packages
npm run build  ✓  1838 modules transformed, ~1s
npm run lint   ✓  0 errors
npm run dev    ✓  Vite ready at http://localhost:3003 in ~280ms
```

Build output shows the plugin architecture working:
- `plugin.manifest-*.js` — Plugin manifest as separate chunk (dynamically loaded)
- `src-*.js` — Plugin component as lazy chunk
- `en-*.js`, `zh-*.js` — Plugin i18n locales as on-demand chunks
- `index-*.js` — Main Portal bundle

## Design Decisions

### 1. Build-time integration (workspace aliases) over runtime (Module Federation)

Disabled plugins are controlled via dynamic `import()` in `plugins.config.js`
— Vite tree-shakes them in production. All plugins are released uniformly with
the Portal (per issue #77 No-Goals: no independent version management).

Future evolution: switch to Module Federation for runtime plugin loading
without rebuilding the Portal.

### 2. Route-driven navigation over state-driven tab switching

Before: `activeTab` state in `App.jsx`, URL always `/`.
After: React Router routes (`/registry`, `/orchestration`, etc.) — URLs are
shareable and bookmarkable.

### 3. Plugin isolation via backend APIs

Plugins do not share frontend state or an event bus (per issue #77 No-Goals).
Cross-plugin communication happens through backend APIs.

### 4. JSX in `.jsx`, plain JS in `.js`

Follows the existing project convention (`AGENTS.md`: "Frontend is JS/JSX,
not TypeScript"). Files containing JSX use `.jsx` extension; the portal-sdk's
`plugin-context.js` is a `.js` shim that re-exports from `.jsx`.

### 5. Peer dependencies for publishable packages

`react`, `react-dom`, `react-router-dom`, `react-i18next`, `i18next` are
declared as `peerDependencies` in `@openan/portal` — the consumer provides
a single React instance, preventing hooks breakage from duplicate React.

## Migration Impact (P3: Existing Business Modules → Plugins)

When migrating existing modules from the monolithic `workflow-designer/` to
plugins, the impact is:

### Zero Impact (unchanged)

- **Backend API** — all endpoints, auth, SSE unchanged
- **Business logic** — component internals (state, effects, data processing)
- **UI/UX** — same Tailwind classes, same layout, same interaction
- **React Flow** — workflow designer DAG canvas unchanged
- **SSE streaming** — execution center EventSource unchanged

### Minimal Change (code organization, not functionality)

| Change | Before | After | Effort |
|--------|--------|-------|--------|
| Component prop source | `isDark`, `t` from props | `usePortalContext()` + `useTranslation('namespace')` | 2-3 lines per root component |
| Sub-component prop drilling | Parent passes `isDark` to children | **Unchanged** — parent gets it from context, passes as before | Zero |
| API import path | `import { fn } from '@/service/api.js'` | `import { fn } from './service/api.js'` (plugin-local) | Import path only |
| API function signatures | `getWorkflows()` | `getWorkflows()` (identical) | Zero |
| i18n keys | `t('registry.title')` (global) | `t('title')` (namespaced) | Remove prefix |
| File location | `components/registry_center/` | `plugins/registry-center/src/` | Move files |
| Navigation | State-driven tab (`activeTab`) | URL route (`/registry`) | Improved — shareable URLs |
| Build | Single project | Monorepo workspace | Dockerfile path changes |

### Cross-Module Dependencies

The execution center currently imports from the orchestration center:
```jsx
import { transformWorkflowToReactFlow } from '@/components/orchestration_center/workflow/utils/index.jsx';
import UnifiedWorkflow from '../orchestration_center/workflow/index.jsx';
```

**Solution**: Extract shared workflow components into a `@openan/shared-workflow`
package that both plugins depend on.

### API Function Distribution

| Functions | Used by | Package |
|-----------|---------|---------|
| `authCheck`, `login`, `logout`, `register`, `changePassword` | Portal Shell | `@openan/portal` (already included) |
| `getAgentCards` | 3 plugins | `@openan/shared-api` (shared) |
| `getWorkflows`, `parsePdf`, `handlePlan`, `generateWorkflowFromIntent`, etc. | Orchestration Center | Plugin-local |
| `matchWorkflows`, `getStartProcessStreamUrl`, `getExecutionRecords`, etc. | Execution Center | Plugin-local |

### i18n Key Distribution (282 keys total)

| Key group | Count | Destination |
|-----------|-------|-------------|
| `nav`, `login`, `common`, `settings`, `error`, `error_boundary` | 48 | `@openan/portal` base |
| `registry`, `agent_profile` | 43 | `plugins/registry-center/src/locales/` |
| `orchestration`, `workflow`, `workflow_empty`, `node_label` | 76 | `plugins/orchestration-center/src/locales/` |
| `execution` | 91 | `plugins/execution-center/src/locales/` |
| `skills` | 22 | `plugins/skill-center/src/locales/` |

## Issue #77 Compliance

| Goal | Status |
|------|--------|
| Independent `openan-website` frontend framework project | ✅ This repo |
| Pluggable architecture: navigation, auth, theme, i18n, plugin registration | ✅ PortalApp |
| Plugin integration spec (routes, menu, permissions) | ✅ plugin.manifest.js |
| Each sub-application as independent plugin | ✅ Plugin spec + config |
| Config file for on-demand composition | ✅ plugins.config.js |
| Standard integration spec for future extensions (Skill Center) | ✅ Plugin spec |
| Each sub-project supports standalone mode | ✅ MockPortal |
| One-click dev script | ✅ `scripts/dev-all.js` |

| No-Goal | Compliance |
|---------|------------|
| No cross-sub-application state sharing / event bus | ✅ Plugins communicate via backend APIs |
| No independent version management | ✅ Build-time integration, uniform release |
| No backend API layer changes | ✅ Backend unchanged |
