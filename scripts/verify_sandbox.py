"""
Send hostile checks to the real sandbox container and print what happens (pending check 19, scenario S6.8).

Run with the stack's sandbox service up:

    docker compose up -d --wait sandbox
    docker compose exec -T backend python - < scripts/verify_sandbox.py

Every row except the first should say ok=False. The container's own walls (no internet, read-only filesystem, no
capabilities, limits) are checked with `docker compose exec sandbox ...` and `docker inspect`; see
docs/checkpoints/phase-8-9.md.
"""

import json
import time
import urllib.request

URL = "http://sandbox:8099/run"
CASES = {
    "a good check": "def check(case):\n    return (1.0, 'fine')\n",
    "a check that never ends": "def check(case):\n    while True:\n        pass\n",
    "read a file": "def check(case):\n    return open('/etc/passwd').read()\n",
    "open a socket (import)": "import socket\ndef check(case):\n    return True\n",
    "import os": "import os\ndef check(case):\n    return True\n",
    "allocate 2 GB": "def check(case):\n    x = bytearray(2 * 1024 * 1024 * 1024)\n    return 1.0\n",
    "import builtins": "def check(case):\n    return 1.0\nimport builtins\n",
    "sleep past the wall time": "import time\ndef check(case):\n    time.sleep(60)\n    return 1.0\n",
    "huge output": "def check(case):\n    return (1.0, 'x' * 10_000_000)\n",
}

for name, code in CASES.items():
    body = json.dumps({"code": code, "case": {"inputs": {}, "output": "a", "expected": "a", "rubric": []}}).encode()
    request = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    began = time.time()
    try:
        out = json.loads(urllib.request.urlopen(request, timeout=30).read())
    except Exception as error:
        out = {"transport_error": str(error)[:100]}
    error_text = str(out.get("error") or out.get("transport_error"))[:90]
    chars = len(out.get("reason") or "")
    took = time.time() - began
    print(f"{name:28s} {took:5.2f}s  ok={out.get('ok')} error={error_text!r} reason_chars={chars}")
