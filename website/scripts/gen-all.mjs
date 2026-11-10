// Runs every generator. `npm run build` and `npm run dev` call this first, so generated pages never drift from their sources.
import "./gen-docs.mjs"
import "./gen-api.mjs"
import "./gen-integrations.mjs"
