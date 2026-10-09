# Parallel task isolation

Run N independent tasks at once over one repo without them colliding. One script owns
allocate / list / remove; the orchestrator runs it, and the children never do.

## Allocate, before dispatch

```sh
# 1. its own worktree on its own branch, cut from the integration branch
git worktree add .worktrees/<TASK-ID> -b ai/<TASK-ID>-<slug> <integration-branch>

# 2. its own database, FROM A TEMPLATE THAT CARRIES THE STACK'S EXTENSIONS
#    a plain CREATE DATABASE inherits only the default template
psql -h <host> -p <port> -U <user> -d <maint-db> -c \
  'CREATE DATABASE task_<id> TEMPLATE template_postgis'

# 3. hardlink the dependencies instead of reinstalling (they are gitignored, so the
#    worktree has none and a fresh install can cost tens of minutes)
cp -al apps/api/node_modules .worktrees/<TASK-ID>/apps/api/node_modules
cp -al apps/web/node_modules .worktrees/<TASK-ID>/apps/web/node_modules

# 4. its own env: copy the gitignored file, then override db name + port per task
cp apps/api/.env .worktrees/<TASK-ID>/apps/api/.env
```

Give each task an offset of ~10 ports from a base (31000, 31010, 31020, ...) so API, web, and any
debug port cannot drift into a neighbour. Put the task's WEB port in its brief as well as its API
port, and say explicitly not to use the shared default: a dev server binds its framework default
(3002 for `next dev`, 5173 for Vite) unless the brief passes the port flag, and the port you left a
demo server on for the human is taken too — so N children and your own demo all collide on one port.

## Repairing the shared contract after the worktrees exist

Discovering that a shared module lacks a capability does not mean re-cutting every worktree. Add it
yourself (you are the single writer for shared files), commit it on the integration branch, then
bring each already-created worktree onto that commit — a fast-forward, because children have not
committed yet:

```sh
for t in <TASK-IDS>; do git -C ".worktrees/$t" merge --ff-only <integration-branch>; done
# then confirm the capability really arrived in each tree
grep -c 'export function <newFn>' .worktrees/<TASK-ID>/<shared-module>.ts
```

If a child has already committed on its branch, a plain merge replaces `--ff-only`; expect a real
merge commit and resolve it as the single committer. Write the allocation map to a committed JSON
(`.agent/tasks/allocations.json`) so a fresh session, or another orchestrator, can see which task
owns which worktree, branch, port block and database.

Caveat on hardlinking: the worktrees now share inodes with the main checkout, so an install or a
native rebuild in ONE worktree mutates every other. That is a second reason the briefs must forbid
install commands.

## Verify the allocation before you dispatch into it

Boot the app in the worktree against its own database and hit a health endpoint. An allocator bug
looks exactly like a broken task: a DB step that connects to the wrong host or maintenance database
can still print something that reads like success. Prove the task's DB carries the required
extension (`SELECT postgis_version()`, or the equivalent) and that the app answers on its own port.

**Read every line of the allocation report, not the first.** N near-identical per-task blocks hide
the one task whose DB step failed, so a wave dispatched on a skimmed report contains a child that
dies at boot for a reason unrelated to its task. A helper whose flags do not match the container
(its default role vs the role that owns the database — `--pg-user <stack-user>`) prints its own
FAILED status and carries on: fix the disposition before dispatch, and when the helper cannot be
reused, create that database by hand from the same template and assert the extension.

**When an allocated block collides with a service you started by hand** (a demo server for the
human — the allocator cannot see it, so it hands the port out), do not move your demo mid-wave. Give
the affected child one explicit free port inside its OWN block, name the port it must not bind, and
carry that override into every command in its brief. A wave that half-starts on a bind error burns a
whole child.

## Before dispatch, re-check per-worktree env

Copying the gitignored `.env` in is not enough — the copy still carries the MAIN checkout's database
name and port, because those are in the file, not in the worktree. Rewrite the task keys (DB name,
DB port, server port) in every worktree's copy and echo them back per task; a worktree left pointing
at the shared database looks like a working allocation and quietly writes to the wrong place.

## Teardown, after the merge

- Remove the worktree but KEEP the branch: the branch is the work, and you still have to merge or
  discard it.
- Dropping the scratch databases is destructive — get consent, and treat a blocked approval as stop.
- Kill the task's servers by the PID that owns the listening port (`ss -ltnp | grep ':<port> '`).
  A `pkill -f <pattern>` can match its own command line and kill your session shell instead.

## When NOT to parallelise

Serialise only for a genuine dependency: a contract must exist before its consumer, an oracle or
fixture before the change it judges, a baseline before the delta, a design decision before its
implementation. Everything else — and especially mechanical, same-shaped work — batches into ONE
agent, because the agent count is the cost unit and a trivial task does not deserve its own run.
