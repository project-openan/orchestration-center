# OpenAN Portal Unified Web Framework — A Composable Pluggable Portal

---

## Page 1 · Cover

# OpenAN Portal
## Unified Web Framework — Pluggable Portal Architecture

**One Framework Shell × N Business Plugins = A Composable OpenAN Frontend**

Issue #77 · Provide a Unified Web Framework (Pluggable Portal)

2026-08

---

## Page 2 · The Idea in One Sentence

## Core Concept: The Framework is a Shell, Business Logic is Plugins

```
┌─────────────────────────────────────────────────────────┐
│                 OpenAN Portal (Shell)                    │
│                                                         │
│   NavBar   Auth   Theme   i18n   Plugin Manager   Router │
│                                                         │
│   ┌───────────┐ ┌───────────┐ ┌───────────┐            │
│   │ Registry   │ │Orchestration│ │ Execution │  ← Plugins│
│   │ Plugin     │ │ Plugin     │ │ Plugin     │            │
│   └───────────┘ └───────────┘ └───────────┘            │
└─────────────────────────────────────────────────────────┘
```

**The Portal provides only the skeleton — zero business logic**

**Any web page → write a manifest → register with the Portal → integration done**

---

## Page 3 · The Composable Architecture

## Split or Combined — Decided by Configuration

### Combined — Unified Portal Mode

All plugins register into a single Portal with unified navigation, unified login, unified theming

```
Portal (:3003)
 ├── /registry      Registry Center plugin
 ├── /orchestrate   Orchestration Center plugin
 ├── /execution     Execution Center plugin
 └── /demos         Demo plugin
```

### Split — Standalone Mode

Each plugin is an independent npm package that can run without the Portal

```
registry-center standalone → wrapped in MockPortal, dev directly
orchestration-center standalone → same
```

### Key Mechanisms

| Capability | Implementation |
|------------|----------------|
| Combined: unified integration | Drop a folder into `plugins/` — auto-discovered |
| Split: standalone operation | Each plugin has `standalone.jsx` + `MockPortal` |
| Combined: shared services | `usePortalContext()` provides api/auth/theme/i18n |
| Split: no cross-dependencies | Plugins share no state; they communicate via their own backend APIs |

---

## Page 4 · How to Integrate an Existing Web Service

## 3 Steps to Integrate — Zero Business Logic Changes, Zero Portal Code Changes

Using the **Registry Center** as an example (original component: 395 lines):

### Step 1: Create the plugin folder + write the manifest `plugin.manifest.js`

Declare "who I am, what my menu looks like, what my route is, what translations I have, where my backend is"

```
plugins/
└── my-service/                  ← drop it here, auto-registered
    ├── package.json
    ├── plugin.manifest.js
    └── src/
        ├── index.jsx            ← your page component (moved as-is)
        └── locales/
```

```js
export default {
    id: 'registry-center',
    name: 'Registry Center',
    version: '0.1.0',
    backend: { gateway: '/api/registry' },   // declare its own backend
    menu: [{ id: 'agents', labelKey: 'registry-center:registry.title',
             icon: LayoutDashboard, order: 1, route: '/registry' }],
    routes: [{ path: '/registry',
               component: () => import('./src/index.jsx') }],
    i18n: { namespace: 'registry-center', resources: {...} },
};
```

### Step 2: Change the component signature (2 lines — in the plugin's own code)

```jsx
// Before: receives props from App.jsx
const AgentRegistry = ({ isDark, t }) => { ... }

// After: obtains services from PortalContext
const AgentRegistry = () => {
    const { theme, api } = usePortalContext();       // ← add this line
    const { t } = useTranslation('registry-center'); // ← add this line
    const isDark = theme.isDark;
    // The 395 lines of business logic, UI, and CSS below remain unchanged
};
```

### Step 3: Change the API call (1 line — in the plugin's own code)

```jsx
// Before: import { getAgentCards } from "@/service/api.js"
const response = await api.get('/rest/v1/registry/agent-cards');
```

**Done. No registration needed, no Portal code changes whatsoever.**

### Change Boundary: Who Changes What

All changes in Steps 2 and 3 happen in the **plugin's own files** (e.g. `plugins/registry-center/src/index.jsx`),
made by the plugin's own developers — no knowledge of Portal internals required:

