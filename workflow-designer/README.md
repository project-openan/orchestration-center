# Prototype: Workflow Designer

A modern, high-performance orchestration platform for multi-agent systems. This prototype provides a visual interface for designing workflows and managing agent registries.

## Runtime Modes

The website runs **standalone** or integrates into the **OpenAN Portal** as a plugin:

### Standalone (own shell)

```bash
npm install
npm run dev          # → http://localhost:3003 (Header / theme / i18n included)
```

### OpenAN Portal plugin (UMD artifact)

```bash
npm run build:plugin
# → dist-plugin/
#   ├── index.js              UMD, sets window.__OPENAN_PLUGIN__orchestration_center
#   ├── index.css             compiled styles
#   └── plugin.manifest.json  runtime metadata
```

The Portal loads the artifact locally (copy under its `public/plugins/orchestration-center/`) or remotely (served by this repo with CORS). React / react-dom / react-i18next / @openan/portal-sdk stay external — the Portal provides them at runtime.

In plugin mode, `src/index.jsx` consumes `usePortalContext()` (theme + api) and routes every service-layer request through the Portal's axios instance via `setApiClient()`; standalone mode keeps the local instance with the same-origin dev proxy.

## 🚀 Features

- **Visual Workflow Designer**: Drag-and-drop interface for building complex agent orchestrations, powered by [React Flow](https://reactflow.dev/).
- **Automatic Layout**: Integrated [Dagre](https://github.com/dagrejs/dagre) engine for smart, automatic node positioning and graph organization.
- **Data Transformation**: Seamless conversion between visual graph representations and structured PSOP JSON workflow definitions.
- **Theme Support**: Seamless switching between Dark and Light modes.
- **Internationalization**: Full support for English and Chinese (Mandarin).
- **Modern Tech Stack**: Built with Vite, React, and Tailwind CSS for a fast and responsive experience.

## 🛠 Tech Stack

- **Framework**: [React 18](https://reactjs.org/)
- **Bundler**: [Vite](https://vitejs.dev/)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/)
- **Graph Engine**: [@xyflow/react (React Flow)](https://reactflow.dev/)
- **Animations**: [Framer Motion](https://www.framer.com/motion/)
- **I18n**: [i18next](https://www.i18next.com/)
- **Testing**: [Vitest](https://vitest.dev/)

## 📦 Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) (version 18 or higher recommended)
- [Yarn](https://yarnpkg.com/) or [npm](https://www.npmjs.com/)

### Installation

```bash
# Clone the repository and navigate to the directory
cd workflow-designer

# Install dependencies
yarn install
```

### Development

```bash
# Start the development server
yarn dev
```

### Build

```bash
# Build for production
yarn build

# Preview production build
yarn preview
```

## 📂 Project Structure

- `src/components/orchestration_center`: Core workflow designer implementation.
- `src/components/registry_center`: Agent registry management components.
- `src/locales`: Translation files for i18n.
- `src/service`: API client and services.

## 🧪 Testing

```bash
# Run unit tests with coverage
yarn coverage
```

---

*Part of the Orchestration Center project.*
