"""
`verano mcp`: a local Model Context Protocol server, so an AI agent can use Verano through your token.

It talks over standard input and output (one JSON message per line) and only calls Verano's public
API, exactly as the CLI does. By default it is read-only: it can list and read, never change. Every
tool that creates, spends or moves something refuses until the person who started the server adds
`--allow-write`; the refusal names that flag.
"""
