# verano-sdk (Python)

Fetch the prompt that Verano serves for a label such as `production`, inside your app. It has no
dependencies, is typed, keeps the last good copy on disk, and keeps working when Verano is down.

```bash
pip install verano-sdk
```

```python
from verano_sdk import Verano

verano = Verano()   # reads VERANO_URL, VERANO_API_TOKEN, VERANO_PROJECT_ID
prompt = verano.prompt("support-bot", label="production")
system, user = prompt.render(question="Where is my order?")
print(prompt.version, prompt.from_cache)
```

Make a token that can only read: `verano token create --name my-app --read-only --project "my project"`.

## What happens when Verano is not reachable

- The library asks Verano whether the prompt changed (an ETag, so an unchanged prompt is an empty answer).
- If Verano cannot be reached (no connection, a timeout, a server error), it returns the last good copy,
  sets `prompt.from_cache = True` and raises a `UserWarning` saying so. Your app keeps serving.
- If there is no saved copy yet, it raises `VeranoUnreachable` and says so.
- If Verano answers "no" (a revoked token, an unknown label), it raises `VeranoRefused`. That is never
  hidden behind the cache, so a revoked token does not go unnoticed.

Options: `cache_dir`, `timeout` (seconds, default 3), `max_age` (seconds to skip asking again, default 0).
`render` fills `{{ name }}` placeholders only; it does not run template logic.
