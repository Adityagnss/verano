// Copies the public source documents into the site, rewriting links and removing the few internal references.
import { read, rewriteLinks, writePage } from "./lib.mjs"

const GH_ACTION_NOTE =
  "- The repository's `gate-demo` workflow runs this action in a real GitHub job against Verano with the built-in test provider (a good prompt passes, a regressed one fails the gate). It has not been run against a paid model, and the action is not published to a marketplace yet."

const docs = [
  { src: "docs/guides/improve-a-prompt.md", out: "guides/improve-a-prompt.md" },
  { src: "docs/guides/add-a-provider.md", out: "guides/add-a-provider.md" },
  {
    src: "docs/guides/add-a-scanner-language.md",
    out: "guides/add-a-scanner-language.md",
    fix: [[/, and add a row to the decision log in `docs\/DEVELOPMENT\.md`/, ""]],
  },
  { src: "docs/guides/self-hosting.md", out: "self-hosting/index.md" },
  {
    src: "cli/README.md",
    out: "reference/cli.md",
    fix: [
      [/\(built, not yet run in a real job\)/g, ""],
      [
        /\(`\.github\/actions\/verano-run` in this repository; it is built\nbut has not been run in a real GitHub job yet, and is not published\)/,
        "(`.github/actions/verano-run` in this repository, not published; see [Use Verano in CI](/guides/use-in-ci))",
      ],
    ],
  },
  {
    src: ".github/actions/verano-run/README.md",
    out: "reference/github-action.md",
    fix: [[/^- Checked here only by reading.*$/m, GH_ACTION_NOTE]],
  },
  { src: "examples/README.md", out: "reference/examples.md" },
]

for (const { src, out, fix = [] } of docs) {
  let text = read(src)
  for (const [from, to] of fix) text = text.replace(from, to)
  text = rewriteLinks(text, src)
  writePage(out, text, { editPath: src })
}

// The verano.yaml reference is the "## verano.yaml" section of the CLI README, on its own page.
const cli = read("cli/README.md")
const start = cli.indexOf("## verano.yaml")
const end = cli.indexOf("\n## ", start + 5)
const section = cli.slice(start, end).replace("## verano.yaml", "# verano.yaml")
writePage("reference/verano-yaml.md", rewriteLinks(section, "cli/README.md"), { editPath: "cli/README.md" })
console.log(`gen-docs: ${docs.length + 1} pages`)
