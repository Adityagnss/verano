# Write a prompt from your documents

If you have documents but no prompt yet (a policy, a manual, a set of past answers), Verano can draft a first prompt from them. It is a starting point you edit, not a finished prompt.

## Steps

1. **Connect a model first.** The drafter needs one model to write with. Add a provider key on the Keys screen (the "Connect models" step). Without one, the button is there but cannot run.
2. **Add your documents.** On the Add examples step, upload the files Verano should read. It extracts the text and splits it into sections.
3. **Open the Write your prompt page** and press **Write it for me**.
4. **Say what the prompt should achieve (optional).** One or two sentences, up to 1,000 characters, for example: *answer customer questions about refunds using our policy.* Leave it empty to let Verano work from the documents alone.
5. **Press "Write the prompt".** Verano shows the draft (system and user text) and a short list of the reasons behind it.
6. **Press "Write another"** if you want a different draft, or **"Use this prompt"** to put the draft into the editor.
7. **Edit and save.** The draft only fills the editor. Nothing is saved until you save it, and the prompt then goes through the same checks as one you wrote yourself.

## Good to know

- The draft is written by the model you connected, so the call is paid like any other model call and is recorded in the call history.
- It uses only the documents you added to this project. They go only to the provider of the model that writes the draft.
- Read the draft before you trust it. The next steps (approved test cases, a run) are how you find out whether it works.

## Next

- Approve test cases and run them: [Quickstart](/get-started/quickstart)
- Make it better, with proof: [Improve a prompt](/guides/improve-a-prompt)
