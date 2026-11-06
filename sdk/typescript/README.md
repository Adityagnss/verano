# @verano/sdk (TypeScript)

Fetch the prompt that Verano serves for a label such as `production`, inside your app. Typed, no
dependencies (only `fetch`), keeps the last good copy, and keeps working when Verano is down.

```bash
npm install @verano/sdk
```

```ts
import { Verano, render } from "@verano/sdk";

const verano = new Verano({ cacheDir: ".verano-cache" }); // VERANO_URL, VERANO_API_TOKEN, VERANO_PROJECT_ID
const prompt = await verano.prompt("support-bot", { label: "production" });
const { system, user } = render(prompt, { question: "Where is my order?" });
console.log(prompt.version, prompt.fromCache);
```

Make a token that can only read: `verano token create --name my-app --read-only --project "my project"`.

## When Verano is not reachable

- It asks Verano whether the prompt changed (an ETag, so an unchanged prompt is an empty answer).
- No connection, a timeout or a server error: it returns the last good copy with `fromCache: true` and calls
  your `onFallback(message, prompt)`. The copy is kept in memory, and on disk when `cacheDir` is set (Node, Bun, Deno).
- No saved copy yet: it throws `VeranoUnreachable`, and says so.
- Verano says no (a revoked token, an unknown label): it throws `VeranoRefused`; this is never hidden by the cache.

Options: `timeoutMs` (default 3000), `maxAgeMs` (skip asking again for this long, default 0), `fetch` (replace the global one).
`render` fills `{{ name }}` placeholders only; it does not run template logic.
