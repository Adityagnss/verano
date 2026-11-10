# Fetch your prompts with the SDKs

Once a prompt wins, your app should use it without a code change. The Python and TypeScript libraries fetch the prompt that Verano serves for a label such as `production`. Move the label in Verano, and your app picks up the new version.

Both libraries have no dependencies, keep the last good copy, and keep working when Verano is down.

::: warning Not published yet
The libraries are in the repository (`sdk/python`, `sdk/typescript`) and are tested, but not on PyPI or npm yet. Install them from a clone for now.
:::

## Make a token that can only read

```bash
verano token create --name my-app --read-only --project "my project"
```

Set `VERANO_URL`, `VERANO_API_TOKEN` and `VERANO_PROJECT_ID` in your app's environment.

## Python

```python
from verano_sdk import Verano

verano = Verano()  # reads VERANO_URL, VERANO_API_TOKEN, VERANO_PROJECT_ID
prompt = verano.prompt("support-bot", label="production")
system, user = prompt.render(question="Where is my order?")
print(prompt.version, prompt.from_cache)
```

## TypeScript

```ts
import { Verano, render } from "@verano/sdk";

const verano = new Verano({ cacheDir: ".verano-cache" });
const prompt = await verano.prompt("support-bot", { label: "production" });
const { system, user } = render(prompt, { question: "Where is my order?" });
console.log(prompt.version, prompt.fromCache);
```

## When Verano is not reachable

- The library asks Verano whether the prompt changed (an unchanged prompt is an empty answer, so it is cheap).
- If Verano cannot be reached (no connection, a timeout or a server error), it returns the last good copy and says so: `from_cache` is true, and Python also raises a `UserWarning`. Your app keeps serving.
- With no saved copy yet, it raises `VeranoUnreachable`.
- If Verano answers no (a revoked token, an unknown label), it raises `VeranoRefused`. That is never hidden behind the cache, so a revoked token does not go unnoticed.

`render` fills `{{ name }}` placeholders only. It does not run template logic.

## Roll back

In Verano, move the label back to an earlier version. The next fetch returns it.
