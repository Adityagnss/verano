#!/usr/bin/env sh
# Pull the local development models (DEVELOPMENT.md E3) into the Ollama at OLLAMA_HOST
# (default: the native Ollama on this machine). Downloads resume if interrupted.
set -eu
MODELS="${MODELS:-qwen2.5:3b qwen2.5:7b llama3.2:3b gemma2:2b}"
for model in $MODELS; do
  echo "Pulling $model"
  ollama pull "$model"
done
