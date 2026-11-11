import fs from "node:fs"
import path from "node:path"
import { defineConfig } from "vitepress"
import { AUTHOR_GITHUB, AUTHOR_HANDLE, AUTHOR_LINKEDIN, BASE, REPO_BRANCH, REPO_URL, SITE_URL } from "./site.config.mts"

// Written by scripts/gen-api.mjs before every build and dev start.
const apiSidebar = JSON.parse(fs.readFileSync(path.join(import.meta.dirname, "generated", "api-sidebar.json"), "utf8"))

const sidebar = [
  {
    text: "Get started",
    items: [
      { text: "What is Verano", link: "/get-started/" },
      { text: "User journeys", link: "/get-started/user-journeys" },
      { text: "Quickstart", link: "/get-started/quickstart" },
      { text: "How it works", link: "/how-it-works" },
      { text: "Architecture overview", link: "/get-started/architecture" },
    ],
  },
  {
    text: "Guides",
    items: [
      { text: "Improve a prompt", link: "/guides/improve-a-prompt" },
      { text: "Write a prompt from your documents", link: "/guides/write-a-prompt-from-documents" },
      { text: "Test your own app", link: "/guides/test-your-own-app" },
      { text: "Live traffic", link: "/guides/live-traffic" },
      { text: "Safety checks", link: "/guides/safety-checks" },
      { text: "Use Verano in CI", link: "/guides/use-in-ci" },
      { text: "Use it from an AI agent (MCP)", link: "/guides/use-from-an-ai-agent" },
      { text: "Fetch prompts with the SDKs", link: "/guides/fetch-prompts-with-the-sdks" },
      { text: "Test Python code and frameworks", link: "/guides/test-python-code-and-frameworks" },
      { text: "Add a provider", link: "/guides/add-a-provider" },
      { text: "Add a scanner language", link: "/guides/add-a-scanner-language" },
    ],
  },
  {
    text: "Reference",
    items: [
      { text: "Command line", link: "/reference/cli" },
      { text: "verano.yaml", link: "/reference/verano-yaml" },
      { text: "GitHub Action", link: "/reference/github-action" },
      { text: "What Verano checks", link: "/reference/checks" },
      { text: "Integrations", link: "/reference/integrations" },
      { text: "Examples", link: "/reference/examples" },
      { text: "API", link: "/reference/api/" },
    ],
  },
  { text: "Self-hosting", items: [{ text: "Run it on a server", link: "/self-hosting/" }] },
]

export default defineConfig({
  title: "Verano",
  description:
    "Open-source prompt and model testing on your own cases. Cost is shown before you spend, and an improved prompt is proven on held-back cases, or Verano says Not proven.",
  lang: "en-US",
  base: BASE,
  cleanUrls: true,
  lastUpdated: true,
  // Dead internal links fail the build. Do not turn this off.
  // Only the example address of a locally running Verano is exempt; every site link is still checked.
  ignoreDeadLinks: [/^https?:\/\/localhost(:\d+)?\/?$/],
  srcExclude: ["README.md", "node_modules/**", "scripts/**", "content/**"],
  head: [
    ["link", { rel: "icon", type: "image/svg+xml", href: `${BASE}logo.svg` }],
    ["meta", { name: "theme-color", content: "#f3f6fb" }],
    [
      "meta",
      {
        name: "keywords",
        content:
          "LLM evaluation, LLM evals, prompt testing, prompt optimization, prompt regression testing, LLM as a judge, RAG evaluation, agent evaluation, model comparison, red teaming, prompt injection, LLM cost control, CI for prompts, open source, self-hosted",
      },
    ],
    ["meta", { property: "og:title", content: "Verano" }],
    ["meta", { property: "og:type", content: "website" }],
    ["meta", { property: "og:description", content: "Open-source prompt and model testing on your own cases. See the cost first, and prove the better prompt." }],
    ["meta", { property: "og:url", content: SITE_URL }],
  ],
  sitemap: { hostname: SITE_URL },
  // Generated pages point their logos at /logos/...; make them follow the base path.
  // The edit link points at the real source of a page: the repo file a generated page is made from, or website/<page>.
  transformPageData(pageData) {
    pageData.filePath = pageData.frontmatter.editPath ?? `website/${pageData.filePath}`
  },
  transformHtml(code) {
    return code.replaceAll('src="/logos/', `src="${BASE}logos/`)
  },
  themeConfig: {
    logo: "/logo.svg",
    siteTitle: "Verano",
    nav: [
      { text: "Docs", link: "/get-started/", activeMatch: "^/(get-started|how-it-works)" },
      { text: "Guides", link: "/guides/improve-a-prompt", activeMatch: "^/guides/" },
      { text: "Reference", link: "/reference/cli", activeMatch: "^/reference/" },
      { text: "Self-hosting", link: "/self-hosting/", activeMatch: "^/self-hosting" },
    ],
    sidebar: {
      "/reference/api/": [
        { text: "API reference", items: apiSidebar },
        { text: "Reference", items: sidebar[2].items },
      ],
      "/": sidebar,
    },
    socialLinks: [
      { icon: "github", link: REPO_URL },
      { icon: "linkedin", link: AUTHOR_LINKEDIN },
    ],
    search: { provider: "local" },
    editLink: {
      pattern: `${REPO_URL}/edit/${REPO_BRANCH}/:path`,
      text: "Edit this page on GitHub",
    },
    lastUpdated: { text: "Last updated" },
    outline: { level: [2, 3] },
    docFooter: { prev: "Previous", next: "Next" },
    footer: {
      message: `Apache 2.0. Open sourced by <a href="${AUTHOR_GITHUB}" target="_blank" rel="noopener">${AUTHOR_HANDLE}</a> · <a href="${AUTHOR_GITHUB}" target="_blank" rel="noopener">GitHub</a> · <a href="${AUTHOR_LINKEDIN}" target="_blank" rel="noopener">LinkedIn</a>`,
      copyright: "Verano is built in the open. Nothing here is a promise of a hosted service.",
    },
  },
})
