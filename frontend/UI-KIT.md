# Verano UI kit

What the foundation provides, so a feature can be built without reading the shared code. Import paths use the `@/` alias (`src/`).

## Rules in one place

- **Palette**: never change colours in `src/styles/tokens.css`. Use the existing Tailwind tokens (`bg-card`, `text-text-secondary`, `text-lagoon-strong`, `bg-lagoon-soft`, `text-success-strong`, `text-danger-strong`, `ring-border`, ...). shadcn's `--sidebar-*` variables are mapped onto the same palette in `globals.css`.
- **Names and routes** come from `src/lib/nav.ts`. Never type a page name twice; import it.
- **Motion**: only to answer an action or show what changed. Use `motion/react` (`motion.div`, `AnimatePresence`) and Magic UI (`NumberTicker`, `AnimatedList`, `BorderBeam`, `AnimatedBeam`, `AnimatedCircularProgressBar` in `@/components/ui/*`). No entrance animation on every section, no hover animation on every card. `MotionProvider` (mounted for you) sets `reducedMotion="user"`; in plain CSS wrap animation in `@media (prefers-reduced-motion: no-preference)`. Use `useReducedMotion()` from `motion/react` when you drive animation by hand.
- **Responsive**: usable at 1440, 1280, 1024, 768 and 390px, and at 125 to 150% zoom. The page must never scroll sideways. Use `min-w-0` on flex children, `flex-wrap`, `grid sm:grid-cols-2 lg:grid-cols-3`, and `overflow-x-auto` on a wrapper around anything that is wider than a phone (code, wide tables). Tap targets on phones are at least 40px (`min-h-10` / `h-10`; Button `size="lg"` is 40px; `size="sm"` is 28px, so add `className="min-h-10"` for important actions on phones).
- **Plain language**: sentence case, names say what a thing is, buttons say what happens ("Run the test", not "Submit"), errors say what went wrong and how to fix it.
- **Accessibility**: visible focus (the primitives already have it), a label on every control, headings in order (one `h1` per page, from `PageIntro`), colour never the only signal.
- **No extra dependencies** in feature branches; ask the foundation.

## The frame (you do not build it)

`src/app/projects/[projectId]/layout.tsx` wraps every project page in `ProjectShell`; `/workspace`, `/tokens`, `/activity` get `AccountFrame` from their layouts; `/projects` wraps itself. You only render page content. Do not render your own header, logo, account menu or `<main>` (the frame supplies `<main id="main">`). Content padding is already applied; use `mx-auto w-full max-w-*` for a reading width.

- 1280px and up: full sidebar. 1024 to 1279px: icon rail (the menu button expands it). Under 1024px: a drawer opened with the "Open menu" button.
- Header: menu button, breadcrumb, spend pill, search (Cmd/Ctrl+K), theme menu, one account menu (email, Usage and spend, Workspace, API tokens, Sign out).
- Sidebar groups are Set up, Test, Improve, Trust, Production, Help, with done marks and a "Next" tag on the guided pages.

Tests: `goToPage(page, /^Compare results/)`, `openAccountMenu`, `signOut`, `chooseTheme` are in `tests/helpers.ts`.

## Navigation: `@/lib/nav`

```ts
import {
  PROJECT_NAV,
  ALL_PROJECT_PAGES,
  ACCOUNT_NAV,
  pageTitleForPath,
  projectHref,
  docsUrl,
  itemsOf,
} from "@/lib/nav"

const page = ALL_PROJECT_PAGES.find((p) => p.key === "results")! // { label, subtitle, icon, segment, group, learnMore }
page.label // "Compare results"
projectHref(projectId, page) // "/projects/<id>/results"
pageTitleForPath("/projects/p1/results") // "Compare results"
docsUrl("results") // "https://docs.verano.example/results"  (DOCS_BASE_URL is the one constant)
```

Use `page.label` as the `PageIntro` title and `page.subtitle` as a basis for its sentence. `STEPS` in `@/lib/steps` is derived from it.

## PageIntro: `@/components/common/page-intro`

Every page opens with it. One `h1`, what the page is, "Use it when", "You get", one primary action, "Learn more". Collapses to one line when `hasContent` is true or after "Hide help" (remembered per `storageKey` in localStorage).

```tsx
<PageIntro
  storageKey="results"
  title="Compare results"
  what="Quality, cost and speed for every model, side by side."
  whenToUse="a test run has finished"
  youGet="a ranking and the cheapest model that is good enough"
  primaryAction={<Button size="lg">Run the test</Button>}
  learnMore="results"
  hasContent={runs.length > 0}
/>
```

## Wizard: `@/components/common/wizard`

