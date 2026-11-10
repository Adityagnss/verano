# Verano website

The public product site and documentation, built with [VitePress](https://vitepress.dev). It is separate from the app: its own `package.json` and lockfile, dev-only, nothing here ships in the Verano images.

## Run it

```bash
cd website
npm install
npm run dev       # http://localhost:5173/verano/
npm run build     # output in .vitepress/dist; fails on any dead internal link
npm run preview   # serve the built site
```

`npm run dev` and `npm run build` first run `scripts/gen-all.mjs`, which writes the generated pages. Do not edit or commit them (they are in `.gitignore`); change the source instead:

| Generated page | Source |
|---|---|
| Improve a prompt, Add a provider, Add a scanner language, Self-hosting | `docs/guides/*.md` |
| Command line, verano.yaml | `cli/README.md` |
| GitHub Action | `.github/actions/verano-run/README.md` |
| Examples | `examples/README.md` |
| Integrations | `docs/integrations/registry.yaml` |
| API reference | `frontend/src/lib/api/openapi.json` (`scripts/gen-api.mjs`) |

Relative links in the sources are rewritten to site routes, or to GitHub for files that are not pages. Internal documents (decision records, plans, checkpoints and the like) are never published; links to them are reduced to plain text (see `PRIVATE` in `scripts/lib.mjs`). Hand-written pages: `index.md`, `get-started/`, `how-it-works.md` and the five new guides in `guides/`.

## Base path and custom domain

Everything that depends on where the site lives is in `.vitepress/site.config.mts`:

```ts
export const BASE = "/verano/"
export const SITE_URL = "https://adityagnss.github.io/verano/"
```

For a custom domain set `BASE` to `"/"` and `SITE_URL` to the domain (and add a `public/CNAME` file). For a one-off build use `VERANO_SITE_BASE=/ VERANO_SITE_URL=https://docs.example.com/ npm run build`.

## Deploying

`.github/workflows/pages.yml` builds the site and deploys it to GitHub Pages. The deploy job runs only when the repository is public. Turn Pages on under Settings, Pages, Source: GitHub Actions.

## Theme

`.vitepress/theme/custom.css` uses the colours of the app (`frontend/src/styles/tokens.css`, copied, not imported), light and dark, with system fonts and no remote assets.