```
Portal (framework, never modified)    Business plugins (each modifies its own)
┌──────────────────────┐              ┌────────────────────────────┐
│ PortalApp.jsx        │              │ plugins/registry-center/   │
│ Header / Login       │              │   └── src/index.jsx        │
│ ThemeContext         │  provides    │     ↓ registry devs change │
│ AuthContext          │ ─────────→   │     1. component props→hook│
│ api.js + createApi() │    the hook  │     2. API call paths      │
│ plugin-discovery     │              │     3. own locales/        │
└──────────────────────┘              └────────────────────────────┘
     provides usePortalContext()             consumes usePortalContext()
```

| Change | Where | Who |
|--------|-------|-----|
| Write `plugin.manifest.js` | Plugin folder | Plugin developer |
| Component signature props → hooks | Plugin `src/index.jsx` | Plugin developer |
| API call paths | Plugin `src/index.jsx` | Plugin developer |
| i18n locale files | Plugin `src/locales/` | Plugin developer |
| Plugin registration | `plugins/` folder (auto-discovered on drop) | Nobody |
| Portal framework code | — | **Nobody touches it** |

The Registry Center edits `plugins/registry-center/src/index.jsx`, the Orchestration Center edits `plugins/orchestration-center/src/index.jsx` — each independently, with zero impact on each other.

### Convention-Based Auto-Discovery (Zero-Config Registration)

The Portal ships with a built-in `openan-plugin-discovery` Vite plugin:

```
At startup / build → fs scans plugins/<name>/plugin.manifest.js
                   → generates the virtual module virtual:openan-plugins
                   → disabled plugins get no import at all (true tree-shaking)
                   → drop a new folder while dev server runs → auto hot-reload
```

| Scenario | Action | Portal code changed? |
|----------|--------|---------------------|
| Add a plugin | Drop the folder into `plugins/` | ❌ |
| Tailor a delivery | Edit `plugins/plugin-overrides.json` (plain JSON, ops-friendly) | ❌ |
| Disable at runtime | Toggle the switch in the Plugin Manager UI | ❌ |
| Remove a plugin | Delete the folder | ❌ |

### Migration Results

| Dimension | Change |
|-----------|--------|
| Lines modified | **3 spots, ~5 lines total** |
| Portal code changes | **Zero** |
| Business logic | **Zero changes** |
| UI/UX | **Zero changes** |
| Sub-components | **Zero changes** (isDark still passed as prop from parent) |

---

## Page 5 · Plugin Definition Spec

## One Plugin = One npm Package = One Manifest

### Manifest Fields

```js
export default {
    // ── Identity ──
    id: 'registry-center',              // unique ID
    name: 'Registry Center',            // display name
    version: '0.1.0',                   // semantic version

    // ── Backend declaration (optional) ──
    backend: { gateway: '/api/registry' },
    // The Portal creates a dedicated axios instance for this plugin
    // accessed via usePortalContext().api

    // ── Menu ── navigation buttons auto-generated
    menu: [{
        id: 'agents',
        labelKey: 'registry-center:registry.title',  // i18n key
        icon: LayoutDashboard,          // nav icon
        order: 1,                       // nav sort order
        route: '/registry',             // route path
    }],

    // ── Routes ── auto-registered with React Router
    routes: [{
        path: '/registry',
        component: () => import('./src/index.jsx'),  // lazy-loaded
        menuId: 'agents',
    }],

    // ── i18n ── isolated namespace, no key collisions
    i18n: {
        namespace: 'registry-center',
        resources: {
            en: () => import('./src/locales/en.json'),
            zh: () => import('./src/locales/zh.json'),
        },
    },

    // ── Standalone operation (optional) ──
    standalone: { enabled: true, entry: './src/standalone.jsx' },
};
```

### PortalContext — Framework Services Available to Plugins

| Service | Type | Description |
|---------|------|-------------|
| `api` | axios instance | Created per plugin's backend.gateway, cookie auto-attached |
| `auth` | object | User, role, auth state, login/logout |
| `theme` | object | Dark/light toggle |
| `i18n` | i18next | Plugin uses its own namespace |
| `navigate` | function | Programmatic navigation |

---

## Page 6 · Plugin Loading & Runtime Flow

## The Complete Pipeline from Startup to Rendering

