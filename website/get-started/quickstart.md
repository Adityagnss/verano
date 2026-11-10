# Quickstart

You will run Verano on your own machine and make a first project. This takes a few minutes plus the time Docker needs to build the images the first time.

## Before you start

- Docker (Desktop or Engine) and `make`.
- A provider key (OpenAI, Anthropic, Gemini and others), or a local model through [Ollama](https://ollama.com) with no key at all.
- Verano is not published as a package or a hosted service yet, so you start from a clone of the repository.

## 1. Start Verano

```bash
git clone https://github.com/Adityagnss/verano.git
cd verano
make env && make up
```

`make env` creates `.env` with fresh secrets (it never overwrites an existing one). `make up` builds the images, starts the stack and waits until every service is healthy. Stop it with `make down`; your data is kept.

Open [http://localhost:8080](http://localhost:8080) and create an account.

::: tip Behind a company firewall that re-signs HTTPS?
If `make up` fails with `x509: certificate signed by unknown authority`, follow the fix in [Self-hosting](/self-hosting/#behind-a-company-firewall-that-re-signs-https).
:::

## 2. Make your first project

The home screen shows the next step for your project. The path is the same every time:

1. **Connect a model provider.** Add a key on the Keys screen, or add the "Ollama (local)" provider to use a local model. Verano checks the key and lists the models it can use.
2. **Write your prompt.** Paste the instructions you want to test, or press **Write it for me** to draft one from your documents ([guide](/guides/write-a-prompt-from-documents)).
3. **Add examples and approve test cases.** Upload a few examples. Verano drafts test cases, expected answers and checks. Generation shows its cost first, and you approve every case that counts.
4. **Run the test.** Pick the models. Verano shows the estimated cost and asks before it starts. Each model answers each case more than once.
5. **Read the results.** Quality, cost, speed and consistency per model, with the reasons for each score.
6. **Improve the prompt.** Verano writes better versions, tests them, and tells you whether the best one is proven on held-back cases, or *Not proven* ([guide](/guides/improve-a-prompt)).

## Use local models for free

Install Ollama (`brew install ollama`), run `make models`, then add the "Ollama (local)" provider on the Keys screen. `make up-local` runs Ollama in a container instead.

## From your codebase

The command-line tool finds the prompts in your code and sets a project up for you:

```bash
uv tool install ./cli      # from the clone, today
verano login && verano init && verano push && verano run
```

See [the command line](/reference/cli) for every command.

## Next

- [Improve a prompt](/guides/improve-a-prompt)
- [Test your own app](/guides/test-your-own-app)
- [Self-hosting on a server](/self-hosting/)
