# Self-hosting

Verano runs as one Docker Compose stack. Caddy is the only entry point; the backend,
frontend, Postgres and Valkey are not reachable from outside the machine.

## Local, plain HTTP

```bash
make env     # creates .env with fresh secrets; local HTTP mode (see below)
make up      # builds, starts, waits until healthy
```

Open http://localhost:8080. The first account can always be created.

## On a server with a domain (automatic HTTPS)

1. Point the domain's DNS at the server and open ports 80 and 443.
2. `make env`, then edit `.env`:

   ```bash
   VERANO_SITE_ADDRESS=verano.example.com   # Caddy obtains and renews certificates
   VERANO_HTTP_PORT=80
   VERANO_HTTPS_PORT=443
   VERANO_ENVIRONMENT=production            # refuses unsafe development settings
   VERANO_REFRESH_COOKIE_SECURE=true        # required in production
   VERANO_ALLOW_SIGNUP=false                # optional: after the first account exists, nobody else can sign up
   POSTGRES_PASSWORD=<a long random value>
   ```
3. `make up`, then create your account right away: while no account exists, whoever
   reaches the site first can create the first one.

With `VERANO_ENVIRONMENT=production` the backend refuses to start with a non-Secure
refresh cookie or with the mock provider enabled.

## Behind your own reverse proxy

If nginx, Traefik or a load balancer sits in front of Caddy, list its address in
`VERANO_TRUSTED_PROXIES` only if it replaces (not appends to) client-supplied
`X-Forwarded-For`. Never list a whole public range: a trusted address can claim to be any
client, which would bypass the sign-in rate limits.

## The command-line tool and API tokens

People and CI can use Verano without the browser through the `verano` command (see
[`cli/README.md`](../../cli/README.md)). Point it at your server:

```bash
export VERANO_URL=https://verano.example.com   # the address you open in the browser
verano login                                    # email and password, once; keeps a 90-day token
verano token create --name ci                   # a token for CI, printed once; set it as VERANO_API_TOKEN
verano token list                               # and `verano token revoke <id>`
```

Things to know as the operator:

- A personal API token acts as its owner, like a session, and is stored only as a hash. It works
  until it expires (90 days by default) or is revoked; revoking is immediate. A token cannot make
  other tokens.
- `VERANO_ALLOW_SIGNUP=false` does not affect the CLI: it signs in to an existing account.
- `verano push` sends the provider keys named in a `verano.yaml` to your Verano server, exactly as
  pasting them in the Keys step would. **Use HTTPS** on a real server so they are not sent in the
  clear. The CLI never prints or saves them.
- Sign-in attempts from the CLI are throttled like the browser's, per IP and per email.

## Teams, sign-in and the audit log

A workspace has four roles: **viewer** (reads results, cannot start a run or change anything), **member** (writes,
runs, deletes), **admin** (also provider keys, members, the spending limit and the audit log) and **owner**. One table
in `app/core/permissions.py` decides every route, and a route nobody listed is refused. Owners give any role; admins
only member and viewer; a workspace always keeps one owner.

- **Invites** carry a random link that expires (7 days by default), can be withdrawn, and works only for the invited
  email. With no mail server set (`VERANO_SMTP_HOST`, `VERANO_SMTP_PORT` and the related settings), the owner copies the
  link from the screen.
- **Sign-in with a provider** (Google, Microsoft or any OIDC provider) is configured with `VERANO_OIDC_PROVIDERS`, a JSON
  list of `{name, kind, display_name, client_id, client_secret, issuer, scopes, organization_id}`. It uses the
  authorization code flow with PKCE and needs a verified email. Provider groups can map to a role, never above admin.
- **Provider keys** are kept once per workspace and shared by its projects; rotating one updates every project that uses
  it.
- **Monthly spending limit**: an admin sets one per workspace under Guardrails. A run that reaches it stops, keeps the
  answers it has, and says why.
- **Audit log**: key, version, label and answer-label changes, invites and role changes are recorded with who did them.
  Keys appear only as their last four characters.
