# Improve a prompt

Improve looks at the test cases your prompt gets wrong, writes better versions of the prompt, tests them, and tells you
whether the best one is really better. It calls a new prompt better only when that is shown on test cases it never saw
while writing it. If nothing wins, it says so and shows the numbers.

<Diagram name="proof" caption="How Improve decides: candidates are tested on the improve part, the best is checked on the held-back part." />

## Prerequisites

- A finished run on your approved test cases, with its answers scored. Improve starts from that run.
- At least 5 test cases in the part used to write improvements, and at least 15 in the held-back part, which is about 20
  approved cases at the default 70/30 split. With fewer, Improve still runs but can say only "not proven".
- A model to write the improvements. By default it is the judge model of the run you start from.

## Basic workflow

1. Open the **Improve** step of the project, after **Results**.
2. Press **Find what's failing and suggest fixes**. Verano shows a rough cost first.
3. Wait for the verdict. A finished session shows, for each round, the candidates, their scores and the one it kept.

What happens behind that button:

1. The failing cases from the **improve** part of your data are grouped by why they fail.
2. Several candidate prompts are written (4 per round by default).
3. Each candidate gets a **quick check** on a small fixed sample. Only the best two get the full test on the improve part.
4. The best candidate is run on the **held-back** part and compared, case by case, with your current prompt.
5. The result is one of **Proven better**, **Not proven** or **Worse**, with the pass rates, the size of the difference and
   how many held-back cases were judged.

If the verdict is **Proven better**, **Accept as new version** saves the candidate as the next version of the prompt. If
you use labels, accepting can move a label such as `production` to it.

## Rounds

A session runs up to 3 rounds by default (at most 6). Each round starts from the best prompt so far. A winner of any round
still has to pass the held-back test against the current prompt, so a long search cannot talk itself into a result.

## Control the cost

- Verano shows a rough cost before the session starts. It covers the writing, the tests and the judging.
- **Stop** ends the session and keeps what has been done.
- A session can carry a spending cap (`budget_cap` in the API). A test that reaches it pauses, finished answers are kept,
  and you can raise the cap and resume it from the **Run** screen.
- The API also takes `rounds` (1 to 6), `population` (candidates per round, 2 to 8), `quick_check` (on by default) and
  `target_effect` (the gain worth detecting, 0.1 by default). With the quick check off, every candidate gets the full test,
  which costs more.

## Reading the verdict

"Proven better" needs a clear gap on at least 15 held-back cases. A gap is clear when it is larger than chance would
explain, tested with a paired bootstrap and a 95% interval. A small gain on a few cases is shown as **Not proven**, not
hidden: the numbers are on screen so you can judge for yourself.

> **Note:** a prompt that is clearly better on one comparison is not necessarily proven. "Clearly better" compares two
> prompts or models on at least 10 cases both were judged on. "Proven" also asks for held-back cases the writer never saw.

## Use it from an AI agent

The `verano mcp` server offers `propose_improvement`, `get_improvement` and `accept_improvement`. The first and the last
change things, so the server must be started with `--allow-write`. See [the command line](../../cli/README.md).

<Diagram name="mcp" caption="An AI agent reaches Verano through verano mcp." />

## Practical guidance

- Approve a few more than 20 cases. The held-back part is what makes "proven" possible.
- Put hard cases in your data, not only easy ones. Improve can only fix what the cases show.
- Use a judge model at least as capable as the models you test, and read a few judged answers yourself.
- Do not accept a prompt because it is new. Accept it because the held-back result is clear.
- If the verdict is **Not proven**, add cases and run again. More held-back cases make a real gain easier to show.

> **Note:** so far Verano's own checks of this loop have run on a test provider and free models, not on a paid model. Treat
> your first real-model run as part of the evidence.
