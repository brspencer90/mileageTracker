#!/usr/bin/env bash
# Run once, as a repo admin, AFTER ci.yml/deploy.yml are on main (the "validate"
# check must have run at least once before it can be required). Needs the gh CLI:
#   gh auth login && bash scripts/setup-branch-protection.sh
set -euo pipefail
REPO="${1:-brspencer90/mileageTracker}"
gh api -X PUT "repos/${REPO}/branches/main/protection" \
  -H "Accept: application/vnd.github+json" --input - <<'JSON'
{
  "required_status_checks": { "strict": true, "checks": [ { "context": "validate" } ] },
  "enforce_admins": true,
  "required_pull_request_reviews": { "required_approving_review_count": 0, "require_code_owner_reviews": false, "dismiss_stale_reviews": true },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
JSON
echo "Branch protection set on ${REPO}: PR required, 'validate' must pass, self-merge allowed."