- **Token scopes**: `verano token create --read-only` makes a token that can look and fetch prompts but change nothing.

## Real traffic

Verano does not trace your app. It can take traces in: `verano traffic import` (or the screen) reads OpenTelemetry,
HAR, Langfuse, Phoenix and LangSmith exports and removes personal data first, and a thin OTLP receiver
(`POST /v1/traces`, also at `/api/v1/otlp/v1/traces`) accepts spans from an instrumented app using an **ingest token**
made per project. It takes OTLP over HTTP as protobuf (the default of the Python exporter) or as JSON, plain or gzipped. Sampled online scoring and drift alerts work on what has come in. Limits are the
`VERANO_TRAFFIC_*` settings in `.env.example`.

## Behind a company firewall that re-signs HTTPS

If `make up` fails with `x509: certificate signed by unknown authority`, your network replaces the certificates of sites
such as Docker Hub with its own. Your computer trusts that certificate; Docker's build helper does not. Fix it once:

1. Export the firewall's root certificate from your system keychain to `.cache/certs/corp-ca.pem` (the folder is
   git-ignored; on macOS: `security find-certificate -a -c "<its name>" -p /Library/Keychains/System.keychain`).
2. Write `.cache/certs/buildkitd.toml` pointing `ca = [...]` at that file under `[registry."docker.io"]` and
   `[registry."registry-1.docker.io"]`, then recreate the builder:
   `docker buildx rm verano && docker buildx create --name verano --driver docker-container --buildkitd-config .cache/certs/buildkitd.toml --bootstrap`.
3. Run `make up`. `make base-images` passes the same certificate to the image builds as a build secret
   (`corp_ca`), used only while installing dependencies and never stored in an image. Without the file, builds are
   unchanged.

## Secrets

- `VERANO_MASTER_KEYS` encrypts provider API keys. Keep a backup: without it, stored keys
  can't be decrypted. To rotate, prepend a new key (`new,old`) and restart: every listed
  key can decrypt and keys saved from then on use the new one. Remove the old key only
  after re-adding the provider keys saved under it (there is no bulk re-encryption yet).
- `VERANO_JWT_SECRET` signs access tokens; changing it signs everyone out of the browser. Personal API tokens do not depend on it: they stay valid until they expire or are revoked (revoke them with `verano token revoke`, or by deleting the account's tokens in the database).

## Outbound connections

A running instance calls only the providers whose keys you add. LiteLLM's price-list
download and `.env` loading are disabled, DeepEval telemetry is opted out, and Next.js
telemetry is disabled.

## Storage and cleanup

`make clean` removes Verano's leftovers only (stopped containers, test containers left
behind by an interrupted test run, dangling images, build cache above 5 GB) and never
touches data. `make clean-all` also deletes Verano's data
volumes, and asks first.

## Backups

The database volume (`verano_postgres-data`) holds everything that matters, including the hashed API tokens. Back it up
with `docker compose exec postgres pg_dump -U verano verano > verano.sql`. The files
volume (`verano_files`) holds uploaded originals and the embedding model used to remove
duplicate test cases. Valkey holds only queues, rate limits, progress and counters, and
can be lost safely.

## Offline and air-gapped installs

Image builds need no network (`make ci-offline` proves it). At run time, the embedding
model (`BAAI/bge-small-en-v1.5`, about 70 MB) is downloaded once, on the first test-case
generation, into the files volume. Without internet, set `VERANO_EMBEDDER=lexical` in
`.env`: duplicates are then detected by near-identical wording only.

## Moving to another machine

A clone carries the code only. `.env` (secrets) is git-ignored, so `make up` creates a new one; copy the old file over a secure channel if you want the same keys. Accounts, projects and runs live in Docker volumes, so move them with `pg_dump` and restore on the new machine. Git-ignored local files (`goldenset.JSON`, `Daywise_logging/`, `backend/data/`) are copied by hand. The README has the step-by-step version.
