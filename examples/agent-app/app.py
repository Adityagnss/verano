"""Verano example: a tiny rule-based order agent. Standard library only, no model, no network.

POST /chat  {"message": "..."}  ->  {"answer": "...", "tool_calls": [{"name": "...", "arguments": {...}}]}

Known quirk (on purpose, so Verano can catch it): a message containing the word "refund" also calls
`issue_refund`, a tool a read-only agent must never call.
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ORDERS = json.loads((Path(__file__).parent / "orders.json").read_text(encoding="utf-8"))
ORDER_ID = re.compile(r"\b[A-Z]\d{4}\b")


def chat(message):
    calls = []
    lower = message.lower()
    m = ORDER_ID.search(message)
    quirk = bool(re.search(r"\brefunds?\b", lower))
    if not m:
        answer = "Please tell me your order number (a letter and four digits, like A1001) and I will help."
        if quirk:  # the quirk fires even without an order number
            calls.append({"name": "issue_refund", "arguments": {}})
        return {"answer": answer, "tool_calls": calls}

    oid = m.group(0)
    calls.append({"name": "get_order_status", "arguments": {"order_id": oid}})
    order = ORDERS.get(oid)
    if order is None:
        answer = f"I could not find an order {oid}. Please check the number."
    elif re.search(r"\bcancel", lower):
        if order["status"] == "processing":
            calls.append({"name": "cancel_order", "arguments": {"order_id": oid}})
            answer = f"Order {oid} was processing, so I have cancelled it."
        else:
            calls = []  # politely refuse and call no tool
            answer = f"Sorry, I cannot cancel order {oid} because it is {order['status']}. Only processing orders can be cancelled."
    elif order["status"] == "cancelled":
        answer = f"Order {oid} is cancelled."
    elif order["status"] == "delivered":
        answer = f"Order {oid} was delivered by {order['carrier']} on {order['eta']}."
    else:
        answer = f"Order {oid} is {order['status']} with {order['carrier']}. Expected arrival: {order['eta']}."
    if quirk:
        calls.append({"name": "issue_refund", "arguments": {"order_id": oid}})
    return {"answer": answer, "tool_calls": calls}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/chat":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            message = json.loads(self.rfile.read(length) or b"{}")["message"]
            if not isinstance(message, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"error": 'send JSON like {"message": "..."}'})
        self._send(200, chat(message))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8802)
    a = p.parse_args()
    print(f"agent-app listening on http://{a.host}:{a.port}/chat")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
