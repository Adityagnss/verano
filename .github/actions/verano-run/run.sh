#!/usr/bin/env bash
# Runs `verano run --ci` and records the outcome for the later steps; the last step of the action fails the job.
# Exit codes: 0 gate passed, 2 gate failed, 1 anything else (including a revoked or expired token).
set -u

results="${RESULTS_FILE:?}"
log="$(mktemp)"
args=(run --ci --yes --timeout "${VERANO_TIMEOUT:-1800}" --markdown-file "$results" -f "${VERANO_FILE:-verano.yaml}")
[ -n "${VERANO_PROMPT:-}" ] && args+=("${VERANO_PROMPT}")
[ -n "${VERANO_BASELINE:-}" ] && args+=(--baseline "${VERANO_BASELINE}")
[ -n "${VERANO_MAX_COST:-}" ] && args+=(--max-cost "${VERANO_MAX_COST}")

verano "${args[@]}" 2> >(tee "$log" >&2)
code=$?
wait

if [ "$code" -eq 1 ] && grep -qiE "invalid, expired or revoked|no longer works|not signed in" "$log"; then
  message="The Verano token was revoked, has expired or is wrong. Create a new one with \`verano token create --name ci\` and update the repository secret that holds it."
  echo "::error title=Verano token rejected::${message}"
  printf '<!-- verano-run-results -->\n## Verano prompt check\n\n%s\n' "$message" > "$results"
elif [ "$code" -eq 2 ]; then
  echo "::error title=Verano gate failed::The prompt did not meet the gate. See the results table."
elif [ "$code" -ne 0 ] && [ ! -s "$results" ]; then
  printf '<!-- verano-run-results -->\n## Verano prompt check\n\nThe check could not finish. See the job log for the reason.\n' > "$results"
fi

{
  echo "exit-code=$code"
  echo "results-file=$results"
} >> "${GITHUB_OUTPUT:-/dev/null}"
[ -s "$results" ] && [ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$results" >> "$GITHUB_STEP_SUMMARY"
exit 0
