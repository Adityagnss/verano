#!/usr/bin/env sh
# Remove the Postgres, Valkey and Caddy containers Verano's tests start (label dev.verano.test).
# Testcontainers normally removes them when a test session ends, but a run that is stopped
# partway can leave them running. While a Verano test run is still going, only stopped ones
# are removed, so that run keeps its databases. No other project's container is touched.
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
if pgrep -f "$ROOT/backend/.venv/bin/pytest" >/dev/null 2>&1; then
  ids=$(docker ps -aq --filter label=dev.verano.test --filter status=exited --filter status=created)
else
  ids=$(docker ps -aq --filter label=dev.verano.test)
fi
if [ -n "$ids" ]; then
  # shellcheck disable=SC2086 # one container id per word
  docker rm -f $ids >/dev/null
fi
