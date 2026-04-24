# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ghost 6 CMS packaged for one-shot deploys on [Coolify](https://coolify.io).
Forked from `TryGhost/ghost-docker` and synced nightly; Coolify-specific
edits live in [`.github/scripts/patch.py`](.github/scripts/patch.py) and are
re-applied on top of each upstream pull.

Coolify's built-in Traefik handles HTTPS and routing, so the Caddy service
from upstream is stripped by the patch. Ghost URL and MySQL credentials use
Coolify's `SERVICE_URL_*` / `SERVICE_USER_*` / `SERVICE_PASSWORD_*` magic
variables, which Coolify auto-generates and wires through the UI.

## Architecture

Services in `compose.yml` after patching:

1. **ghost** — Ghost CMS, port 2368 internal. Proxy wiring via
   `SERVICE_URL_GHOST_2368` declaration; referenced as `$SERVICE_URL_GHOST`.
2. **db** — MySQL 8.0 (pinned, Renovate restricted to `~8.0`). Credentials
   from `SERVICE_USER_MYSQL`, `SERVICE_PASSWORD_MYSQL`, `SERVICE_PASSWORD_MYSQLROOT`.
3. **traffic-analytics** (profile `analytics`) — Tinybird proxy on port 3000.
   Proxy via `SERVICE_URL_ANALYTICS_3000`.
4. **activitypub** (profile `activitypub`) — Federation service on port 8080.
   Proxy via `SERVICE_URL_ACTIVITYPUB_8080`.
5. Supporting one-shot services: `tinybird-login`, `tinybird-sync`,
   `tinybird-deploy`, `activitypub-migrate`.

Internal DNS on the `ghost_network` bridge: `ghost` → `db:3306`,
`activitypub` → `db:3306`. External ingress is Coolify's responsibility; this
repo does not ship a reverse proxy.

## Common Commands

```bash
# Core (Coolify runs these under the hood; equivalents for local debugging)
docker compose up -d
docker compose down
docker compose logs -f ghost
docker compose ps
docker compose pull
docker compose restart ghost

# Optional profiles
docker compose --profile=analytics up -d
docker compose --profile=activitypub up -d
COMPOSE_PROFILES=analytics,activitypub docker compose up -d

# Tinybird setup (analytics profile only)
docker compose run --rm tinybird-login
docker compose --profile=analytics up tinybird-sync
docker compose --profile=analytics up tinybird-deploy

# Debugging
docker compose exec ghost sh
docker compose exec db mysql -u root -p
```

## Configuration

Deployments on Coolify: set FQDNs and SMTP env vars in the Coolify UI;
MySQL passwords auto-generate. See [`README.md`](README.md) for the flow.

Local development without Coolify: set the SERVICE_* vars in `.env`:

```
SERVICE_URL_GHOST=http://localhost:2368
SERVICE_USER_MYSQL=ghost
SERVICE_PASSWORD_MYSQL=localdev
SERVICE_PASSWORD_MYSQLROOT=localrootdev
SERVICE_URL_ANALYTICS=http://localhost:3000
```

Ghost config uses the flattened env-var pattern, e.g. `mail__options__host`,
`mail__transport=SMTP`. See [Ghost's config docs](https://ghost.org/docs/config/).

### Key files
- [`compose.yml`](compose.yml) — regenerated nightly from upstream + `patch.py`. Don't edit by hand.
- [`.github/scripts/patch.py`](.github/scripts/patch.py) — all Coolify edits live here.
- [`.github/workflows/sync.yml`](.github/workflows/sync.yml) — nightly upstream sync.
- [`.env.example`](.env.example) — environment template.
- [`README.coolify.md`](README.coolify.md) — deploy docs; `patch.py` copies this to `README.md`.
- [`mysql-init/create-multiple-databases.sh`](mysql-init/create-multiple-databases.sh) — creates the `activitypub` database.

## Migration from Ghost CLI

The scripts in [`scripts/`](scripts/) are bare-metal migration tools, not
intended to run inside Coolify:

- [`scripts/migrate.sh`](scripts/migrate.sh) — backs up a Ghost CLI install,
  dumps the database with `--no-tablespaces`, converts `config.production.json`
  to `.env`, and starts the Docker stack.
- [`scripts/config-to-env.js`](scripts/config-to-env.js) — flattens Ghost's
  nested JSON config into the `section__subsection__key` env-var pattern.

For Coolify migration from an existing Ghost CLI install, run `migrate.sh`
on the source host to produce an `.env`, then transfer the `.env` + database
dump + content directory to the Coolify host and deploy normally.

## Daily sync workflow

[`sync.yml`](.github/workflows/sync.yml) runs at 00:00 UTC:

1. Clone this fork, back up `.github/` to `/tmp`.
2. `git reset --hard upstream/main` (TryGhost/ghost-docker).
3. Restore `.github/` over the reset.
4. Run `python3 .github/scripts/patch.py` — re-applies Coolify edits.
5. `docker compose config --quiet` — validates the patched YAML.
6. `git push --force-with-lease`.

Any hand-edits to `compose.yml`, `caddy/`, `.env.example`, or `README.md`
will be overwritten nightly. Put durable changes in `patch.py`.

## Important Notes

- Ghost pins to `${GHOST_VERSION:-6-alpine}`; Renovate intentionally does
  not pin this image. Bump `GHOST_VERSION` in Coolify's env UI when needed.
- MySQL is pinned to `~8.0` (Renovate rule in [`.github/renovate.json5`](.github/renovate.json5)). Required for Ghost 6.
- Transactional email (`mail__*`) is required for admin invites and
  password resets — not just newsletters.
- The patched `compose.yml` depends on Coolify's magic var injection.
  Running `docker compose up` outside Coolify needs the SERVICE_* vars
  in `.env` (see Configuration above).
