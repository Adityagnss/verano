# Verano prompt check (GitHub Action)

Runs your prompt tests in Verano on every pull request, posts a results table as a comment (and updates it on
the next push), and fails the job when the gate fails.

```yaml
name: Prompt check
on: pull_request
permissions:
  contents: read
  pull-requests: write
jobs:
  verano:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/verano-run        # or verano/run-action@v1 once published
        with:
          server-url: https://verano.example.com
          token: ${{ secrets.VERANO_API_TOKEN }}
          max-cost: "2"
```

## The gate

Written in `verano.yaml`, per prompt. Scores are fractions (0.8 is 80%):

```yaml
gate:
  min_quality: 0.8
  min_pass_rate: 0.9
  max_drop: 0.03            # against the baseline run
  max_cost_per_call: 0.01   # dollars
  max_latency_ms: 4000      # average answer time
  max_cost_increase: 0.2    # at most 20% dearer than the baseline
  max_slowdown: 0.3         # at most 30% slower than the baseline
  baseline: <run id>        # pin the baseline; the input `baseline` overrides it
```

Without `baseline`, the comparison is the latest earlier run of the same models and settings on the same test cases.

## Results

| Exit code | Meaning |
|-----------|---------|
| 0 | the gate passed |
| 2 | the gate failed: a pull request that breaks the prompt fails here, and the comment shows why |
| 1 | something else went wrong (the job log says what) |

## A revoked or expired token

The job fails with exit 1, an annotation "Verano token rejected" and a comment that says: the token was revoked,
has expired or is wrong; create a new one with `verano token create --name ci` and update the repository secret.
Use a token limited to one project (`--project`). A read-only token can fetch prompts but cannot start a run.

## Notes

- Secrets are passed through environment variables only; the token is never printed.
- The action installs `verano` from PyPI (`cli-version` pins it).
- Checked here only by reading and by `bash -n`; it has not yet run in a real GitHub job (pending check 13).
