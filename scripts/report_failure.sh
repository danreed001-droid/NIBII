#!/usr/bin/env bash
# A workflow's failure step: open a GitHub issue that @mentions the owner (once per title) and add the same line
# to the scanner page's issues log (data/issues_log.json, mtl/health.py), committed from a clean copy of main so a
# half-finished run's files are never pushed.
#   scripts/report_failure.sh "Scanner run failed 2026-10-19" "What failed and what it means." [source]
# Needs GH_TOKEN, OWNER and the usual GITHUB_* variables; the job needs contents: write and issues: write.
set -u
title="$1"; what="$2"; src="${3:-run}"
run_url="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"

if gh issue list --repo "$GITHUB_REPOSITORY" --state all --search "\"$title\" in:title" --json title \
     --jq ".[] | select(.title == \"$title\") | .title" | grep -q .; then
  echo "issue already open: $title"
else
  printf '%s\n\nRun log: %s\n\n@%s - sent automatically.\n' "$what" "$run_url" "${OWNER:-}" > "$RUNNER_TEMP/fail.md"
  gh issue create --repo "$GITHUB_REPOSITORY" --title "$title" --body-file "$RUNNER_TEMP/fail.md" || echo "could not open the issue"
fi

# the issues log, from a fresh worktree of main
wt="$RUNNER_TEMP/issues-log"
git fetch -q origin main && git worktree add -q --detach "$wt" origin/main || { echo "could not check out main for the issues log"; exit 0; }
cd "$wt"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
for i in 1 2 3; do
  python scripts/log_issue.py "$src" "$what" || break
  git add data/issues_log.json
  git diff --cached --quiet && exit 0
  git commit -q -m "Issues log: $title"
  git push -q origin HEAD:main && exit 0
  sleep 10
  git fetch -q origin main && git reset -q --hard origin/main
done
echo "could not push the issues log"
