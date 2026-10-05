# Example: support-triage

A tiny support-desk app with two prompts, and 100 labelled tickets. It shows the whole path from
"I have a codebase" to "I have numbers" in about two minutes.

```text
app/triage.py            the app: classify_ticket() and draft_reply(), each calls a model
data/tickets.csv         100 tickets with the team that should handle each (ticket,expected)
verano.yaml              what `verano init` proposed, with its TODOs filled in
verano.ollama.yaml       the same project on a free local model
```

## Before you start

Verano is running (`make up`, then open http://localhost:8080 and create an account) and the CLI is
installed (`uv tool install ../../cli`, or `pipx install ../../cli`). Then sign in:

```bash
verano login          # asks for the email and password of your Verano account
export OPENAI_API_KEY=sk-...    # only needed for verano.yaml; see "No paid key?" below
```

## The two minutes

```bash
cd examples/support-triage

verano init --print     # 1. what Verano finds in app/triage.py. Nothing is written or sent.
verano validate         # 2. check verano.yaml (already filled in) and preview what push will do
verano push --dry-run   # 3. see what would be created on your server; nothing changes
verano push             # 4. create the project, add your key, pick the models, upload the 100 cases
verano run              # 5. shows the cost first, asks, then runs and prints a table and a link
verano status           # 6. the latest results again, any time
```

What to look at:

- **Step 1** finds two prompts. `classify_ticket` is ticked. `draft_reply` is left out, with the reason:
  it has two inputs, and Verano's real test cases supply one. It stays in the file as a comment.
- **Step 4** is safe to repeat. Run it again and it says "unchanged" for everything.
- **Step 5** shows the estimated cost before it sends anything. The table shows quality, how many
  passed, how steady each model's answers are across the two runs, speed and cost.
- Edit the prompt in `app/triage.py`, copy the change into `verano.yaml`, run `verano push` (a new
  prompt version is saved, the test cases are kept) and `verano run` again: the web app's Results
  page shows both runs, and `max_drop` in the `gate:` fails a pull request if quality falls.

## In a pull request

```yaml
# .github/workflows/prompts.yml (excerpt)
- run: pipx install verano
- run: verano push && verano run --ci
  env:
    VERANO_URL: ${{ vars.VERANO_URL }}
    VERANO_API_TOKEN: ${{ secrets.VERANO_API_TOKEN }}   # made once with `verano token create --name ci`
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
```

`verano run --ci` never asks a question, and exits with 2 when the quality gate fails.

## No paid key?

Use the local model instead. Pull it once (`make models`), start Verano with the local profile
(`make up-local`), then use the other file for every command:

```bash
verano push -f verano.ollama.yaml
verano run  -f verano.ollama.yaml --yes
```
