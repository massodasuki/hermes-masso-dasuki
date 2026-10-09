# Taking a project from demo-ready to production-ready

A UAT-ready app and a production-ready app differ in a specific, checkable way: UAT asks "can a
tester use every control?", production asks "can a stranger use it, unsupervised, and can you operate
it when it breaks?" The gap is almost never the feature list — it is identity, secrets, migrations,
packaging, and operations. Run it as waves with gates, exactly like any other pipeline, and never
let a wave report "done" on a claim.

## 0. The order, and why it is an order

    INVENTORY -> SECRETS/CONFIG -> AUTH (register > login > verify > reset > session) -> DATA/MIGRATIONS
      -> PACKAGING (compose) -> OPS (health, logs, backups) -> CI/CD -> REVIEW -> HUMAN GATE

Auth comes before packaging because packaging must carry the auth secrets and the email transport;
migrations come before packaging because the container must not own its schema; packaging comes before
ops because healthchecks are a property of the composed stack, not of a bare process. Packaging first
produces a compose file that has to be rewritten once identity lands.

**Everything below is a change to the auth/security model or to infrastructure, both of which almost
always sit behind the human gate** (`AGENTS.md`: merge, deploy, migrations on non-local DBs, auth
changes need approval). Get the scope approved as ONE list up front — the waves can run in parallel
after that, but each is a policy decision, not an implementation detail.

## 1. Wave 0 — inventory before you dispatch anything

Answer these from the running system, not from the README, and write the answers into the plan:

- What identity exists today? (a dev-persona header, a stub, a real session?) Anything labelled
  "temporary", "dev identity" or "not a login" is the first thing production replaces.
- Where do secrets come from now, and is any secret committed? `git log --all -- .env` and a grep for
  high-entropy strings across history — **a secret that was ever committed is leaked and must be
  rotated, not deleted from the tip**.
- Does the schema come from migrations or from a framework sync flag? (`synchronize: true`, `db.create_all()`)
- What does the deploy target actually need — one process, or postgres + cache + queue + workers +
  reverse proxy?
- Which endpoints are unauthenticated today that must not be in production?

Each unknown becomes either a blocking question for the human or a recorded assumption. Do not guess
business intent (who may register? is email domain-restricted? is there an approval step?).

## 2. Identity: the auth epic, in the order that avoids rework

Register -> verify -> login -> session -> reset -> logout -> hardening. Each step is its own task; a
single "add auth" task produces an untestable blob.

### Registration
- Validate and normalise the email (lowercase at rest, unique index — a case-variant duplicate is a
  real bug that a unique constraint catches for free).
- **Never return whether an email already exists.** Accept the request, respond identically, and email
  the address instead ("if this address is new, we've sent a link"). Registration doubles as an
  account-existence oracle otherwise.
- Hash with a memory-hard function (argon2id preferred; bcrypt cost >= 12). Never log or serialise the
  hash — the DTO/serialiser exclusion is a *separate*, already-earned fix; re-verify it after auth lands.
- Store the verification token **hashed**, single-use, with an expiry (24h is typical) and a resend
  throttle. A plaintext token in the database is a password equivalent.

### Login and session
- One generic failure message for wrong-email and wrong-password; constant-time comparison.
- Rate-limit by IP **and** by account (a per-account counter without a per-IP one is a lockout DoS;
  per-IP without per-account is a credential-stuffing hole).
- Decide the session mechanism explicitly and write it down: httpOnly + Secure + SameSite cookie
  (preferred) or bearer token with a short TTL and a refresh path. A token in `localStorage` is an
  XSS-exfiltration risk you should be able to justify.
- Logout must invalidate server-side, not just clear the client.

