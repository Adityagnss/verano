What is known about which prompt changes help, from measured experiments (not folklore).
Use it to choose different strategies for the 3 candidates, and never rely on a technique
that is known not to help.

- Measure, don't assume: a gain smaller than the run-to-run spread is noise.
- Say exactly what the output must look like: the format, the allowed values, one-line rules.
  This is the most reliable change for outputs that break the format.
- Step-by-step reasoning (chain of thought) helps plain models on multi-step tasks (large
  gains measured) but adds cost and can hurt reasoning models, and does nothing for
  classification or lookup. Ask for the reasoning first, then a clearly marked final answer.
- Worked examples (few-shot, 2 to 4 close to the failures) mostly fix the output format;
  the gain varies by model and is larger for small models.
- When the answer is JSON with a reasoning field and an answer field, put the reasoning
  field first: answer-first order cost about 39 points on multi-step problems.
- Put reference material and the input before the question, the question or instruction
  last, and delimit the input clearly.
- Personas ("you are a world-class expert") change tone, not accuracy. Politeness and
  offered rewards had no reliable effect. Asking the model to check its own answer without
  new information does not help. Do not build a candidate around these.
- A rule for ambiguous or multi-issue inputs, and a guard against instructions inside the
  input, are worth one candidate when the failures show such inputs.
