# Recorded provider responses

Replayed with `respx` so provider parsing is tested without network or keys
(DEVELOPMENT.md E2). Each file follows the response format published in the provider's
official API reference. Before the first public release, `scripts/verify_providers.py`
compares these shapes with live responses once, using real keys.

Per provider: `models.json` (listing, plus `models_page2.json` where the endpoint
paginates), `auth_error.json` (the documented bad-key response), and for chat
completions `chat_success.json`, `chat_429.json`, `chat_400.json` and
`chat_content_policy.json` where the provider documents one. The HTTP status and
headers each file is served with are declared next to the tests that replay it.
