# OpenTelemetry against the real exporter and instrumentation libraries (2026-11-10)

Done in a spare environment outside the repository, with the real OpenAI SDK sending one chat call to a local stand-in
server, so no key and no hosted service were used.

| Package | Version |
|---|---|
| opentelemetry-sdk, opentelemetry-exporter-otlp-proto-http | 1.45.2 |
| openinference-instrumentation-openai (OpenInference) | 0.1.69 |
| opentelemetry-instrumentation-openai (OpenLLMetry) | 0.63.0 |
| openai | 3.49.0 |

## What was found

1. **The receiver could not hear the standard Python exporter.** `opentelemetry-exporter-otlp-proto-http` sends
   `application/x-protobuf` and has no JSON mode. The receiver accepted JSON only, and its error told people to set
   `OTEL_EXPORTER_OTLP_PROTOCOL=http/json`, which that exporter does not offer. Live tracing from a Python app did not work.
2. **Fixed:** the receiver now also takes `application/x-protobuf` (plain or gzipped), converts it to the JSON it already
   reads (ids as hex text) and answers in protobuf, with the number of dropped spans when there are any
   (`backend/app/modules/traffic/otlp.py`). The new tests send the exact bytes the real exporter produced
   (`backend/tests/fixtures/otlp`).
3. **The spans of both real instrumentation libraries are understood.** Question, answer, model and token counts come
   through for OpenInference (`llm.*`, `input.value`) and OpenLLMetry (`gen_ai.*`). The attribute names in the mapping
   were written from memory and matched.

## What this does not show

- Only the **OpenAI** instrumentation of each library was tried. Their LangChain, LlamaIndex, Anthropic and other
  instrumentations were not, so no other framework is listed as working.
- The JavaScript exporter (which sends JSON) was not run.
- No hosted tool (Langfuse, Phoenix, LangSmith) was involved, and the live receiver was exercised through the test suite,
  not by a Python process sending over a network to a running stack.