### Email verification and password reset
- Both are the same primitive: a single-use, hashed, expiring token emailed as a link.
- **Enumerate the whole loop before you split it across waves.** A verification flow is four parts:
  (a) issue and store a hashed token, (b) the REDEEM endpoint that consumes it, (c) the persisted
  "verified" state it writes, and (d) the page a person lands on. Splitting "auth" and "email" into
  separate waves is exactly how (b) and (c) fall into the seam — the token is issued, the mail is sent,
  the link is built, every wave reports green, and the link leads nowhere because nothing consumes the
  token and no column records the result. Before dispatching, write the loop as an explicit interface
  (paths, bodies, error codes) that BOTH waves check themselves against.
- The email transport must be an interface with two implementations: a real SMTP/provider adapter
  configured by env vars, and a **dev transport that records the message (log or a `messages` table)**
  so the flow is verifiable end to end with no credentials. Never hardcode a provider.
- Reset must not reveal existence, must expire quickly (1h), and must invalidate sessions on success.
- Verify the whole loop by actually fetching the token from your dev transport, following the link, and
  reading back the row state — "the endpoint returned 200" is not verification of an email flow.

### Hardening (the part that is always skipped)
- Authorisation, not just authentication: every mutating endpoint re-checks ownership server-side.
  The dev-persona shortcut is exactly where this is missing.
- Security headers (HSTS, CSP), CORS locked to known origins, TLS at the proxy, cookie domain scoped.
- Secrets rotation path (key ids), and an audit trail for login/admin actions.

## 3. Secrets and configuration

