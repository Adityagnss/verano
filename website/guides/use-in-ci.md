# Use Verano in CI

Fail a pull request when a prompt gets worse. The repository has a GitHub Action, `.github/actions/verano-run`, that runs your prompt tests in Verano, posts a results table as a pull request comment (and updates it on the next push), and fails the job when the gate fails.

The action is in the repository and is not published to a marketplace. Use it by path from a checkout of this repository, or copy the folder.

## Set up

1. Have a Verano server your CI can reach (see [Self-hosting](/self-hosting/)) and a `verano.yaml` in your repository ([format](/reference/verano-yaml)).
2. Create a token for CI and save it as a repository secret named `VERANO_API_TOKEN`:

   ```bash
   verano token create --name ci --project <project>
   ```

   Use a full token limited to one project. A read-only token cannot start a run.
3. Add a gate to each prompt in `verano.yaml`, for example `gate: {min_quality: 0.8, max_drop: 0.03}`.
4. Add the workflow:

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
      - uses: ./.github/actions/verano-run
        with:
          server-url: https://verano.example.com
          token: ${{ secrets.VERANO_API_TOKEN }}
          max-cost: "2"
```

## Inputs

| Input | Default | What it does |
|---|---|---|
| `server-url` | required | The address of your Verano server. |
| `token` | required | The API token, from a repository secret. |
| `file` | `verano.yaml` | The file to use. |
| `prompt` | all | Run only this prompt. |
| `baseline` | latest comparable run | The id of an earlier run to compare with. |
| `max-cost` | none | Refuse to start if the estimate is above this many dollars. |
| `timeout` | `1800` | Seconds to wait for each run. |
| `comment` | `true` | Post or update the results table as a pull request comment. |
| `cli-source` | PyPI | Install the `verano` CLI from a path or pip requirement, for example `./cli` for the copy in your checkout. The CLI is not on PyPI yet, so set this today. |
| `cli-version` | latest | The CLI version to install. |

The gate options and exit codes are in the [GitHub Action reference](/reference/github-action), which is generated from the action's own README.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | The gate passed. |
| 2 | The gate failed. The comment shows why. |
| 1 | Something else went wrong; the job log says what. |

## A working demo

The repository proves the gate in a real job. [`gate-demo.yml`](https://github.com/Adityagnss/verano/blob/main/.github/workflows/gate-demo.yml) starts Verano from the checkout with the built-in test provider (no model key and no cost), signs up a throwaway account, and runs the action twice on [a tiny task](https://github.com/Adityagnss/verano/tree/main/examples/gate-demo): a prompt that meets the quality gate, where the job must pass, and a regressed prompt, where the job must fail with exit code 2. It uses `cli-source: ./cli`. This shows the gate works end to end on the test provider. It does not show results on a paid model, which have not been run.
