/** Copy-ready setup text for connecting an app. Pure, so it can be tested. */

export type Snippet = { id: "python" | "node" | "curl"; label: string; code: string }

export function envLines(endpoint: string, token: string): string[] {
  return [
    `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=${endpoint}`,
    `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer ${token}`,
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf",
  ]
}

export function snippets(endpoint: string, token: string): Snippet[] {
  const env = envLines(endpoint, token)
    .map((l) => `export ${l}`)
    .join("\n")
  return [
    {
      id: "python",
      label: "Python",
      code: `${env}\n\n# pip install openinference-instrumentation-openai opentelemetry-sdk opentelemetry-exporter-otlp-proto-http\nfrom opentelemetry.sdk.trace import TracerProvider\nfrom opentelemetry.sdk.trace.export import BatchSpanProcessor\nfrom opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter\nfrom openinference.instrumentation.openai import OpenAIInstrumentor\n\nprovider = TracerProvider()\nprovider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))\nOpenAIInstrumentor().instrument(tracer_provider=provider)`,
    },
    {
      id: "node",
      label: "Node",
      code: `${env}\n\n// npm install @traceloop/node-server-sdk\nimport * as traceloop from "@traceloop/node-server-sdk"\n\ntraceloop.initialize({ disableBatch: false })`,
    },
    {
      id: "curl",
      label: "curl",
      code: `curl -X POST ${endpoint} \\\n  -H "Authorization: Bearer ${token}" \\\n  -H "Content-Type: application/json" \\\n  -d '{"resourceSpans":[]}'`,
    },
  ]
}

export const TESTED_WITH =
  "Verano has been checked with the OpenAI instrumentations of OpenInference and OpenLLMetry only. Other libraries may work, but we have not tested them."
