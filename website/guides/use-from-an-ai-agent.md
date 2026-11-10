# Use Verano from an AI agent (MCP)

`verano mcp` starts a local [Model Context Protocol](https://modelcontextprotocol.io) server, so an AI agent, such as the one in your editor, can list projects, run a test, read the results and ask Verano to improve a prompt. It only calls Verano's public API with your token, the same way the command line does.

## Start it

You need the command line installed (see [Quickstart](/get-started/quickstart)) and to be signed in (`verano login`) or to have `VERANO_API_TOKEN` and `VERANO_URL` set.

Most MCP clients take a small JSON block that tells them how to start the server:

```json
{
  "mcpServers": {
    "verano": {
      "command": "verano",
      "args": ["mcp"],
      "env": {
        "VERANO_URL": "http://localhost:8080",
        "VERANO_API_TOKEN": "vrn_..."
      }
    }
  }
}
```

Make a token for it with `verano token create --name agent` (add `--read-only` for an agent that should only look).

## Read-only by default

The server starts **read-only**. An agent can look but not change anything.

| Tool | What it does | Needs `--allow-write` |
|---|---|---|
| `list_projects` | The projects the token can see | no |
| `list_prompts` | The prompts in a project | no |
| `list_labels` | Which version each label (such as `production`) points at | no |
| `get_result` | The latest results of a run, with what the numbers can and cannot tell you | no |
| `get_improvement` | The state and verdict of an Improve session | no |
| `create_project` | Make a project | **yes** |
| `run_evaluation` | Start a run on a prompt's test cases | **yes** |
| `propose_improvement` | Start Improve on a finished run | **yes** |
| `accept_improvement` | Accept a proven better prompt as a new version | **yes** |
| `move_label` | Point a label at a saved version | **yes** |

A tool that writes refuses until you start the server with `--allow-write`, and the refusal names that flag.

## Keep the cost in check

```bash
verano mcp --allow-write --max-cost 1
```

`--max-cost` is the most a run started by the agent may cost, in dollars. Nothing starts if the estimate is higher. Verano shows the cost first for every run, so the agent can report it before spending.

## Good to know

- `get_result` returns a `limits` list that says what the numbers cannot show. A good agent repeats it when it reports.
- An agent can start paid runs only with `--allow-write`. Start with read-only and add the flag when you trust the setup.
- The server talks over standard input and output, so it never opens a port.
