#!/usr/bin/env bash
# Test patch.py against a fresh upstream checkout.
#
# Mimics what the nightly sync workflow does: fetch upstream compose.yml +
# .env.example, apply patch.py, validate the output with `docker compose
# config`, then re-apply to assert idempotency.
#
# Run locally (from repo root) or in CI. Exits non-zero on any failure.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT

cd "$SCRATCH"

echo "→ fetching upstream"
curl -fsSL https://raw.githubusercontent.com/TryGhost/ghost-docker/main/compose.yml -o compose.yml
curl -fsSL https://raw.githubusercontent.com/TryGhost/ghost-docker/main/.env.example -o .env.example
mkdir -p caddy/snippets .github
touch caddy/Caddyfile.example caddy/snippets/Logging .env
cp "$REPO_ROOT/.github/README.coolify.md" .github/
cp "$REPO_ROOT/.github/CLAUDE.coolify.md" .github/
cp "$REPO_ROOT/.github/scripts/patch.py" .

assert_absent() {
  if grep -qE "$1" compose.yml; then
    echo "unexpected match for /$1/ in compose.yml" >&2
    exit 1
  fi
}

echo "→ run 1: apply patch"
python3 patch.py

echo "→ validate: docker compose config"
docker compose -f compose.yml config --quiet

echo "→ assert SERVICE_URL declarations present"
grep -q 'SERVICE_URL_GHOST_2368: ""' compose.yml
grep -q 'SERVICE_URL_ANALYTICS_3000: ""' compose.yml
grep -q 'SERVICE_URL_ACTIVITYPUB_8080: ""' compose.yml

echo "→ assert Ghost healthcheck injected"
grep -q '"nc", "-z", "localhost", "2368"' compose.yml

echo "→ assert mail vars exposed to Coolify UI"
# shellcheck disable=SC2016  # literal compose ${...} syntax, no shell expansion wanted
grep -qF 'mail__transport: ${mail__transport:-SMTP}' compose.yml
# shellcheck disable=SC2016
grep -qF 'mail__options__host: ${mail__options__host:-}' compose.yml
# shellcheck disable=SC2016
grep -qF 'mail__from: ${mail__from:-}' compose.yml

echo "→ assert admin_url rewritten to Coolify-friendly form"
# shellcheck disable=SC2016  # literal compose syntax, no shell expansion wanted
grep -qF 'admin__url: ${admin__url:-$SERVICE_URL_GHOST}' compose.yml
# Old :+ conditional must be gone (Coolify mis-parses the nested form)
assert_absent 'ADMIN_DOMAIN:\+'

echo "→ assert DOMAIN and DATABASE_* refs gone from compose.yml"
assert_absent '\$\{DOMAIN(:[^}]*)?\}'
assert_absent 'DATABASE_PASSWORD'
assert_absent 'DATABASE_ROOT_PASSWORD'
assert_absent 'DATABASE_USER'

echo "→ assert caddy/ deleted"
[ ! -e caddy ]

echo "→ assert README.md overwritten with Coolify content"
head -1 README.md | grep -q 'Ghost on Coolify'

echo "→ assert CLAUDE.md overwritten with Coolify content"
grep -q 'Coolify' CLAUDE.md

echo "→ run 2: idempotency"
cp compose.yml compose.r1.yml
cp .env.example env.r1
python3 patch.py
diff -u compose.r1.yml compose.yml
diff -u env.r1 .env.example

echo ""
echo "✓ all checks passed"
