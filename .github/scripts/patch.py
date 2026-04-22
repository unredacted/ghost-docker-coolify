#!/usr/bin/env python3
"""Coolify compatibility patch for TryGhost/ghost-docker upstream.

Runs after `git reset --hard upstream/main` in the daily sync workflow and
rewrites the upstream compose.yml to deploy cleanly on Coolify:

  - Removes the Caddy reverse proxy (Coolify's Traefik handles ingress)
  - Switches Ghost URL / MySQL credentials to Coolify SERVICE_* magic vars
  - Declares SERVICE_URL_<NAME>_<PORT> so Traefik discovers the right port
  - Adds a Ghost healthcheck for Coolify's UI indicator
  - Deletes caddy/ and strips Caddy refs from .env.example
  - Overwrites README.md with the Coolify-specific README.coolify.md

All edits are idempotent: re-running on already-patched input is a no-op.
Each substitution fails loudly when the anchor is missing, so upstream
restructuring surfaces as a nonzero exit rather than silent breakage.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys


def fail(msg: str) -> None:
    print(f"patch.py: {msg}", file=sys.stderr)
    sys.exit(1)


def swap(content: str, old: str, new: str, label: str) -> str:
    """Single-occurrence replacement with idempotency and loud failure.
    Checks `new` before `old` so that superset replacements (where `old`
    is a substring of `new`) don't double-apply."""
    if new in content:
        return content
    if old in content:
        n = content.count(old)
        if n != 1:
            fail(f"{label}: expected 1 occurrence of old anchor, found {n}")
        return content.replace(old, new, 1)
    fail(f"{label}: neither old nor new anchor present — upstream changed?")


def swap_all(content: str, old: str, new: str, label: str, expected: int) -> str:
    """Multi-occurrence replacement with idempotency and loud failure."""
    n_new = content.count(new)
    if n_new == expected and old not in content:
        return content
    if old in content:
        n = content.count(old)
        if n != expected:
            fail(f"{label}: expected {expected} occurrences of old anchor, found {n}")
        return content.replace(old, new)
    fail(f"{label}: found {n_new} of new anchor, expected {expected} — upstream changed?")


def patch_compose() -> None:
    path = pathlib.Path("compose.yml")
    if not path.exists():
        fail("compose.yml not found — run from repo root")
    c = path.read_text()

    # Caddy service block (Coolify's Traefik replaces it)
    c = re.sub(r"^  caddy:.*?(?=^  [a-z])", "", c, flags=re.MULTILINE | re.DOTALL)
    c = c.replace("  caddy_data:\n", "")
    c = c.replace("  caddy_config:\n", "")
    c = re.sub(r"^\s+- caddy\n", "", c, flags=re.MULTILINE)

    # Ghost URL → Coolify magic
    c = swap(
        c,
        "url: https://${DOMAIN:?DOMAIN environment variable is required}\n",
        "url: $SERVICE_URL_GHOST\n",
        "ghost.url",
    )

    # MySQL credentials → Coolify magic
    c = swap(
        c,
        "MYSQL_ROOT_PASSWORD: ${DATABASE_ROOT_PASSWORD:?DATABASE_ROOT_PASSWORD environment variable is required}",
        "MYSQL_ROOT_PASSWORD: $SERVICE_PASSWORD_MYSQLROOT",
        "MYSQL_ROOT_PASSWORD",
    )
    c = swap_all(
        c,
        "MYSQL_USER: ${DATABASE_USER:-ghost}",
        "MYSQL_USER: $SERVICE_USER_MYSQL",
        "MYSQL_USER",
        expected=2,
    )
    c = swap(
        c,
        "database__connection__user: ${DATABASE_USER:-ghost}",
        "database__connection__user: $SERVICE_USER_MYSQL",
        "database__connection__user",
    )
    c = swap_all(
        c,
        "MYSQL_PASSWORD: ${DATABASE_PASSWORD:?DATABASE_PASSWORD environment variable is required}",
        "MYSQL_PASSWORD: $SERVICE_PASSWORD_MYSQL",
        "MYSQL_PASSWORD",
        expected=2,
    )
    c = swap(
        c,
        "database__connection__password: ${DATABASE_PASSWORD:?DATABASE_PASSWORD environment variable is required}",
        "database__connection__password: $SERVICE_PASSWORD_MYSQL",
        "database__connection__password",
    )
    c = swap(
        c,
        "MYSQL_DB: mysql://${DATABASE_USER:-ghost}:${DATABASE_PASSWORD:?DATABASE_PASSWORD environment variable is required}@tcp(db:3306)/activitypub",
        "MYSQL_DB: mysql://$SERVICE_USER_MYSQL:$SERVICE_PASSWORD_MYSQL@tcp(db:3306)/activitypub",
        "activitypub-migrate.MYSQL_DB",
    )

    # Tinybird tracker endpoint → analytics FQDN (optional profile)
    c = swap(
        c,
        "tinybird__tracker__endpoint: https://${DOMAIN:?DOMAIN environment variable is required}/.ghost/analytics/api/v1/page_hit",
        "tinybird__tracker__endpoint: $SERVICE_URL_ANALYTICS/api/v1/page_hit",
        "tinybird__tracker__endpoint",
    )

    # ActivityPub image storage URL → Ghost origin (images must stay on primary domain)
    c = swap(
        c,
        "LOCAL_STORAGE_HOSTING_URL: https://${DOMAIN}/content/images/activitypub",
        "LOCAL_STORAGE_HOSTING_URL: $SERVICE_URL_GHOST/content/images/activitypub",
        "activitypub.LOCAL_STORAGE_HOSTING_URL",
    )

    # Ghost healthcheck (inserted between env_file and environment)
    ghost_env_anchor = (
        "    # This is required to import current config when migrating\n"
        "    env_file:\n"
        "      - .env\n"
        "    environment:\n"
    )
    ghost_with_hc = (
        "    # This is required to import current config when migrating\n"
        "    env_file:\n"
        "      - .env\n"
        "    healthcheck:\n"
        '      test: ["CMD", "wget", "-qO-", "http://localhost:2368/ghost/api/admin/site/"]\n'
        "      interval: 30s\n"
        "      timeout: 5s\n"
        "      retries: 5\n"
        "      start_period: 60s\n"
        "    environment:\n"
    )
    c = swap(c, ghost_env_anchor, ghost_with_hc, "ghost.healthcheck")

    # SERVICE_URL_<NAME>_<PORT> declarations — Coolify uses these to wire Traefik
    c = swap(
        c,
        "      url: $SERVICE_URL_GHOST\n",
        '      url: $SERVICE_URL_GHOST\n      SERVICE_URL_GHOST_2368: ""\n',
        "ghost.SERVICE_URL_GHOST_2368",
    )
    c = swap(
        c,
        "    environment:\n      NODE_ENV: production\n      PROXY_TARGET:",
        '    environment:\n      NODE_ENV: production\n      SERVICE_URL_ANALYTICS_3000: ""\n      PROXY_TARGET:',
        "traffic-analytics.SERVICE_URL_ANALYTICS_3000",
    )
    c = swap(
        c,
        "      NODE_ENV: production\n      MYSQL_HOST: db\n",
        '      NODE_ENV: production\n      SERVICE_URL_ACTIVITYPUB_8080: ""\n      MYSQL_HOST: db\n',
        "activitypub.SERVICE_URL_ACTIVITYPUB_8080",
    )

    # Expose SMTP vars as explicit ${...} refs so Coolify's env scanner
    # surfaces them in the UI (upstream passes mail via env_file, which
    # Coolify doesn't scan).
    c = swap(
        c,
        "      tinybird__stats__endpoint: ${TINYBIRD_API_URL:-https://api.tinybird.co}\n"
        "    volumes:\n",
        "      tinybird__stats__endpoint: ${TINYBIRD_API_URL:-https://api.tinybird.co}\n"
        "      mail__transport: ${mail__transport:-SMTP}\n"
        "      mail__options__host: ${mail__options__host:-}\n"
        "      mail__options__port: ${mail__options__port:-465}\n"
        "      mail__options__secure: ${mail__options__secure:-true}\n"
        "      mail__options__auth__user: ${mail__options__auth__user:-}\n"
        "      mail__options__auth__pass: ${mail__options__auth__pass:-}\n"
        "      mail__from: ${mail__from:-}\n"
        "    volumes:\n",
        "ghost.mail vars",
    )

    path.write_text(c)