```
At Vite startup / build time
     │
     ▼
① Plugin auto-discovery (openan-plugin-discovery)
   ├── fs scans plugins/<name>/plugin.manifest.js
   ├── Reads plugin-overrides.json to filter disabled entries
   ├── Generates the virtual module virtual:openan-plugins
   │   (disabled plugins get no import at all → true tree-shaking)
     │
     ▼
Browser loads Portal (:3003)
     │
     ▼
② PortalApp boots
   ├── Initializes i18n base
   ├── Auth check (/auth/check)
     │
     ▼
③ Load plugin manifests
   ├── Imports the virtual module (auto-discovered plugin list)
   ├── Dynamic import() of each manifest
   ├── validateManifest() field validation
     │
     ▼
④ Load plugin i18n
   ├── Reads manifest.i18n.resources
   ├── On-demand load of en.json / zh.json
   ├── Registers into isolated namespace
     │
     ▼
⑤ Assemble PortalContext
   ├── Checks manifest.backend.gateway
   ├── Present → createApi(gateway) creates dedicated axios
   ├── Absent → uses default API instance
     │
     ▼
⑥ Render Portal Shell
   ├── Header generates nav buttons from manifest.menu[]
   ├── Routes registered to React Router from manifest.routes[]
   ├── Each route wrapped in PortalProvider + ErrorBoundary + Suspense
     │
     ▼
⑦ Lazy-load plugin components
   ├── User clicks nav → React.lazy() triggers import()
   ├── Plugin component loaded on demand as a separate chunk
   ├── Component calls usePortalContext() for shared services
   └── A plugin crash affects only itself (ErrorBoundary isolation)
```

### Disabled Plugin Loading Logic

```
"enabled": false in plugin-overrides.json
     │
     ▼
Skipped entirely at discovery time (no import generated)
     │
     ▼
Completely tree-shaken in production builds
     │
     ▼
Plugin code totally absent from the bundle
```

---

## Page 7 · Code Directory Structure

## Framework Repository: openan-website/

```
openan-website/                          ← Framework repo (standalone)
│
├── packages/                            ← Shared packages
│   ├── portal-sdk/          6 files     ← @openan/portal-sdk
│   │   └── src/
│   │       ├── index.js                 Library entry
│   │       ├── plugin-context.jsx       PortalContext + usePortalContext
│   │       ├── plugin-manifest.js       Manifest interface + validator
│   │       ├── config-loader.js         loadEnabledPlugins()
│   │       └── standalone.jsx           MockPortal (for standalone mode)
│   │
│   └── shared-workflow/     14 files    ← @openan/shared-workflow
│       └── src/                         UnifiedWorkflow canvas
│           ├── index.jsx                (shared by orchestration + execution)
│           ├── utils/                   transformWorkflowToReactFlow
│           └── CustomNodes/ toolbar/ sidebar/ ...
│
├── portal/                  20 files    ← @openan/portal (framework shell)
│   ├── vite.config.js                   Vite config + multi-backend proxy
│   ├── tailwind.config.js               content includes all plugin sources
│   └── src/
│       ├── index.js                     Library entry: export { PortalApp }
│       ├── PortalApp.jsx                Reusable shell (accepts pluginsConfig)
│       ├── plugins.config.js            Plugin enable/disable config ★
│       ├── auth/                        AuthContext + Login
│       ├── theme/                       ThemeContext
│       ├── i18n/                        Base translations + plugin namespace loading
│       ├── service/api.js               Shared axios + createApi(gateway)
│       └── components/
│           ├── header/                  Dynamic nav (generated from manifests)
│           ├── plugin_manager/           Runtime enable/disable/inspect config
│           └── error_boundary/           Per-plugin error isolation
│
├── plugins/                            ← Business plugins ★
│   ├── registry-center/     5 files     ← Own backend (:5000)
│   ├── orchestration-center/ 4 files    ← Default backend (:5001)
│   ├── execution-center/    5 files     ← Default backend (:5001)
│   ├── demo-showcase/       10 files    ← No backend, demo only
│   └── hello-portal/        4 files     ← Framework validation mock
│
├── scripts/
│   ├── dev-all.js                       One-click startup
│   └── mock-backend.mjs                 Dual backend mocks (:5000 + :5001)
│
├── docs/                               Design documents
├── README.md / README_zh.md            Bilingual docs
└── package.json                         npm workspaces root
```

---

## Page 8 · Business Plugin Directory Structure

## Registry Center Plugin (Own Backend)

