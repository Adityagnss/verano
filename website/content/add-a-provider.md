# Add a provider

Most providers need **one YAML entry and nothing else**. A provider with its own API shape
needs one small plugin class. Either way no business logic changes: the registry and the
gateway ask the catalog and the model profile what a provider supports, never "is this
provider X?".

## A. OpenAI-compatible providers (most of them)

If the provider lists models at `GET {base_url}/models` with a Bearer key, add an entry to
`backend/app/modules/registry/config/providers.yaml`:

```yaml
  fireworks:
    display_name: Fireworks AI
    client: openai_compatible          # reuse the generic client
    litellm_prefix: fireworks_ai       # LiteLLM's provider prefix for calls
    base_url: https://api.fireworks.ai/inference/v1
    requires_key: true
    listing:
      items_path: data                 # where the list sits ("" if the body is a list)
      fields:                          # optional: where extra facts live in each item
        context_window: context_length
      chat_rules:                      # optional: how to tell chat models apart
        - {path: supports_chat, equals: true}
    exclude_id_patterns: [embed]       # optional: ids that are never chat models
    rate_limits: {rpm: 60, tpm: 500000}  # starting defaults only; they adapt
```

Prices can come from the listing too (`input_price` / `output_price` fields plus
`price_unit: per_token | per_million_tokens`); otherwise LiteLLM's bundled metadata or
`model_overrides.yaml` supply them, and an unknown price is shown as unknown.

## B. A provider with its own listing API

1. Create `backend/app/modules/registry/plugins/<name>.py`:

   ```python
   @PROVIDER_CLIENTS.register("<name>")
   class MyProviderClient(BaseProviderClient):
       client_name = "<name>"

       async def list_models(self, api_key: str | None, base_url: str) -> list[RawModel]:
           payload = await self.http.get_json(f"{base_url}/models", {"Authorization": f"Bearer {api_key}"})
           return [RawModel(id=item["id"], capabilities={Capability.CHAT}) for item in payload["models"]]
   ```

   `self.http` turns every failure into a typed error with a message that tells the user
   what to do (401/403 → "This key was rejected by …"). If the provider reports a bad key
   with another status, list a marker from its error body in `auth_error_markers`.
   If the provider's model list is public (it answers without a valid key, as OpenRouter's
   does), add `key_check_path:` with an endpoint that needs the key (OpenRouter: `/key`);
   adding a key calls it first, so a wrong key is refused instead of saved.
2. Add the entry to `providers.yaml` with `client: <name>`.

## C. Test it without a key

Put the provider's documented responses in `backend/tests/fixtures/providers/<name>/`
(`models.json`, `auth_error.json`), then add it to the `ROUTES`, `AUTH_URLS` and `EXPECTED`
tables in `backend/tests/integration/registry/test_registry.py`. The discovery and bad-key
tests are parametrized over those tables, so this adds both tests. Run `make test`.

Before a public release, `scripts/verify_providers.py` checks the fixtures against the live
API once, with a real key.

## D. Which settings the provider accepts

Every model starts with the common settings (`temperature`, `top_p`, `max_tokens`, `seed`, the two
penalties and `stop`), narrowed by what the provider's listing or LiteLLM's metadata says the model
supports, and the Run step offers only what remains. Tune it in the provider's entry:

```yaml
    parameter_ranges:                  # a narrower range than the catalog's default
      temperature: {max: 1.0}
    unsupported_parameters: [seed, presence_penalty, frequency_penalty]   # never sent to this provider
    extra_parameters: [top_k]          # opt-in settings this provider accepts
```

`top_k` is opt-in because most OpenAI-style APIs reject it and no listing says who accepts it: it
is offered only when the entry lists it under `extra_parameters` (Anthropic, Gemini and Ollama do) or
a model's own listing names it. A setting that a model does not accept is never sent, and an
experiment records it as ignored.

## E. The command-line tool

A provider's `litellm_prefix`-free name (`fireworks` above) is the name used under `keys:` in a
`verano.yaml`. To let `verano init` propose its key, add its usual environment variable to
`PROVIDER_KEYS` in `cli/src/verano/scan/findings.py`, and add the SDK's package name to `SDK_HINTS` in
`cli/src/verano/scan/broad_scan.py` if it is not already covered.
