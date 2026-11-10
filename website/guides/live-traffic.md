# Live traffic

Verano does not trace your app. It takes traces in, so you can turn real questions into test cases and watch quality on live answers. Open the **Traffic** page of a project.

<Diagram name="traffic" caption="Traces in, personal data out, then test cases you approve and live scores that can alert." />

## Import a file

Press **Import a file** and choose an export from your tracing tool. Supported formats:

- Langfuse
- Phoenix
- LangSmith
- OpenTelemetry
- HAR (a browser or proxy capture)

Leave the format on **Work it out for me** and Verano looks at the file and picks one. You can also set a prompt version for records that do not say which prompt produced them, so live scores can be split by version. Records that cannot be used are listed with the reason.

**Personal data is removed before anything is stored**: email addresses, phone numbers and card-like numbers, plus your own regular expressions, under Privacy and storage. You can also set how many days traffic is kept.

From the command line:

```bash
verano traffic import export.json -p my-project   # --format auto looks at the file
verano traffic list
```

## Send spans from your app

Instead of files, point an OpenTelemetry exporter at Verano's receiver (`POST /v1/traces`, also at `/api/v1/otlp/v1/traces`) with an **ingest token** made per project on the Connect tab. Both OTLP protobuf (the Python exporter's default) and OTLP JSON work, plain or gzipped. The page shows how many spans were dropped for being over a rate or size limit; the limits are the `VERANO_TRAFFIC_*` settings in `.env.example`.

## Make test cases from traffic

Filter the list (failed, low rated, slow, new topic, not used yet, or search the questions), select traces, and press **Make cases**. Pick the name of the prompt variable that should get the question, preview, and **Add as drafts**. Repeats of the same question are folded into one. Nothing is used in a test run until you approve it on the Test cases step.

## Live scores

Turn on **Score live traffic** to run the same checks as your tests on a sample of live answers. Rule checks are free. Judge checks cost money, so they run on a small share of traffic and stop at a monthly limit you set. The chart shows the share of answers that pass, by day, and can be split by prompt version.

## Alerts

Add a channel (Slack or a webhook, and email when the server has mail set up) and rules: alert when the pass rate falls below its usual level, or below a fixed level. Alerts fire when quality is clearly lower for more than one day, never for a single bad day, and once per problem. **Send a test** checks the channel, and **Mark as resolved** closes an alert.

## Limits

Verano is not a tracing backend. Use your tracing tool for traces and Verano for what you test and score.
