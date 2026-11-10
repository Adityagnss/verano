# Real OTLP requests

`openinference.pb` and `openllmetry.pb` are the exact bytes the real Python exporter (`opentelemetry-exporter-otlp-proto-http`
1.45.2) sent for one OpenAI chat call made with the real OpenAI SDK (3.49.0) instrumented by the real
`openinference-instrumentation-openai` (0.1.69) and `opentelemetry-instrumentation-openai` (OpenLLMetry 0.63.0).
The call went to a local stand-in server; the question is "How long do refunds take?" and the answer "Refunds take 30 days."
Captured on 2026-11-10. They contain no secrets.
