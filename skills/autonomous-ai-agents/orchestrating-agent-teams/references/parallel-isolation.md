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
debug port cannot drift into a neighbour. Write the allocation map to a committed JSON
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
