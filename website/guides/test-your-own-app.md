# Test your own app

When your product is more than a prompt and a model (a chatbot, an API, a RAG app), connect it and Verano scores it on the same test cases as your models. Verano sends each test case to your app over HTTP, reads the answer out of the reply, and can also score the retrieved text and the tool calls.

Open the **Apps** page of a project and press **Connect an app**. There are three short steps.

## 1. Where is your app?

Paste the **address** Verano should send questions to, for example `https://my-app.example.com/ask`. A name is optional. **Check connection** saves the app and sends it one short greeting, nothing else.

### Allowed hosts

Verano refuses to call addresses on private networks (localhost, internal hosts), so a test case cannot be used to probe your network. A server owner allows specific hosts with the `VERANO_APP_ALLOWED_HOSTS` setting in `.env`, a JSON list:

```bash
VERANO_APP_ALLOWED_HOSTS=["localhost","my-app.internal"]
```

Empty (the default) means only public addresses can be called. Restart the stack after changing `.env`. If your app runs on your own machine, remember that Verano itself runs in Docker, so use a host name the containers can reach and list that name.

## 2. What does it expect?

Pick the shape closest to your app, then adjust the details:

- **Request template.** JSON that Verano sends as a `POST`. Write `{{ name | tojson }}` where a test case's input goes, using the same names as your prompt's variables. The page shows a preview of the exact request.
- **Answer path.** Where in the reply the answer is, for example `$.answer`.
- **Retrieved text path (optional).** For a RAG app, for example `$.sources[*].text`, so the retrieved passages can be checked.
- **Tool calls path (optional).** For example `$.tool_calls`.

Under **Advanced** you set sign-in (none, bearer token, username and password, or a custom header; secrets are stored encrypted and never shown again), a timeout, and whether to **talk to it turn by turn with a simulated user**, where a judge model plays the user.

## 3. Try one test case

Fill in the inputs your request uses, one per line as `name=value`, and press **Send it**. Verano shows what was sent, what came back (status and time) and what it read from the reply. Nothing is stored. If the answer is empty or wrong, fix the answer path here, before you run.

Then **Run on my test cases**. Your app appears as a column next to the models, and cost and speed are shown like any other run.

## From the command line

```bash
verano app list
verano app add        # connect an app
verano app test       # send one test case and show what was sent and read
```

See [the command line](/reference/cli).

## Settings

The server has limits for app calls in `.env.example`: `VERANO_APP_TIMEOUT_S`, `VERANO_APP_CONCURRENCY` and `VERANO_APP_RETRY_ATTEMPTS` (extra attempts after a failed call, 0 by default).
