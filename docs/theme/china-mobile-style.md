# China Mobile visual identity for the workflow designer

This branch restyles the orchestration center frontend to match the China
Mobile group AI-platform reference design. The reference is a light, dense
enterprise UI: a pale blue-grey canvas, white cards with hairline borders and
almost no shadow, a single brand blue for actions, and a 13px base type scale.

The restyle is carried by design tokens, not by a second stylesheet. Component
code keeps reading like Tailwind, and every surface picks up the palette from
`tailwind.config.js`.

## Colour tokens

| Token | Light | Dark | Used for |
|---|---|---|---|
| `cm-canvas` | `#F5F8FE` | `#0C1B2E` (`cm-night`) | application canvas |
| `cm-surface` / `white` | `#FFFFFF` | `zinc-900` `#142843` | cards, panels |
| `cm-line` | `#E1E9F6` | `zinc-700` | card and input borders |
| `cm-line-soft` | `#EAF0F8` | `zinc-800` | dividers inside cards |
| `cm-ink` | `#172D4D` | `zinc-100` | body text |
| `cm-heading` | `#18304D` | `zinc-100` | page and section titles |
| `cm-secondary` | `#506988` | `zinc-300` | secondary text |
| `cm-muted` | `#7188AA` | `zinc-400` | labels, hints |
| `cm-faint` | `#94A9C2` | `zinc-500` | meta text, placeholder |
| `cm-primary` | `#2464E8` | `blue-400` `#6E9DF4` | primary actions, links, active state |
| `cm-primary-hover` | `#1758D7` | — | primary hover |
| `cm-primary-faint` | `#E7F0FF` | `#1D3352` | active nav pill, icon button hover |
| `cm-primary-soft` | `#EEF5FF` | `#1D3352` | selected rows, subtle fills |
| `cm-sky` / `cm-topbar` | `#EAF3FF` / `#E9F3FF` | `zinc-900` | top bar |
| `cm-topbar-line` | `#CDDFF7` | `zinc-800` | top bar hairline |
| `cm-accent` | `#2B61CD` | — | tag text inside cards |
| `cmcc-blue` / `cmcc-green` | `#0084CF` / `#8DC21F` | — | logo artwork only |

`zinc` and `slate` are remapped wholesale to a blue-grey ramp
(`#F5F8FE` → `#0C1B2E`), and `blue` is remapped to the brand ramp, so existing
`bg-zinc-*`, `text-zinc-*`, `border-zinc-*` and `bg-blue-600` utilities already
render on brand. Prefer the `cm-*` names in new code for intent.

## Shape and elevation

| Property | Value | Notes |
|---|---|---|
| Card radius | `rounded-cm` (10px) | `rounded-xl` also resolves to 10px |
| Control radius | `rounded-cm-sm` (7px) | buttons, inputs, tabs |
| Panel radius | `rounded-cm-panel` (11px) | floating designer panels |
| Modal radius | `rounded-3xl` (14px) | dialogs |
| Card shadow | `shadow-card` = `0 3px 14px rgba(37,86,151,.045)` | barely visible |
| Hover shadow | `shadow-card-hover` = `0 8px 20px rgba(29,94,209,.09)` | |
| Panel shadow | `shadow-panel` | floating toolbars/sidebars |

## Type

- Base 13px, page title 18px/700 (`cm-section-title`), card title 14px/700,
  meta 11px, tag 11px, button 13px.
- `font-black` is capped at 700 by a utility override: the reference never uses
  a 900 weight.
- Font stack: Inter, Microsoft YaHei, PingFang SC, system fallbacks.

## Reusable classes (`src/index.css`)

| Class | Purpose |
|---|---|
| `cm-card` | white card, hairline border, soft shadow |
| `cm-card-hover` | lift + brand border on hover |
| `cm-panel` | floating designer panel |
| `cm-chip` / `cm-chip-neutral` | capability pills |
| `cm-btn` / `cm-btn-primary` / `cm-btn-soft` / `cm-icon-btn` | buttons |
| `cm-search` | 39px search field with focus ring |
| `cm-input` | form input |
| `cm-entity-icon` / `cm-entity-icon-square` | 36px entity tile |
| `cm-entity-title` / `cm-entity-meta` | card header type |
| `cm-section-title` / `cm-eyebrow` | page headings |

## Screen patterns

```text
Page header:  [18px title + 12px muted subtitle]            [primary button]
Toolbar:      [search box, flex-1]                          [pill actions]
Card grid:    repeat(3, minmax(0,1fr)), gap 17px
Card:         padding 17px 16px 14px
              [36px icon tile + 14px title + 11px meta]
              [12px summary, line-height 1.6]
              [11px tag row]                    [11px usage + tiny button]
Category rail: 200px, sticky, items 12px,
              active = #EAF2FF bg + #255BCE text + 700 weight
```

Status colours keep their meaning: `emerald` success, `amber` warning,
`rose` error. Decorative accents use the brand ramp; indigo/violet/purple are
remapped to the same blue family.

## Rules for contributors

1. Style only. Do not change data flow, API calls, component props, ids,
   `aria-*`, `data-testid`, or i18n keys.
2. Every surface must still work in dark mode: keep the `dark:` counterpart
   when replacing a class.
3. No new dependencies, no second CSS framework, no inline hex where a token
   exists.
4. Buttons that submit or advance a flow use `cm-btn-primary`; secondary
   actions use `cm-btn`; icon-only actions use `cm-icon-btn`.
5. Prefer `rounded-cm` / `rounded-cm-sm`; avoid `rounded-full` on rectangles
   and avoid radii above 14px.

## Where the theme lives

| Path | Role |
|---|---|
| `workflow-designer/tailwind.config.js` | palette, radii, shadows, gradients, type stack |
| `workflow-designer/src/index.css` | base layer, `cm-*` component classes, React Flow chrome, scrollbars |
| `workflow-designer/src/components/common/brand/index.jsx` | brand mark and wordmark lockup |
| `workflow-designer/src/assets/brand/` | supplied China Mobile artwork (mark, two lockups) |
| `workflow-designer/public/favicon.svg` | mark used as the application icon |

`cm-*` component classes carry their own `dark:` variants, so a component that
uses `cm-card`, `cm-btn`, `cm-search`, `cm-chip` or `cm-entity-icon` is already
dark-mode capable; per-usage `dark:` overrides are only needed for bespoke
surfaces.

## Scope of this branch

- Top bar, account actions and language switch restyled to the reference
  chrome (65px pale-blue bar, light-blue active pill, gradient avatar).
- Login page rebuilt as a brand panel plus credentials card.
- Registry, orchestration, execution and skill pages moved onto the canvas /
  card / entity-head / chip / toolbar patterns above.
- Workflow designer: canvas background, grid and edge colours, floating
  toolbar, node palette, property panel, agent/start/end nodes.
- Chinese-first type stack and a calmer weight ceiling (no 900-weight titles).

