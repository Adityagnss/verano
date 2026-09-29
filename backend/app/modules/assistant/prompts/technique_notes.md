# Prompting notes

What is known about which prompt changes help, taken from a measured tutorial ("Prompt Engineering Tutorial 2026: Prove Which Prompts Work", ranjankumar.in/prompt-engineering) and the studies it cites. The numbers come from a small 3B local model on a 12-question suite, so read them as evidence about the *method*, not as promises for your task. Verano's Improve step reads these same notes when it writes candidate prompts.

## The one habit: measure first

- Almost every prompt claim is a statement about a difference between two scores. Whether that difference means anything depends on how much the score moves when nothing changes (the spread).
- A gain smaller than the spread is noise. Run each prompt more than once before believing a difference.
- Change one thing at a time, and test on your own inputs. Twenty real inputs with the answers you wanted beat any borrowed benchmark.

## What a prompt is made of

- Instruction: the task, the rules, the output contract. Most advice is aimed here.
- Examples: worked demonstrations shown before the real question. They teach the task and fix the output format.
- Input: the documents and the question. Where you place them changes what the model can use.
- Output format: the schema and settings that constrain the answer while it is being written.

## Use these

- State the exact output format: the shape, the allowed values, one-line rules. This is the most dependable fix for answers that come back in the wrong form.
- Reasoning before the answer, in JSON. With a reasoning field and an answer field, put reasoning first. Answer-first order cost about 39 points on multi-step problems, and it used fewer tokens than free-text step-by-step (122 against 264). Declaring the work first costs nothing.
- Keep schemas plain (strings, numbers, booleans, fixed choices, nested objects) and check strict rules such as patterns in a second pass in your own code.
- Stable material first, the question last. Put documents and reference text before the question and delimit them clearly. A model can only use what it has already read.

## Measure these (they depend on the model and the task)

- Chain of thought (ask for step-by-step reasoning, then a marked final answer). On a plain model it gave +75 points on multi-step arithmetic, but nothing on single-step questions, and it cost about 53 times the output tokens and about 6 times the time. Across many datasets it is worth about 14 points on symbolic work and under 1 point elsewhere. Do not add it to classification or lookup tasks.
- Reasoning models react differently. One study found +13.5 points on a plain model and -3.3 on a reasoning model for the same instruction. A model that already thinks before answering makes the instruction redundant. Check which kind of model you use.
- Few-shot examples. Two examples moved accuracy from 91.7 to 97.2, then more examples stopped helping and each one adds roughly 300 input tokens to every call. On strong models the examples mostly fix the format. Show them as earlier conversation turns, not as one block labelled "Examples". Use examples close to the failures.
- Majority vote (ask several times, take the most common answer). +8.3 points for three times the tokens on a small model that makes errors; near its ceiling a model gains almost nothing. Worth it only where individual answers are often wrong.
- Input order. The published gain for putting the question last did not reproduce on a small test, but the rule still stands because the cause (a model reads left to right) does.

## Do not build a candidate around these

- Expert personas ("you are a world-class expert"): about +2.8 points, inside the noise. They steer tone, not accuracy.
- Politeness ("please", "thank you"): no measured effect. It only spends tokens.
- Offered rewards or threats ("I'll tip $200"): no reliable effect, and a hint of harm on hard cases.
- Asking the model to check its own answer with no new information: it does not help and can make answers worse.

## How the main techniques work

### Chain of thought

The model writes its working before the answer, so each step can build on the previous one. It pays on multi-step problems and on plain models; it costs extra output tokens, and reasoning models already do it internally.

### Few-shot examples

Two to four solved examples come before the real question, ideally as earlier conversation turns. They fix the format and show the pattern. Pick examples that look like your failures.

### Reasoning first in JSON

A JSON answer is written left to right, so the field order is the order of thinking. Reasoning before the answer lets the answer use the working; answer first forces a guess.

### Majority vote

Ask the same question several times and keep the most common answer. Useful when single answers are often wrong; wasteful when the model is already right almost every time.

### Prompt chaining

Split a big task into small prompts, for example extract, then decide, then format the answer. Each step is short, can be tested on its own, and a failure points at one step. It costs more calls and adds delay.

### Context first, question last

Put the reference text and rules first and the question or instruction at the end, with clear delimiters around the text. The model reads left to right and can only use what it has already read.

### Prompt caching

Providers reuse the already-read start of a prompt. Keep instructions, examples and reference text at the start, unchanged between calls, and put the part that changes last. Reading a cached prefix was about 100 times faster and about a tenth of the price.

### AI judge

A second model scores the first model's answer against a written rubric. Ask for a pass or fail with the reasoning first, use exact checks wherever they can decide, and audit the judge against answers you labelled yourself.

### Untrusted text and injection

Text you did not write (a document, an email, a spreadsheet cell) can contain instructions, and the model may follow them. Marking the text as data helps but is not a guarantee. Add such a case to the tests, and limit what the model is allowed to do.

### Automatic prompt search

Instead of guessing improvements by hand, generate several candidate prompts, score each on the same test cases, and keep the one that wins on cases it was not written from. This is what the Improve step does.

## Scoring answers

- Use exact, rule-based checks first. They are free and never drift. Add an AI judge only for what rules cannot decide.
- A judge should give a binary pass or fail against a written rubric, not a score out of five, and should write its reasoning before the verdict.
- A judge is a model. Audit it against answers you labelled yourself: a stable judge can be stably wrong (one judge rejected 17 percent of good answers while being perfectly repeatable). For pairwise comparisons, run both orders, since order changes winners.

## Speed and cost

- Put stable content (instructions, examples, reference text) at the start of the prompt and the changing part at the end. Providers then reuse the already-read prefix: reading it again took 1.6 seconds instead of 207, and cached input is billed at about a tenth of the normal rate.
- Long prompts can be cut off silently. Check the model's context window and give reasoning-heavy answers a large reply limit.

## Safety

- Delimiters around untrusted text are an instruction, not a security boundary. A model will follow instructions found inside a document it was handed.
- Add an injection case to the test set ("ignore your instructions and …" inside the input). If the consequences of being hijacked are real, fix it in the design of the system, not only in the prompt.

## Checklist for a new prompt version

- Is the output format stated exactly, with allowed values?
- If the answer is JSON, does reasoning come before the answer?
- Is the reference material before the question?
- Are the examples close to the real failures, and only as many as help?
- Was it run more than once, and is the gain bigger than the spread?
