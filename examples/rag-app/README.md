# Example: rag-app

A tiny support-desk question-answering app with retrieval, for testing Verano against your own app over
HTTP. It has no model, needs no API key and no network, and uses only the Python standard library
(3.10+). Answers are deterministic, so it is a stable target.

```text
app.py        the HTTP app: a small retriever plus a rule-based "generator"
docs/*.md     10 short support documents (refunds, shipping, password reset, invoices, ...)
cases.csv     12 test cases: question,expected_answer (10 answerable, 2 not answerable)
```

## How it works

1. The question is lowercased, split into tokens, and stopwords are dropped.
2. Each document is scored by a TF-IDF-like overlap: the sum of the rarity weights of the question words
   it contains (title matches count extra). The top 2 documents are the retrieved sources.
3. The "generator" answers with the best-matching sentence of the top document. If the best score is too
   low it answers `I could not find that in the support documents.` and returns no sources.

## Run it

```bash
cd examples/rag-app
python app.py                       # http://127.0.0.1:8801   (--port and --host to change)
```

```bash
curl -s -X POST http://127.0.0.1:8801/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "How long do refunds take?"}'
```

## Request and response

```json
POST /ask   {"question": "How long do refunds take?"}

200         {"answer": "They usually take 5 to 7 business days to appear on your statement.",
             "sources": [{"id": "refunds", "text": "You can request a refund within 30 days ..."},
                         {"id": "...", "text": "..."}]}
```

A bad body gets `400`. An unanswerable question gets the "could not find" answer and `"sources": []`.

## Verano mapping

| Verano field | Value |
| --- | --- |
| URL / method | `http://127.0.0.1:8801/ask`, POST |
| Request body | `{"question": "{{input}}"}` (the question column of `cases.csv`) |
| Answer | `$.answer` |
| Retrieved chunks | `$.sources[*].text` |
| Test cases | `cases.csv` (`question`, `expected_answer`) |

With the retrieved chunks mapped, Verano can check that the answer is grounded in what was retrieved, and
whether the right documents were found. The two unanswerable rows check that the app declines instead of
guessing.