def patch_env_example() -> None:
    path = pathlib.Path(".env.example")
    if not path.exists():
        return
    e = path.read_text()

    # DOMAIN is supplied by Coolify's SERVICE_URL_GHOST — no need to set here
    e = re.sub(
        r"# Ghost domain\n# Custom public domain Ghost will run on\nDOMAIN=example\.com\n\n",
        "",
        e,
    )
    # Drop the Caddyfile reference in the ADMIN_DOMAIN comment
    e = e.replace(
        "# If you have Ghost Admin setup on a separate domain uncomment the line below and add the domain\n"
        "# You also need to uncomment the corresponding block in your Caddyfile\n",
        "# If Ghost Admin lives on its own domain, add it as a second FQDN on the\n"
        "# `ghost` service in the Coolify UI, or uncomment the line below for local runs.\n",
    )
    # Coolify owns ingress ports
    e = re.sub(
        r"# Ghost ports\n# Ports where Ghost will listen for HTTP traffic\.\n"
        r"# Change these if the default ports are in use, or if Ghost is behind a reverse proxy\.\n"
        r"HTTP_PORT=80\nHTTPS_PORT=443\n\n",
        "",
        e,
    )
    # Coolify auto-generates DB credentials via SERVICE_USER_MYSQL / SERVICE_PASSWORD_MYSQL
    e = re.sub(
        r"# Database settings\n# All database settings must not be changed once the database is initialised\n"
        r"DATABASE_ROOT_PASSWORD=reallysecurerootpassword\n"
        r"# DATABASE_USER=optionalusername\n"
        r"DATABASE_PASSWORD=ghostpassword\n\n",
        "",
        e,
    )

    path.write_text(e)


def overwrite_readme() -> None:
    src = pathlib.Path(".github/README.coolify.md")
    if not src.exists():
        fail(f"{src} missing — the sync workflow should back it up under .github/")
    pathlib.Path("README.md").write_text(src.read_text())


def main() -> None:
    patch_compose()
    shutil.rmtree("caddy", ignore_errors=True)
    patch_env_example()
    overwrite_readme()
    print("Patched compose.yml successfully")


if __name__ == "__main__":
    main()
