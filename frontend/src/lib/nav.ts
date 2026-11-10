/**
 * The single source of navigation: groups, items, names, subtitles, icons and routes.
 * The sidebar, the breadcrumb, the command palette and the page titles all read from here, so
 * renaming a page means editing one line. Route paths never change; only the words do.
 *
 * Project pages live at `/projects/<id>/<segment>`. Account pages (`ACCOUNT_NAV`) live at the top
 * level. `learnMore` is the slug appended to the docs address (see `docsUrl`).
 */
import {
  Activity,
  BookOpen,
  BrainCircuit,
  ClipboardCheck,
  FileText,
  FlaskConical,
  Gauge,
  History,
  KeyRound,
  LineChart,
  ListChecks,
  Play,
  Plug,
  Radio,
  Settings2,
  ShieldCheck,
  Sparkles,
  Table2,
  type LucideIcon,
} from "lucide-react"

/** Placeholder docs address; change it here and every "Learn more" link follows. */
export const DOCS_BASE_URL = "https://docs.verano.example"

export function docsUrl(slug: string): string {
  return `${DOCS_BASE_URL}/${slug}`
}

export type NavGroupId = "setup" | "test" | "improve" | "trust" | "production" | "help"

export type NavItem = {
  /** Same as the route segment. */
  key: string
  /** The page's name, sentence case. */
  label: string
  /** One line saying what the page is for. */
  subtitle: string
  icon: LucideIcon
  /** Route under /projects/<id>/ . */
  segment: string
  group: NavGroupId
  /** Docs slug for the "Learn more" link. */
  learnMore: string
  /** False for pages that are not built; shown but not clickable. */
  available: boolean
  /** Part of the guided setup path shown with done / current marks. */
  guided: boolean
}

export type NavGroup = { id: NavGroupId; label: string }

export const NAV_GROUPS: NavGroup[] = [
  { id: "setup", label: "Set up" },
  { id: "test", label: "Test" },
  { id: "improve", label: "Improve" },
  { id: "trust", label: "Trust" },
  { id: "production", label: "Production" },
  { id: "help", label: "Help" },
]

function item(
  key: string,
  label: string,
  subtitle: string,
  icon: LucideIcon,
  group: NavGroupId,
  guided = false,
): NavItem {
  return { key, label, subtitle, icon, segment: key, group, learnMore: key, available: true, guided }
}

export const PROJECT_NAV: NavItem[] = [
  item("keys", "Connect models", "Add provider keys and pick the models to test", KeyRound, "setup", true),
  item("prompt", "Write your prompt", "The instructions you want to test", FileText, "setup", true),
  item("data", "Add examples", "Optional files with real inputs and answers", Table2, "setup", true),
  item("tests", "Approve test cases", "Check what the models will be tested on", ListChecks, "setup", true),
  item("run", "Run the test", "Run every model on your test cases", Play, "test", true),
  item("results", "Compare results", "Quality, cost and speed side by side", Gauge, "test", true),
  item(
    "improve",
    "Improve the prompt",
    "Find what fails and test better versions",
    Sparkles,
    "improve",
    true,
  ),
  item("security", "Safety checks", "Try common attacks on your prompt", ShieldCheck, "improve"),
  item(
    "review",
    "Review answers",
    "Mark answers good or bad to see if the judge agrees with you",
    ClipboardCheck,
    "trust",
  ),
  item("logbook", "History", "Every answer and every model call", History, "trust"),
  item("apps", "Test your own app", "Test a chatbot, API or RAG app you already run", Plug, "production"),
  item(
    "traffic",
    "Live traffic",
    "Real questions from your users: turn them into tests and get alerts",
    Radio,
    "production",
  ),
  item("guide", "Prompting guide", "Techniques, templates and how to prove what works", BookOpen, "help"),
]

/** Project-scoped page that sits in the account area of the sidebar (below the groups). */
export const TRENDS_NAV: NavItem = {
  ...item("dashboard", "Trends", "How prompts and models change over time", LineChart, "help"),
}

/** Pages outside a project. */
export type AccountNavItem = {
  key: string
  label: string
  subtitle: string
  icon: LucideIcon
  href: string
  learnMore: string
}

export const ACCOUNT_NAV: AccountNavItem[] = [
  {
    key: "activity",
    label: "Usage and spend",
    subtitle: "Cost and requests across all projects",
    icon: Activity,
    href: "/activity",
    learnMore: "usage",
  },
  {
    key: "workspace",
    label: "Workspace",
    subtitle: "Members, invitations and spending limits",
    icon: Settings2,
    href: "/workspace",
    learnMore: "workspace",
  },
  {
    key: "tokens",
    label: "API tokens",
    subtitle: "Keys for the command line, CI and your apps",
    icon: BrainCircuit,
    href: "/tokens",
    learnMore: "api-tokens",
  },
]

export const PROJECTS_NAV = {
  key: "projects",
  label: "Projects",
  subtitle: "A project holds the keys, prompt, test cases and results for one use case",
  icon: FlaskConical,
  href: "/projects",
  learnMore: "projects",
}

/** Every project page including Trends, in menu order. */
export const ALL_PROJECT_PAGES: NavItem[] = [...PROJECT_NAV, TRENDS_NAV]

export function projectHref(projectId: string, segmentOrItem: string | NavItem): string {
  const segment = typeof segmentOrItem === "string" ? segmentOrItem : segmentOrItem.segment
  return `/projects/${projectId}/${segment}`
}

/** Items of one group, in order. */
export function itemsOf(group: NavGroupId): NavItem[] {
  return PROJECT_NAV.filter((entry) => entry.group === group)
}

/** The project page for a pathname such as `/projects/abc/results`, or undefined. */
export function projectPageForPath(pathname: string): NavItem | undefined {
  const match = /^\/projects\/[^/]+\/([^/?#]+)/.exec(pathname)
  return match ? ALL_PROJECT_PAGES.find((entry) => entry.segment === match[1]) : undefined
}

/** The account page for a top-level pathname such as `/tokens`, or undefined. */
export function accountPageForPath(pathname: string): AccountNavItem | undefined {
  return ACCOUNT_NAV.find((entry) => pathname === entry.href || pathname.startsWith(`${entry.href}/`))
}

/** The page's name for any app route; undefined when the route is not in the navigation. */
export function pageTitleForPath(pathname: string): string | undefined {
  if (pathname === "/projects") return PROJECTS_NAV.label
  return projectPageForPath(pathname)?.label ?? accountPageForPath(pathname)?.label
}

/** Docs slug for any app route. */
export function learnMoreForPath(pathname: string): string | undefined {
  if (pathname === "/projects") return PROJECTS_NAV.learnMore
  return projectPageForPath(pathname)?.learnMore ?? accountPageForPath(pathname)?.learnMore
}