Stepped flow, one decision per screen, with a progress indicator (dots on wide screens, "Step 2 of 4" plus a bar on phones), Back and Next, animated transitions. `validate` returns `true` or the message that blocks Next (may be async). Step content is mounted only while current, so keep state in the parent.

```tsx
<Wizard
  finishLabel="Create project"
  onCancel={() => router.back()}
  onFinish={async () => {
    await create.mutateAsync(name)
  }}
  steps={[
    {
      id: "name",
      title: "Name it",
      description: "Pick a name you will recognise.",
      content: <Input aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} />,
      validate: () => (name.trim() ? true : "Enter a name for the project."),
    },
    { id: "confirm", title: "Confirm", content: <p>Create “{name}”?</p> },
  ]}
/>
```

Controlled mode: pass `step` and `onStepChange`.

## AnimatedNumber: `@/components/common/animated-number`

Counts up once when it appears; plain text under reduced motion, or when `animate={false}`, or when you pass `format` (money, units). Use for a few headline numbers only.

```tsx
<AnimatedNumber value={87} suffix="%" className="text-3xl font-semibold" />
<AnimatedNumber value={cost} format={formatCost} />
```

## EmptyState: `@/components/common/empty-state`

An invitation, never a blank panel: icon, title, one sentence, one primary action.

```tsx
<EmptyState
  icon={FileText}
  title="No prompt yet"
  description="Write the instructions you want to test."
  action={<Button size="lg">Write your prompt</Button>}
/>
```

## ResponsiveTable: `@/components/common/responsive-table`

A table from 768px, a stack of cards below (the `primary` column is the card title; the other columns become "Label: value" lines). For big sortable tables keep TanStack Table and wrap it in `overflow-x-auto`.

```tsx
<ResponsiveTable
  caption="Models and their cost"
  rows={models}
  rowKey={(m) => m.id}
  columns={[
    { id: "name", header: "Model", primary: true, cell: (m) => m.name },
    { id: "cost", header: "Cost", align: "right", cell: (m) => formatCost(m.cost) },
  ]}
  empty={<EmptyState title="No models" description="Connect a provider first." />}
/>
```

## useBreakpoint: `@/components/common/use-breakpoint`

Change what renders, not just styling (prefer CSS classes when styling is enough). Bands: sm 640, md 768, lg 1024, xl 1280, 2xl 1536. "base" on the server and first render.

```tsx
const { current, atLeast } = useBreakpoint()
return atLeast("lg") ? <SideBySide /> : <Stacked />
```

## CommandPalette: `@/components/common/command-palette`

Mounted by the frame. Cmd/Ctrl+K lists every page of the current project, the account pages and the user's projects. Open it from your own button with `openCommandPalette()`.

## MotionProvider

Mounted in `AppProviders` with `MotionConfig reducedMotion="user"`. Nothing to do.

## shadcn and Magic UI components: `@/components/ui/*`

Base UI based ("base-nova"). Present: accordion, alert, alert-dialog, animated-beam, animated-circular-progress-bar, animated-list, avatar, badge, border-beam, breadcrumb, button, card, chart, checkbox, collapsible, combobox, command, dialog, dropdown-menu, empty, field, input, input-group, kbd, label, number-ticker, popover, progress, radio-group, scroll-area, select, separator, sheet, sidebar, skeleton, slider, sonner (toasts), spinner, switch, table, tabs, textarea, toggle, toggle-group, tooltip.

Base UI uses a `render` prop instead of `asChild`: `<DropdownMenuItem render={<Link href="/x" />}>`, `<DropdownMenuTrigger render={<Button />}>`. Charts: `chart.tsx` (`ChartContainer`, `ChartTooltip`, `ChartLegend`) over Recharts; theme series with `var(--color-chart-1)`; always add a text or table alternative.

## Other shared pieces

`Section`, `StatTile`, `StatusBadge`, `ErrorMessage`, `CopyButton`, `Markdown`, `DiffView`, `PageActions` (sticky bottom primary action), `ThemeSwitch` (already in the header) are unchanged. `StepHeader` and `UsageGuide` are the old page openers: replace them with `PageIntro` on the pages you own.

## Testing

- `*.test.ts` run in node; `*.test.tsx` run in jsdom with Testing Library (`@testing-library/react`, `user-event`, jest-dom matchers are preloaded).
- `setViewport(390)` from `@/test/viewport` changes `innerWidth` and `matchMedia` for responsive components.
- Browser tests: copy the pattern of `tests/new-screens.spec.ts`; `tests/responsive.spec.ts` keeps ONE array of routes at its top (`PROJECT_ROUTES`, `ACCOUNT_ROUTES`): add yours there.
