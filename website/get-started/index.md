# What is Verano

Verano tests prompts and models on your own test cases. You give it your API keys, a prompt and a few examples. It builds the evaluation, runs the models you choose, shows the quality, cost and speed tradeoffs, explains why a prompt fails, and suggests better prompts. It calls a new prompt better only when that is proven on cases it never saw.

## What makes it different

- **Cost is shown first.** Every model call is shown with its cost before it starts. Generation and runs have a budget cap and a stop button, and nothing paid starts without your say-so.
- **Proof, or "Not proven".** A new prompt is built from one part of the data and confirmed on a held-back part. "Better" needs a clear difference on at least 15 held-back cases (a setting). Otherwise Verano says *not proven* and shows the numbers.
- **A judge you choose, and can read.** The model that scores answers is picked on purpose, its criteria are editable, every request it received can be read, and an answer it could not score is shown as unscored, never as a pass.
- **Consistency is a metric.** Each model runs each case several times, so you see how predictable it is, not just how good it was once.
- **Reproducible, and honest about it.** Every run records its configuration as a fingerprint. A fixed seed is shown as a setting, never as a guarantee.
- **Free to try.** It runs on local models through Ollama, with no provider account and no API key.

## Ways to use it

| You want to | Go to |
|---|---|
| See which situation is yours | [User journeys](/get-started/user-journeys) |
| Try it in the browser | [Quickstart](/get-started/quickstart) |
| Test a prompt that lives in your code | [The command line](/reference/cli) |
| Test an app you already run | [Test your own app](/guides/test-your-own-app) |
| Fail a pull request when quality drops | [Use Verano in CI](/guides/use-in-ci) |
| Run it for a team on a server | [Self-hosting](/self-hosting/) |

## Where it stands

The whole loop is built: keys, prompt, your data, test cases, run, results, improve. It is tested on a built-in mock provider, recorded responses and free models. **Nothing has been proven on a paid model yet.** The `verano` command-line tool and the Python and TypeScript libraries are not on PyPI or npm, so you install them from a clone of the repository. There is no hosted cloud: you run Verano yourself.

The [integrations page](/reference/integrations) lists what has been checked against real third-party tools and what has only been tested with stand-ins.
