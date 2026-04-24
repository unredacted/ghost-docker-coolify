# Ghost on Coolify

Ghost 6 CMS packaged for one-shot deploys on [Coolify](https://coolify.io), with
optional Tinybird analytics and ActivityPub federation. Forked from
[`TryGhost/ghost-docker`](https://github.com/TryGhost/ghost-docker) and synced
daily; the Coolify-specific patch lives in
[`.github/scripts/patch.py`](.github/scripts/patch.py).

## Deploy

1. In Coolify: **New Resource → Public Repository**, point at this repo,
   build pack **Docker Compose**, compose file `compose.yml`.
2. On the `ghost` service, set the primary **Domain (FQDN)** to the URL
   you want (e.g. `https://blog.example.com`). Coolify fills in
   `SERVICE_URL_GHOST` automatically and wires Traefik to port 2368.
3. Fill in the SMTP rows in the **Environment Variables** tab — the
   keys (`mail__options__host`, `mail__options__port`,
   `mail__options__auth__user`, `mail__options__auth__pass`, `mail__from`)
   are pre-listed. Transactional email is required for staff invites and
   password resets; Ghost will still boot without it, only those flows fail.
4. **Deploy**. MySQL credentials generate on first boot via
   `SERVICE_USER_MYSQL` / `SERVICE_PASSWORD_MYSQL` / `SERVICE_PASSWORD_MYSQLROOT` —
   you don't enter them manually.

## Optional: separate admin domain

Set `ADMIN_DOMAIN=admin.example.com` on the resource and add the same value
as a second FQDN on the `ghost` service in Coolify. Upstream's
`${ADMIN_DOMAIN:+https://${ADMIN_DOMAIN}}` expression means Ghost sees
`admin__url` only when the variable is non-empty.

## Optional: analytics (Tinybird)

Enable the `analytics` profile on the resource
(`COMPOSE_PROFILES=analytics`). Set a second FQDN on the `traffic-analytics`
service (e.g. `analytics.example.com`) — Coolify fills
`SERVICE_URL_ANALYTICS` and proxies port 3000. Populate
`TINYBIRD_*` env vars per [`TINYBIRD.md`](TINYBIRD.md).

## Optional: ActivityPub

Enable the `activitypub` profile (`COMPOSE_PROFILES=analytics,activitypub`
if combined). Set a third FQDN on the `activitypub` service.

Fediverse discovery via `@user@your-primary-domain` additionally requires
routing `/.well-known/webfinger` on the Ghost FQDN to the ActivityPub
service. In Coolify, add this custom label to the `ghost` service:

```
traefik.http.routers.ghost-webfinger.rule=Host(`blog.example.com`) && PathPrefix(`/.well-known/webfinger`)
traefik.http.routers.ghost-webfinger.service=activitypub-http
traefik.http.services.activitypub-http.loadbalancer.server.port=8080
```

## Upgrades

Ghost's version floats on `${GHOST_VERSION:-6-alpine}`. Pin explicitly by
setting `GHOST_VERSION=6.2-alpine` on the resource if you need a specific
release. Renovate tracks MySQL patch updates within 8.0.x and the
analytics/ActivityPub image digests; Ghost itself is not pinned.

## Running locally (without Coolify)

Because the patched `compose.yml` targets Coolify's magic vars, local
`docker compose up` needs those vars set in `.env`:

```
SERVICE_URL_GHOST=http://localhost:2368
SERVICE_USER_MYSQL=ghost
SERVICE_PASSWORD_MYSQL=localdev
SERVICE_PASSWORD_MYSQLROOT=localrootdev
SERVICE_URL_ANALYTICS=http://localhost:3000
```

For a bare-metal Ghost CLI → Docker migration, see
[`scripts/migrate.sh`](scripts/migrate.sh) (not intended for Coolify hosts).

## License

MIT — see [LICENSE](LICENSE).