```
plugins/registry-center/
├── package.json                  ← @openan-plugins/registry-center
│                                    exports: ./plugin.manifest.js
├── plugin.manifest.js            ← Plugin declaration ★ core
│                                    id / menu / routes / i18n / backend
├── vite.config.js                ← Standalone build config (independently deployable)
├── tsconfig.json
├── index.html                    ← Standalone runtime entry
└── src/
    ├── index.jsx                 ← Main component (usePortalContext)
    ├── standalone.jsx            ← Standalone entry (MockPortal wrapper)
    ├── agentcard_visualization/  ← AgentCard detail component
    ├── code_inspector/           ← JSON viewer
    └── locales/
        ├── en.json               ← Plugin-specific translations
        └── zh.json
```

## Orchestration Center Plugin (Default Backend)

```
plugins/orchestration-center/
├── package.json                  ← @openan-plugins/orchestration-center
├── plugin.manifest.js            ← Declares menu/routes/i18n (no backend)
├── vite.config.js
└── src/
    ├── index.jsx                 ← Main component
    ├── standalone.jsx            ← Standalone entry
    ├── packages/                 ← SolutionPackage upload
    └── locales/
        ├── en.json
        └── zh.json

Dependency: @openan/shared-workflow  ← Shared workflow canvas
                                        (shared with Execution Center, no duplication)
```

## Plugin Directory Commonalities

| File | Required | Purpose |
|------|----------|---------|
| `plugin.manifest.js` | ✅ | Declares menu, routes, i18n, backend |
| `src/index.jsx` | ✅ | Plugin main component |
| `src/locales/*.json` | ✅ | Plugin-specific translations |
| `src/standalone.jsx` | Optional | Run without the Portal |
| `vite.config.js` | Optional | Standalone build (independently deployable) |

---

## Page 9 · Multi-Backend & Deployment

## Each Plugin Can Connect Directly to Its Own Backend

```
Browser (:3003)
    │
    ├── /api/registry/*    →  Registry backend (:5000)   ← registry-center plugin
    │                          /rest/v1/registry/agent-cards
    │
    ├── /api/orchestrate/* →  Orchestration backend (:5001) ← orchestration/execution plugins
    │                          /rest/v1/orchestrate/workflows
    │                          /rest/v1/orchestrate/execute (SSE)
    │
    └── (no backend)        →  demo-showcase plugin
```

## Production Deployment (docker-compose)

```yaml
services:
  portal:                        # Framework shell
    build: ./openan-website/portal
    ports: ["3003:80"]
    environment:
      - REGISTRY_URL=http://registry-center:5000
      - BACKEND_URL=http://orchestration-center:5001

  orchestration-center:          # Orchestration Center (backend + plugin)
    build: ./orchestration-center
    ports: ["5001:5001"]

  registry-center:               # Registry Center (standalone service)
    build: ./registry-center
    ports: ["5000:5000"]
```

## Independent Deployment Roadmap

| Phase | Integration | Plugin Deployment |
|-------|-------------|-------------------|
| **Current** | Build-time (workspace) | Built with the Portal, released together |
| **Near-term** | Independent builds + nginx serving | Each built, deployed, and versioned separately |
| **Long-term** | Module Federation | Runtime remote loading, no Portal rebuild needed |

---

## Page 10 · Roadmap & Value Summary

## Verified Results

| Verification Item | Result |
|-------------------|--------|
| Framework build | ✅ 1838 modules, ~1s |
| All 4 plugins load | ✅ Dynamic nav + routing + i18n |
| Plugin standalone mode | ✅ MockPortal standalone |
| Runtime enable/disable | ✅ Persisted in localStorage |
| Multi-backend proxy | ✅ /api/registry + /api/orchestrate |
| Migration cost | ✅ 5 spots per plugin, zero business changes |
| Codebase | 68 files (vs. 40-file monolith, now clearly structured) |

## Core Value

**Composable (Split)** — Every plugin is an independent npm package: independently developed, independently run, independently built, independently deployed

**Combinable (Unified)** — Drop a plugin folder into the directory and it is auto-registered, sharing navigation, auth, theming, and i18n with zero Portal code changes

**Extensible** — Future Skill Center only needs one manifest + a 2-line component signature change; drop the folder in and integration is complete

**Tailorable** — Set `"enabled": false` in `plugin-overrides.json` (plain JSON); automatically tree-shaken at build time

## Next Steps

1. Complete Skill Center plugin migration (spec reuse, ~half a day)
2. Dockerized full-stack deployment verification
3. Publish `@openan/portal` to npm for external consumers
4. Explore independent builds + Module Federation runtime loading
