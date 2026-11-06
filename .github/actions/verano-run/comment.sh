#!/usr/bin/env bash
# Posts the results table on the pull request, or updates the comment an earlier run left (found by its hidden marker).
set -eu

[ -s "${RESULTS_FILE:?}" ] || exit 0
api="https://api.github.com/repos/${REPOSITORY:?}"
auth=(-H "Authorization: Bearer ${GITHUB_TOKEN:?}" -H "Accept: application/vnd.github+json")
body="$(python3 -c 'import json,sys; print(json.dumps({"body": open(sys.argv[1]).read()}))' "$RESULTS_FILE")"

existing="$(curl -fsS "${auth[@]}" "$api/issues/${PULL_NUMBER:?}/comments?per_page=100" |
  python3 -c 'import json,sys
for c in json.load(sys.stdin):
    if "<!-- verano-run-results -->" in c.get("body", ""):
        print(c["id"]); break')"

if [ -n "$existing" ]; then
  curl -fsS -X PATCH "${auth[@]}" -d "$body" "$api/issues/comments/$existing" > /dev/null
else
  curl -fsS -X POST "${auth[@]}" -d "$body" "$api/issues/${PULL_NUMBER}/comments" > /dev/null
fi
echo "Posted the Verano results on pull request #${PULL_NUMBER}."
