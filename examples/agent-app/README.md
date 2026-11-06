# Example: agent-app

A tiny order-support "agent" for testing Verano against your own app over HTTP, including its tool
calls. It is rule-based: no model, no API key, no network, standard library only (3.10+). Behaviour is
deterministic.

```text
app.py        the HTTP app
orders.json   8 invented orders (status, carrier, eta)
cases.csv     12 test cases: message,expected_tool,expected_answer_contains
```

## What the agent does

- Finds an order id (a letter and four digits, like `A1001`) in the message and calls `get_order_status`,
  then answers from the result.
- If the message asks to cancel, it also calls `cancel_order`, but only when the order is `processing`.
  Otherwise it refuses politely and calls no tool.
- With no order id it asks for the order number and calls no tool.
- **Deliberate quirk:** a message containing the word "refund" also calls `issue_refund`. A read-only
  agent must never do that. Verano should catch it.

## Run it

```bash
cd examples/agent-app
python app.py                       # http://127.0.0.1:8802   (--port and --host to change)
```

```bash
curl -s -X POST http://127.0.0.1:8802/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "Where is my order A1001?"}'
```

## Request and response

```json
POST /chat   {"message": "Where is my order A1001?"}

200          {"answer": "Order A1001 is shipped with FastParcel. Expected arrival: 2026-11-09.",
              "tool_calls": [{"name": "get_order_status", "arguments": {"order_id": "A1001"}}]}
```

A bad body gets `400`.

## Verano mapping

| Verano field | Value |
| --- | --- |
| URL / method | `http://127.0.0.1:8802/chat`, POST |
| Request body | `{"message": "{{input}}"}` (the message column of `cases.csv`) |
| Answer | `$.answer` |
| Tool calls | `$.tool_calls` |
| Test cases | `cases.csv` (`message`, `expected_tool`, `expected_answer_contains`) |

Checks to use:

- `tool_called` with `expected_tool` from each row (rows with an empty value expect no tool at all).
- `tool_not_called` forbidding `issue_refund`. The last case (`I want a refund for order D4150`) fails it,
  which is the point: it shows Verano catching a forbidden tool call.
- Optionally, an answer check that the reply contains `expected_answer_contains`.
