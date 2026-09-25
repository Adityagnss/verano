"""
Verano backend package: FastAPI app, feature modules and Celery workers.

Two LiteLLM import-time behaviours are switched off here, before anything can import it:
- `LITELLM_MODE=PRODUCTION` stops it from loading a `.env` file (searched upward from the
  working directory) into the process environment. Configuration comes only from
  `Settings`; a developer's local `.env` must never leak into tests or workers.
- `LITELLM_LOCAL_MODEL_COST_MAP=True` makes it use the model metadata bundled with the
  pinned LiteLLM version instead of downloading the latest from GitHub at startup, so a
  self-hosted install makes no outbound call and prices are reproducible per version.
Both are defaults, so an operator can still override them explicitly.
"""

import os

os.environ.setdefault("LITELLM_MODE", "PRODUCTION")
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
