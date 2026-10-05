# verano (command-line tool)

Connects your own codebase to a [Verano](../README.md) server: sign in, then (in the next steps of
the roadmap) scan your code for prompts, push them to a project and run evaluations from the
terminal or from CI.

```text
verano login            sign in and save a personal API token on this machine
verano whoami           who you are signed in as, and to which server
verano logout           revoke the saved token and delete it from this machine
verano token create     make a token for CI (printed once; set it as VERANO_API_TOKEN)
verano token list       your tokens
verano token revoke ID  stop a token from working
```

The server address is `http://localhost:8080` unless you pass `--url` or set `VERANO_URL`. In CI, set
`VERANO_URL` and `VERANO_API_TOKEN`; no login step is needed.

The CLI only uses Verano's public API, so every model call still goes through the gateway.
