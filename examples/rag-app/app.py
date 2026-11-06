"""Verano example: a tiny support RAG app. Standard library only, no model, no network.

POST /ask  {"question": "..."}  ->  {"answer": "...", "sources": [{"id": "...", "text": "..."}]}
"""
import argparse
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DOCS_DIR = Path(__file__).parent / "docs"
NO_ANSWER = "I could not find that in the support documents."
MIN_SCORE = 0.5  # below this the retriever's best match is treated as "not found"
STOPWORDS = set(
    "a an and are as at be by can could do does for from how i in is it my of on or our so that the "
    "their then there these this to was we what when where which who why will with you your me us "
    "if not no any".split()
)


def tokens(text):
    out = []
    for t in re.findall(r"[a-z0-9]+", text.lower()):
        if t in STOPWORDS:
            continue
        if len(t) > 3 and t.endswith("s"):  # crude plural folding: refunds -> refund
            t = t[:-1]
        out.append(t)
    return out


def load_docs():
    docs = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        lines = text.splitlines()
        title = lines[0].lstrip("# ").strip()
        body = " ".join(lines[1:]).strip()
        docs.append({"id": path.stem, "title": title, "body": body, "tokens": set(tokens(title + " " + body))})
    return docs


DOCS = load_docs()


def idf(term):
    df = sum(1 for d in DOCS if term in d["tokens"])
    return math.log(1 + len(DOCS) / (1 + df)) if df else 0.0


def score(query_tokens, doc):
    # Sum of IDF weights of query terms found in the document, plus a bonus for title hits.
    title = set(tokens(doc["title"]))
    return sum(idf(t) * (1.5 if t in title else 1.0) for t in set(query_tokens) if t in doc["tokens"])


def retrieve(question, k=2):
    q = tokens(question)
    ranked = sorted(((score(q, d), d) for d in DOCS), key=lambda x: -x[0])
    return q, [(s, d) for s, d in ranked[:k] if s > 0]


def best_sentence(q, doc):
    sentences = re.split(r"(?<=[.!?])\s+", doc["body"])
    return max(sentences, key=lambda s: len(set(q) & set(tokens(s))))


def ask(question):
    q, hits = retrieve(question)
    if not hits or hits[0][0] < MIN_SCORE * 3:
        return {"answer": NO_ANSWER, "sources": []}
    return {
        "answer": best_sentence(q, hits[0][1]),
        "sources": [{"id": d["id"], "text": d["body"]} for _, d in hits],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/ask":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length) or b"{}")
            question = data["question"]
            if not isinstance(question, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return self._send(400, {"error": 'send JSON like {"question": "..."}'})
        self._send(200, ask(question))

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8801)
    a = p.parse_args()
    print(f"rag-app listening on http://{a.host}:{a.port}/ask")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