- Settings in config, secrets in env, `.env.example` with **names and placeholders only**.
- **Fail fast and loud on a missing secret** — a `throw new Error('X is not set, there is no fallback')`
  at boot is a feature. (It also means a process that starts without its env looks like a crash, so put
  "source the env file" in the compose/healthcheck and in every child's brief — this bites twice.)
- No secret in logs, in error bodies, in CI output, in a health endpoint, or in an artifact. Grep the
  built artifacts for the value before you hand over.
- **Never give a secret a fallback default.** `process.env.DB_PASSWORD || 'devpass'` compiles the
  literal INTO THE BUILD: the value ships, a secret-scan gate flags it (correctly, not as a false
  positive), and a default password is a live hazard wherever the env is unset. Route it through the
  fail-fast accessor instead. Remember the copies people miss — the migration/CLI data source and the
  seed script read the same variable separately from the app.
- **Scan a CLEAN build.** A stale output directory left by an earlier build layout survives a rebuild,
  then turns up in the scan and can even be what a running process is serving. `rm -rf dist && build`
  before scanning or verifying, and treat "the secret was in an old artifact" as a packaging bug to fix
  rather than a scanning quirk to ignore.
- If a secret ever reached a commit: rotate it, and say so. Deleting the line does not un-leak it.

## 4. Data layer

- **Turn `synchronize` off in production and introduce migrations.** A container that creates its own
  schema cannot be rolled back, cannot run as a non-superuser, and races its own replicas.
- **Adopting migrations on a database that was already built by the sync flag.** The baseline cannot
  run against tables that already exist, so every existing environment needs one of two EXPLICIT
  paths, chosen and written into the runbook: mark the baseline as applied for that environment (insert
  its row into the migrations table) or rebuild the environment from migrations. An un-marked existing
  database fails at the first deploy with a table-already-exists error, and "just drop it" is not an
  acceptable default on anything but a scratch database — prove the path by building a scratch database
  from migrations alone and comparing its schema against the sync-built one.
- Migrations are reversible, reviewed, and never destructive without an explicit approval step.
  Back up before migrating, and rehearse the rollback at least once.
- Separate schema from seed. A dev seed must never run in a production path, and its teardown must
  reset children **by parent**, not by the rows it remembers creating.
- Unique constraints and FKs are the free correctness you get from doing this properly — add them in
  the migration where the feature lands, not "later".

## 5. Packaging: docker-compose

The compose file is the deliverable a stranger runs. It must be true on a clean machine.

- One service per concern (app, db, cache, queue, worker, proxy); pin image tags (a floating `latest`
  makes the build non-reproducible); multi-stage builds; run as a **non-root** user.
- `healthcheck` per service, and `depends_on: {condition: service_healthy}` — plain `depends_on` only
  orders container start, not readiness, and produces the classic "app crashed because the db was not
  up yet" race.
- Named volumes for state; no bind-mounts of host paths in the production profile; no `.env` baked into
  an image (`COPY . .` after a `.dockerignore` that excludes it).
- Postgres with an extension (PostGIS, pgvector) must be the extended image, and every service that
  talks to it needs the same extension-owning user — and any `CREATE DATABASE` must be FROM a template
  that carries the extension, or the ORM's first sync dies with a misleading type error.
- One command must bring the whole thing up: `docker compose up -d --build` then a health probe of every
  service. Verify THAT, not the individual containers.
- **Container networking honesty.** Published ports are not always reachable from the host (VPN-routed
  bridge subnets do this); a health probe that runs on the host can fail while the stack is fine, and a
  probe that runs inside the network can pass while the host is cut off. Test the path the user actually
  uses, and if published ports are unreachable, `network_mode: host` on non-conflicting ports is the
  documented fallback — say which one you chose and why.
- A reverse proxy (nginx/traefik) terminates TLS, routes per service, and owns the per-route switchover
  when an old and a new app run side by side.

## 6. Operations

- `/healthz` (liveness) and `/readyz` (readiness: db + cache + queue reachable) as distinct endpoints.
- Structured JSON logs with a request id; never the body of an auth request.
- Metrics/error tracking wired (even a minimal exporter), and an alert on the error rate, not just logs.
- **Backup and restore rehearsed once, on purpose.** An untested backup is a hypothesis.
- A runbook: how to deploy, roll back, rotate a secret, restore a dump, and where the logs are.

## 7. CI/CD

- Gates on the MERGED tree: lint, typecheck, build, unit + integration suites, and (once migrations
  exist) "migrations apply cleanly to an empty database and to a copy of production".
- Read every gate's EXIT CODE — an empty or tail-truncated output is not a pass.
- Build the production image in CI so a broken Dockerfile fails there, not at deploy time.
- No secrets printed in CI output; deploy and DB migrations on non-local databases STOP at the human gate.

## 8. The verification bar for a production claim

A production-readiness claim is only as good as the command output behind it. For each item:

- the flow exercised against the RUNNING composed stack (register with a fresh email, follow the link
  from the dev transport, log in, request a reset, log out), with the resulting row state read back;
- `docker compose up` on a clean checkout with no pre-existing volumes, then a health probe of every
  service;
- the migration path proven on an empty database AND on a copy of the current one;
- a grep of the built artifacts for each secret value, returning nothing.

Report what is NOT done at the same volume as what is. A visible gap is reviewable; a fabricated one
survives review and becomes an incident. Anything you cannot finish renders disabled with the reason.

## 9. Pitfalls that cost real time

- **Treating "it runs on my machine" as packaging.** The compose file is verified by running it from a
  clean state, not by observing the dev servers still running.
- **Assuming the tests cover auth.** Characterization suites pin the OLD behaviour; adding auth will
  legitimately change some pins. List every flipped assertion and get sign-off — do not silently
  rewrite the oracle. **Predict the flip that is MECHANICALLY REQUIRED rather than defending it at
  merge time:** the no-existence-oracle rule makes it impossible for registration to return the created
  user, so its response shape must change even though login's need not. Announce that consequence up
  front as a designed trade-off; a flip discovered during integration instead reads like a regression.
- **Leaving the dev-identity scaffold in place.** It is convenient and it is a production hole; remove
  it in the same wave that introduces real sessions, and delete its helper module rather than leaving
  it unused.
- **Building the auth epic as one task.** Registration, login, verification, reset and hardening fail
  and are reviewed at different rates; split them.
- **Forgetting the two-person rule on secrets.** The pipeline that deploys should not be able to read
  the secret values it injects where the platform supports it.
