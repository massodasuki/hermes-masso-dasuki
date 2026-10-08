# Parallel task isolation

How to run several children at once over one repo without them destroying each other, and how to
tell a real dependency apart from a self-inflicted bottleneck.

## The collision taxonomy

Only **dependencies** force serial execution. Everything else here is a collision you can engineer
away, and conflating the two is what turns a five-agent team into a single-threaded developer.

| # | Collision | Symptom if ignored | Fix |
|---|---|---|---|
| C1 | One shared git index / working tree | concurrent `git commit` corrupts the index; children clobber each other's edits | worktree per task |
| C2 | One shared port space | children bind the same port; unrelated dev stacks already hold 5432/6379/3000 | port block per task |
| C3 | One shared database or schema | one child's `synchronize` or fixture load wipes another's data | database per task |
| C4 | One writer per file | two children editing one file conflict every time | path partitioning in the brief |
| C5 | One network pipe / package cache | concurrent big installs and image pulls starve each other and look like hangs | stagger heavy fetches |

Rule of thumb: in practice roughly 20% of tasks are genuinely dependent and 80% of the perceived
serialisation is collision avoidance.

## What genuinely serialises (accept it, do not fight it)

- **Contract before consumer** — a client cannot be written against an API contract that does not exist.
- **Oracle before port** — a migrated screen cannot be parity-checked before the original's behaviour is captured.
- **Baseline before change** — a behaviour change cannot be proven against a baseline captured after it.
- **Design decision before implementation** — a mid-flight design change goes back to the architect.
- **Merge order** — two branches touching one file merge in a defined order, one at a time.

## Layer 1 — worktree per task (kills C1)

Give each task `git worktree add` on its own branch. Each worktree has its own index, so:

- children **may and should commit** their own work — the orchestrator is no longer the single writer;
- the main checkout stays clean and never becomes the conflict battlefield;
- tearing a task down cannot touch anyone else's work.

Brief every child with: *work in `<worktree path>` (branch `<branch>`), do not touch the main
checkout, do not push, do not merge, do not rebase, never touch `main`.* The orchestrator merges.

If the repo ships an allocator (the AI Software House kit ships `.agent/scripts/task-env.sh`), use
it; otherwise the equivalent is a few lines: `git worktree add -b ai/<task>-<slug> <dir> <base>`.
A fresh worktree has no `node_modules` — it is gitignored, so `git worktree add` does not bring it —
and letting each child install its own is the C5 bottleneck made concrete: measured on a slow link,
~30 min per install, with N concurrent installs starving each other. **Hardlink the existing install
into the worktree instead:**

```bash
cp -al <main>/apps/api/node_modules <worktree>/apps/api/node_modules
```

Metadata-only and effectively instant — four worktrees, ~566 package dirs each, zero network — and
the children then build and test normally. Two conditions: the task must not change dependencies (if
it edits `package.json` it needs a real install), and every brief must say **do not run `npm install`
/ `npm ci`** in the worktree, because the files are shared with the main checkout.

## Layer 2 — port block per task (kills C2)

Allocate a block of ~10 host ports per task and **persist the allocation to disk**, not to your
memory: a fresh session must read the same map. Commit the allocation map on the integration
branch. Choose a base well clear of dev defaults (3000/3001/5173/5432/6379/5672) — 31000 upward is
safe — and tell each child its exact ports in the brief.

## Layer 3 — database per task (kills C3)

One database server hosts many databases. Create `task_<slug>` per task and hand the child the name.

- **Never auto-create a database in whatever database container happens to be running.** On a
  shared host that container belongs to someone else's project, and creating databases inside it is
  a silent side effect on infrastructure this task was never given. Auto-detect only a container
  whose image is unambiguously this project's (e.g. a `postgis` image for a PostGIS project);
  otherwise require the caller to name the container explicitly, and report the DB as *skipped*
  rather than pretending.
- **Connect to the maintenance database over an explicit host and port.** A `docker exec … psql`
  with no `-h`/`-p` talks to the container's own unix socket on the default port, so against a server
  listening anywhere else (a host-networked PostGIS on 55432 is the common case) the existence check
  "succeeds" while `CREATE DATABASE` silently does nothing — the allocator reports FAILED and the
  brief goes out pointing at a database that does not exist. Pass host, port, user and maintenance DB
  explicitly, and make the port overridable instead of assuming 5432.
- **Verify provisioning by asking the server** (`SELECT datname FROM pg_database WHERE datname='…'`),
  never by reading the allocator's own summary table. A table that carries a worktree-exists flag
  beside the DB column will be misread as DB status at least once; label the columns unambiguously and
  check the server regardless.
- **Create the per-task database FROM a template that carries the project's extensions.** A plain
  `CREATE DATABASE` clones `template1`, which in the official PostGIS image holds only `plpgsql` — so
  the "fresh" database has **no `geography` type at all** and the child's `synchronize` dies on the
  geography column at boot. `template_postgis` is where that image keeps `postgis, postgis_topology,
  fuzzystrmatch, postgis_tiger_geocoder`: create with `CREATE DATABASE <name> TEMPLATE template_postgis`,
  and make the template an allocator option rather than a hardcoded assumption (other stacks have
  their own). Verify the extension actually landed in the task DB before you brief — a child that hits
  this at boot may "fix" it by editing the entity, and a schema edit is far more expensive to unwind
  than the `CREATE EXTENSION` it should have been.
- Report DB creation honestly: `created` / `exists` / `skipped` / `FAILED`. A child that reports a
  database it did not create poisons every result after it.

## Per-surface baselines, not one monolithic sweep

A single characterization pass that gates N dependent tasks is the most expensive serialisation
available: N-1 children sit idle while one long sweep runs.

Capture the baseline **per module / route / surface**, and unblock a task the moment **its own**
section exists. Make the artefacts addressable — one file per surface — so each task can cite the
exact section it is measured against. Then a three-surface baseline runs three-wide instead of one
long queue.

## Cost rules

Agent count is the **cost unit**; wall-clock is the **benefit unit**.

- **Batch mechanical work into ONE child.** Several small, unrelated, low-risk edits (a config
  deletion, a compose edit, a rename) belong in one brief. A two-line change does not deserve its own run.
- **Spread reasoning, not typing.** Use separate children where the thinking is genuinely independent.
- **Tier the models** — mechanical work on the cheap model, design/security/architecture on the strong one.
- **Do not parallelise to look busy.** Two children that each re-read the same files cost twice and
  finish at the same time as one.
- **Stagger heavy downloads** (C5). Sequence a large `npm install` and a large image pull, or wait;
  a starved pull is indistinguishable from a hang and burns more wall-clock than queueing it would have.

## Orchestrator checklist per task

1. Allocate isolation (worktree + branch + ports + DB) and record it on disk.
2. Brief with: task id, acceptance criteria, **exact owned paths**, the worktree path, the port
   block, the DB name, and the previous handoff JSON. Nothing else.
3. On return, verify the claims yourself — a self-report is not evidence.
4. Merge the task branch into the integration branch in dependency order; resolve conflicts yourself.
5. Re-check the definition-of-done gates, then tear the worktree down.

## Teardown

Removing the worktree and freeing the allocation should **not** delete the task branch: the branch
is the work, and it still has to be merged or discarded deliberately. Do the DB drop as an explicit
opt-in flag, and note that any argument not persisted in the allocation (e.g. the DB container name)
must be passed again at teardown time.

## Safety rule for the orchestrator

While children have work in flight in the main checkout, commit **explicit paths only** — a sweeping
`git add -A && git commit` swallows their in-progress files into your checkpoint commit and makes the
history lie about what was done when.
