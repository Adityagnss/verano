#!/usr/bin/env sh
# Prove `make ci` needs no network once dependencies and base images were fetched once:
# Verano's own builder container is disconnected from the network, and uv and npm are
# forced offline. The builder is reconnected on every exit path, including Ctrl-C.
# Only Verano's builder (buildx_buildkit_verano0) is touched; no other container is.
set -u
BUILDER_CONTAINER=buildx_buildkit_verano0
reconnect() {
  docker network connect bridge "$BUILDER_CONTAINER" 2>/dev/null || true
}
trap reconnect EXIT INT TERM
docker network disconnect bridge "$BUILDER_CONTAINER" 2>/dev/null || true
UV_OFFLINE=1 npm_config_offline=true make --no-print-directory ci
status=$?
if [ "$status" -eq 0 ]; then
  echo "make ci passed with no network access."
else
  echo "make ci needed the network (exit $status)."
fi
exit "$status"
