"""
Create .env from .env.example with freshly generated secrets.

Fills VERANO_MASTER_KEYS (a Fernet key: 32 random bytes, url-safe base64) and
VERANO_JWT_SECRET, and configures local plain-HTTP use: the refresh cookie is not marked
Secure, because Safari/WebKit won't send Secure cookies to http://localhost (measured in
the Phase 1 browser tests). Never overwrites an existing .env, so running it twice is safe.
Standard library only, so it works before any dependency is installed. Run: `make env`.
"""

import base64
import os
import re
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_OVERRIDES = {"VERANO_REFRESH_COOKIE_SECURE": "false"}
LOCAL_NOTE = (
    "Local HTTP mode: the refresh cookie is not marked Secure (Safari needs this on "
    "http://localhost). Serving over HTTPS? Set VERANO_REFRESH_COOKIE_SECURE=true and "
    "VERANO_ENVIRONMENT=production."
)
SECRETS = {
    "VERANO_MASTER_KEYS": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "VERANO_JWT_SECRET": lambda: secrets.token_urlsafe(48),
}


def main() -> int:
    target = ROOT / ".env"
    if target.exists():
        print(".env already exists; leaving it unchanged.")
        return 0
    text = (ROOT / ".env.example").read_text()
    for name, generate in SECRETS.items():
        text = re.sub(rf"^{name}=$", f"{name}={generate()}", text, flags=re.MULTILINE)
    for name, value in LOCAL_OVERRIDES.items():
        text = re.sub(rf"^{name}=.*$", f"{name}={value}", text, flags=re.MULTILINE)
    target.write_text(text)
    target.chmod(0o600)
    print("Created .env with new secrets.")
    print(LOCAL_NOTE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
