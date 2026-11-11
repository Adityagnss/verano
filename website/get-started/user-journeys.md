# User journeys

Pick the one that sounds like you. Every journey ends with something you can see: a number, a verdict, or an alert.

<Diagram name="j-full" caption="The whole path through the app. Blue edge: what you give. Amber: what can go wrong. Green: the outcome." />

## Why you can trust the result

Verano checks a new prompt in three ways.

### 1. It is tested on cases the writer never saw

- When you approve test cases, they are split in two: an **improve** part and a **held-back** part.
- Better prompts are written from the improve part only.
- The best one is then run **once** on the held-back part, next to your current prompt, on the same cases.
- If it does not clearly win, you see **Not proven** or **Worse**, with the numbers.

### 2. One rule decides "clearly better"

- One piece of code makes that call.
- Results, the re-run check, Improve and the command line all use it.
- So two screens can never show two different verdicts.

### 3. The judge is open

- You can read the exact request the judge received for each answer.
- Change the judge or a criterion and you get a new version and a new scoring pass. Old and new scores are never mixed.
- An answer the judge cannot score is marked **unscored**. It is left out of the numbers and is never counted as a pass.
- You can label answers yourself and see how often the judge agrees with you.

## Pick your journey

| You are | You want | Journey |
|---|---|---|
| Someone with a prompt | Make it better, with proof | [1](#_1-i-have-a-prompt-and-want-it-better) |
| Someone with documents but no prompt | A first draft to start from | [2](#_2-i-have-no-prompt-yet) |
| Choosing between models | The best one for the money | [3](#_3-which-model-should-i-use) |
| A developer with prompts in code | Stop a bad change from shipping | [4](#_4-i-want-pull-requests-checked) |
| Running a chatbot or RAG app | Know when real answers get worse | [5](#_5-my-app-is-already-live) |
| Worried about attacks | See if the prompt holds up | [6](#_6-is-my-prompt-safe) |
| Running it for a team | Roles, shared keys, a spending limit | [7](#_7-my-team-shares-one-verano) |
| Using an AI agent | Let the agent run tests | [8](#_8-an-ai-agent-uses-it) |

## 1. I have a prompt and want it better

<p class="who">Prompt owner, product developer, anyone shipping a feature built on a prompt.</p>

<Diagram name="j-improve" />

- Add a key, or a local model with no key.
- Verano drafts test cases. You approve each one.
- You see the cost before the run starts.
- You see quality, cost, speed and consistency for each model, with the reasons.
- Improve writes better prompts from the cases that fail.
- The best one is tested on cases it never saw.

**What you end with:** *Proven*, with the numbers, or *Not proven*, with the numbers and what to do next.

Go deeper: [Quickstart](/get-started/quickstart), [Improve a prompt](/guides/improve-a-prompt).

## 2. I have no prompt yet

<p class="who">You have a policy, a manual or past answers, and nothing written.</p>

<Diagram name="j-docs" />

- Upload the documents.
- Press **Write it for me**. Say what the prompt should do, or leave it empty.
- You get a draft and the reasons behind each part.
- Edit it. Nothing is saved until you save.
- Then it is journey 1.

**What you end with:** a first prompt you understand, ready to be tested.

Go deeper: [Write a prompt from your documents](/guides/write-a-prompt-from-documents).

## 3. Which model should I use?

<p class="who">You are choosing, or switching, a model and want to see the cost.</p>

<Diagram name="j-model" />

- Tick several models. Mix providers, or use local ones.
- See the estimated cost. Confirm, or stop.
- Each model answers each case more than once, so you also see how steady it is.
- Set a budget cap. If a run reaches it, the run pauses and keeps its answers.

**What you end with:** one table with quality, pass rate, consistency, speed and cost, and every answer side by side. Export it to CSV.

Go deeper: [Quickstart](/get-started/quickstart).

## 4. I want pull requests checked

<p class="who">A developer or team with prompts in a repository.</p>

<Diagram name="j-ci" />

- `verano init` finds the prompts in your code.
- Add a gate to `verano.yaml`, for example a minimum quality.
- Every pull request runs the tests. `max-cost` caps the spend.
- A results table is posted on the pull request.

**What you end with:** a pull request that fails when quality, cost or speed gets worse.

Go deeper: [Use Verano in CI](/guides/use-in-ci), [The command line](/reference/cli).

## 5. My app is already live

<p class="who">You run a chatbot, an API or a RAG app, and real users are talking to it.</p>

<Diagram name="j-live" />

- Connect the app by its HTTP address, or send traces from your tracing tool.
- Verano scores the answer, the retrieved text and the tool calls.
- Personal data is removed first.
- Pick bad or slow answers. Turn them into draft test cases.
- A sample of live answers is scored. A lasting drop sends an alert.

**What you end with:** real problems turned into tests, and a warning before users complain.

Go deeper: [Test your own app](/guides/test-your-own-app), [Live traffic](/guides/live-traffic).

## 6. Is my prompt safe?

<p class="who">You want to see how the prompt handles common attacks.</p>

<Diagram name="j-safety" />

- Pick the kinds of attack to try.
- Verano writes the attacks. You approve each one.
- You get a pass rate for each kind, next to the earlier run.
- **Harden** asks Improve to add defences, then proves the result like any other change.

**What you end with:** a clear report. It is a small set of common attacks, not a security audit.

Go deeper: [Safety checks](/guides/safety-checks).

## 7. My team shares one Verano

<p class="who">An owner or admin sets it up. Others use it.</p>

<Diagram name="j-team" />

- Run it on a server with automatic HTTPS.
- Invite people by link. Four roles: viewer, member, admin, owner.
- Provider keys are kept once and shared. Set a monthly spending limit.
- A run that reaches the limit stops, keeps its answers and says why.

**What you end with:** a shared place to test, with a record of who changed what.

Go deeper: [Self-hosting](/self-hosting/).

## 8. An AI agent uses it

<p class="who">An agent in your editor needs to run tests and read results.</p>

<Diagram name="j-agent" />

- Make a token. Add `--read-only` to let the agent only look.
- Start `verano mcp`. It is read-only until you pass `--allow-write`.
- `--max-cost` caps what the agent can spend.

**What you end with:** an agent that can check its own work, inside limits you set.

Go deeper: [Use it from an AI agent](/guides/use-from-an-ai-agent).

## When something goes wrong

| What happens | What you see |
|---|---|
| A key does not work | Verano checks it with a free request before saving, and says so |
| A run reaches its budget cap | It pauses and keeps finished answers. Raise the cap and resume |
| The monthly spending limit is reached | The run stops, keeps its answers and says why |
| A worker stops in the middle of a run | The run is picked up again |
| The judge cannot score an answer | The answer is shown as unscored, left out of the scores, and never counted as a pass |
| Too few held-back cases | *Not proven*. You need at least 15 held-back cases |
| Your app is on a private address | Verano refuses, unless the server owner allows that host |
| One bad day in live traffic | No alert. Alerts need a lower level for more than one day |
