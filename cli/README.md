# verano, the command-line tool

Connect your own codebase to a [Verano](../README.md) server. `verano init` finds the prompts in
your code, `verano push` sets them up in Verano, and `verano run` tests them on your examples and
prints a table. In a pull request, `verano run --ci` fails the build when quality drops.

It only uses Verano's public API, so every model call still goes through Verano's gateway, with its
cost, tokens and retries recorded. Nothing is sent anywhere until you run `push` or `run`.

## Install

You need Python 3.10 or newer, and a running Verano (`make up` in the repository, then open
http://localhost:8080 and create an account).

```bash
uvx verano --help             # run it without installing, once it is published
pipx install verano           # or install it (also: pip install verano)
uv tool install ./cli         # from a clone of this repository, today
```

## The two minutes

```bash
verano login          # your Verano email and password; saves a personal token on this machine
cd my-app
verano init           # scans the code (Python, TypeScript, JavaScript and eight more languages)
                      #   and writes verano.yaml. Look for TODO and fill them in.
verano validate       # checks the file and shows what push would set up
verano push --dry-run # what would be created on your server; nothing changes
verano push           # creates the project, adds your key, picks the models, uploads your examples
verano run            # shows the cost first, asks, runs, prints results and a link
verano status         # the latest results again
```

A complete, runnable example is in [`examples/support-triage`](../examples/support-triage/).

## Commands

| Command | What it does |
|---------|--------------|
| `verano login` | Sign in with a password; keeps a 90-day token (`--days`), not the password. `--token` saves one you already have. |
| `verano logout` | Revokes the saved token and deletes it from this machine. |
| `verano whoami` | Who you are, which server, and where the sign-in comes from. |
| `verano token create --name ci` | A token for CI, printed once on its own line. `list` and `revoke` manage them. |
| `verano init [folder]` | Scans the code and writes `verano.yaml`. `--print` shows it instead; `--yes` takes everything that can be tested; `--force` replaces an existing file. |
| `verano validate` | Checks `verano.yaml` with line numbers and "did you mean" hints. Sends nothing. |
| `verano push [name]` | Makes Verano match the file: project, keys, models, prompt, test cases. Safe to repeat. `--dry-run`, `--no-data`, `--replace-draft`. |
| `verano run [name]` | Runs each prompt on its test cases. `--yes` skips the question, `--max-cost 2` refuses a dearer run, `--json` prints one JSON document, `--ci` is for pipelines. |
| `verano status [name]` | The latest finished run of each prompt. |

Use `-f other.yaml` on `validate`, `push`, `run` and `status` to use a different file.

## verano.yaml

```yaml
version: 1
project: support-bot               # each prompt below becomes the Verano project "support-bot · <name>"
keys:
  openai: env:OPENAI_API_KEY       # the NAME of an environment variable, never the key itself
  ollama: none                     # a provider that needs no key
prompts:
  - name: classify-ticket
    source: {file: app/triage.py, line: 17}   # where it came from; push reports changes against it
    system: |                      # or system_file: prompts/triage.txt
      You are a support triage assistant...
    user: "Ticket: {{ attachment }}"          # or user_file; {{ attachment }} is each test case's input
    params: {temperature: 0, max_tokens: 5}   # temperature 0 and seed 42 are filled in for models that accept them
    task:
      type: classification         # classification, extraction, summarization, question_answering,
      goal: Route each ticket to a team        #   generation, transformation, conversation
      allowed_outputs: [billing, shipping, technical]   # required for classification
    data:
      cases: {file: data/tickets.csv, input: ticket, expected: expected}   # one test case per row
      # or your own files:  inputs: ["tickets/*.txt"]  golden: answers.csv  columns: {input_file: file, expected_output: answer}
    models: [gpt-4o-mini, claude-haiku]       # names as Verano lists them; provider/model if two keys offer one
    judge: gpt-4o                  # a model that scores answers, when the task needs one
    runs: 2                        # 1 to 5; more runs show how steady a model is
    budget: 1.00                   # dollars; the run stops when spent
    gate: {min_quality: 0.85, min_pass_rate: 0.9, max_drop: 0.05}   # what --ci demands (0 to 1)
```

Prompt text can be in the file or in files next to it. Every file named must stay inside the
folder of `verano.yaml`. `data.cases` takes CSV, TSV, JSON or JSONL with up to 500 usable rows.

## In a pull request

```yaml
- run: pipx install verano
- run: verano push && verano run --ci
  env:
    VERANO_URL: https://verano.example.com
    VERANO_API_TOKEN: ${{ secrets.VERANO_API_TOKEN }}   # from `verano token create --name ci`
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

`--ci` never asks a question. Exit codes: **0** done (and the gate passed), **1** an error,
**2** the quality gate failed. A run that stopped early (budget, error) fails its gate. `max_drop`
compares with the last completed run of the same models and settings on the same test cases.

## What leaves your machine

| When | What is sent, and where |
|------|-------------------------|
| `init`, `validate` | Nothing. |
| `login`, `token create` | Your email and password, once, to your Verano server. |
| `push` | Prompt text, task, test cases and the provider keys named under `keys:`, to your Verano server only. The CLI never prints or saves a key. |
| `run` | A request to start the run. The model calls are made by your Verano server. |

## How `init` reads your code

| Level | Languages | How | Accuracy |
|-------|-----------|-----|----------|
| Full | Python, TypeScript, JavaScript | A real syntax tree: follows constants, f-strings, template literals, `.format()` | High |
| Broad | Java, Go, C#, Ruby, PHP, Rust, Kotlin, Swift | Finds model names, SDK imports, API addresses and long instruction-like text near them | Medium: never ticked for you |

It always says what it could not read (a prompt built by a function call, messages passed in from
elsewhere) instead of guessing. Prompts kept in text files, and unusual frameworks, are for a later
`init --deep`; write those into `verano.yaml` by hand.

## Good to know

- **One project per prompt.** Verano tests one prompt per project: its examples, task, models and
  keys belong to it. A `verano.yaml` with three prompts makes three projects.
- **Real examples arrive as one input.** Test cases from your own files reach the prompt as
  `{{ attachment }}` (or as the user message of a system-only prompt). A prompt with several
  variables, like `{{ ticket }}` and `{{ tone }}`, can't run on them yet; `init` offers it unticked
  and `push` explains the fix.
- **Changing the examples or the task makes a new dataset version**, so old runs keep the data
  they ran on. Rewording the prompt does not.

## Troubleshooting

| You see | Do this |
|---------|---------|
| `Can't reach Verano at ...` | Start it (`make up`), or pass `--url` / set `VERANO_URL` to the address you open in the browser. |
| `doesn't look like a Verano server` | The address is a web page, not Verano's. Use the one from the browser. |
| `The environment variable OPENAI_API_KEY ... is not set` | `export` it, or remove that line under `keys:`. |
| `No model called ...` | Add that provider's key under `keys:`; the message lists the models that exist. |
| `Not starting without your confirmation` | You're in a script: add `--yes` (or `--ci`). |
| `... unapproved test cases that are not in verano.yaml` | They came from the web app. Review them there, or `verano push --replace-draft`. |

`VERANO_DEBUG=1 verano ...` shows the details of an unexpected error.
