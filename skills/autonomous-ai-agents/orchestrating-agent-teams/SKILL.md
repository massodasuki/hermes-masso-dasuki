---
name: orchestrating-agent-teams
description: "Use when orchestrating subagent teams over a repo."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [orchestration, subagents, delegation, verification, pipeline]
    category: autonomous-ai-agents
    related_skills: [claude-code, codex, opencode, sdlc-review, git-safe-publish]
---

# Orchestrating agent teams

You are the orchestrator (tech lead / delivery manager) of specialist role agents — architect,
developer, QA, reverse-engineer — running a gated pipeline (discovery -> design -> implement ->
QA -> fix loop -> review -> PR -> human approval). You decompose work, dispatch, VERIFY, and
report. You do not write production code and you do not review your own dispatch.

## 0. The repo's own kit is the source of truth

When the repo ships `AGENTS.md`, `.claude/agents/*.md` and `.agent/STATE.md`, read them FIRST.
They define the phases, gates, handoff JSON shape, and hard rules. This skill only adds what
those files do not cover: how to actually run such a kit from Hermes, and how to keep the
pipeline honest. Obey the repo's rules over your defaults; when you must deviate, record the
deviation in `.agent/STATE.md` and surface it to the human instead of silently absorbing it.

## 1. Recon before you dispatch (one batched call)

Read the state file, the agent definition files, the README. Then list the target tree and size
it. Establish: source roots, LOC/file counts, what must NEVER be read (`node_modules/`, compiled
`dist/`), and whether the target is a git repo of its own. Do this before writing any brief — a
brief has to cite real paths and real file counts.

## 2. Dispatch

- **Claude-Code-style kits run fine under Hermes.** If the repo's AGENTS.md says "call the
  subagents by name", that assumes the `claude` CLI exists. The Hermes-native equivalent is
  `delegate_task` with the contents of `.claude/agents/<name>.md` as the brief — same role
  separation, same handoff contract, no CLI dependency. When the CLI *is* available, prefer it
  (see the `claude-code` / `codex` / `opencode` skills).
- **One `delegate_task` call, many tasks.** Independent passes batched in one call run in
  parallel. Give each child a DISJOINT write target — two children writing the same doc clobber
  each other. Say which docs each child owns and which another child owns. One writer per FILE, and
  the orchestrator is the only process that runs writing git commands (section 2b).
- **A subagent gets a brief, not history.** Pass task id, acceptance criteria, artifact paths,
  and the previous handoff JSON. Nothing else.
- **List what earlier passes already established, with "do not re-derive this — build on it".** A
  child that re-derives a census from scratch returns its own numbers, and you inherit the
  reconciliation job across every pass. Repeating the confirmed facts keeps the passes consistent.
- **Dependent passes go in a LATER round.** A pass that has to read other passes' outputs — a
  backlog, a consolidated questions file, a final report — cannot run alongside them. Dispatch
  the independent passes first, then dispatch the synthesis pass once that batch has landed.
- **Background results arrive between turns.** A batched dispatch returns immediately; children
  report back as their own message. Do the work that does not depend on them, then end the turn
  with a one-line status. Do not poll transcripts or artifact files to wait.
- **Repeat the non-obvious rules in every child's `context`** — children inherit nothing:
  read-only path list; evidence format `path/File.ext:LINE`; "mark anything unverified
  UNVERIFIED"; "separate observed behaviour from your interpretation"; "do not read node_modules/
  or dist/"; "never copy secret values into artifacts, env var NAMES only"; and the exact output
  paths to write. **Quote every path absolutely, or explicitly relative to the child's own cwd.** A
  child runs from its worktree and often from an app subdirectory inside it, so a repo-relative path
  that resolves in your shell (`./docs/...`) resolves somewhere else for the child or fails outright.
  Anything a child is told to `-r`, `--config`, or execute needs its absolute path.
- **Give each child an `output_schema` matching the pipeline's handoff JSON**, and require the
  handoff JSON be written to `.agent/handoffs/<task-id>-<agent>.json` as well as returned, so
  routing the result back into the pipeline is mechanical.

## 2b. Parallel execution: isolate every task before you dispatch it

Parallel is the default whenever the tasks are genuinely independent; a serial pipeline is the
exception and needs a stated reason. N agents in one working tree is the failure mode — they fight
over the git index, the dependency tree, the ports, the database, and each other's files. Isolate
each task:

1. **Its own git worktree + branch**, cut from the integration branch before dispatch:
   `git worktree add .worktrees/<TASK-ID> -b ai/<TASK-ID>-<slug> <integration-branch>`. A worktree
   has its own index, so children can commit without corrupting the main checkout — but two
   concurrent commits in ONE tree corrupt that index, so **the orchestrator is the only committer**:
   every brief says do not push, merge, rebase, or touch `main`, and you merge the branches in
   dependency order afterwards.
2. **Its own port block and its own database.** Tasks sharing a database delete each other's rows and
   produce failures neither can explain. Allocate EVERY port a task binds, not just the API port: a
   framework dev server falls back to its own fixed default (`next dev` 3002, Vite 5173) unless the
   brief passes the port flag explicitly, so four children silently fight over one port — and over
   whichever port the demo server you left running for the human already holds. The allocator cannot
   know about a server YOU started by hand, so note your demo's ports before allocating and, when an
   allocation output hands a child one of them, override that port inside THAT child's brief (and tell
   the child why) rather than moving the demo the human is looking at.
3. **Its own `.env`.** A worktree materialises only tracked files, so a gitignored `.env` is absent
   and anything that fails fast on a missing secret aborts at boot. Copy it in and override the
   task's DB name and port.
4. **Hardlinked dependencies, never a fresh install.** `cp -al` the main checkout's `node_modules`
   into the worktree's app dir — seconds instead of tens of minutes. Then put "dependencies are
   already installed, do NOT run install commands" in every brief.
5. **Write targets partitioned per file.** Give each task an ownership list AND a "do not touch"
   list. A shared helper module is a collision waiting to happen: if several tasks need the same new
   capability, make adding it its own task in an earlier round rather than letting them all edit it.
   If you only discover the gap after the worktrees exist, do not serialise a new task and do not let
   the children share the edit: add the capability yourself as the single writer, commit it on the
   integration branch, then fast-forward every worktree onto that commit before dispatch
   (`references/parallel-isolation.md`).

**Fixtures, oracles and contracts land in an earlier round than their consumers.** A seed script, a
captured baseline, or a shared typed contract must be merged before the tasks that are verified
against it are dispatched, so every consumer measures against identical data.

**When a producer and its consumer MUST run in the same round, freeze the interface as TEXT in both
briefs** — exact paths, request and response fields, error codes — and tell the consumer to build
against that document and to REPORT a missing endpoint rather than patch one. This is how a frontend
and its backend can run in parallel: the backend implements the frozen paths while the frontend builds
against them. An unfrozen seam is the failure mode worth naming, because both halves report themselves
complete and meet nowhere — the page posts to a path that was never created, and each wave's own gates
are green.

**Split a parallel backend wave by FEATURE MODULE, and keep the app-root registry off-limits to all of
it.** Several agents can add tables and endpoints in parallel without colliding if each registers its
new entity inside its OWN existing feature module (`TypeOrmModule.forFeature([...])`) and every brief
forbids the root module file — that registry is the one file every backend agent would otherwise have
to touch. Do the same for a shared fixture loader: name exactly ONE agent as its owner for the round
and forbid the rest, since the loader is the second file every backend agent wants to edit.

**When a LATER wave genuinely needs the root registry** (a new module that must be registered there),
assign that one file to exactly ONE named wave and tell the others to work without it — a
per-controller decorator (a guard, an interceptor) carries what a global registration would, and the
wave that does not own the file must not open it. Stating "do not touch the registry" without naming
the wave that DOES own it just moves the collision to whoever needs it first.

**A completeness pass ("make every control work") is a wave plan, not a polish task.** Inventory the
controls before dispatching, classify each one by whether the endpoint behind it exists, and order the
waves by that dependency — a control whose endpoint is missing cannot be finished by a UI agent.
Recipe and disposition matrix: `references/completeness-pass.md`.

**“Make it production ready” is a second, different wave plan.** Registration, login, email
verification, secret handling, migrations, docker-compose packaging, healthchecks and CI/CD are an
identity-and-operations epic, not a feature list: auth lands before packaging, migrations before
packaging, packaging before ops monitoring. The order, the per-workstream checklists and the evidence
bar for a production claim are in `references/production-readiness.md`. Nearly every wave in it changes
the auth or infrastructure model, so get the whole scope approved as ONE list before dispatching, then
run the waves in parallel.

**Write the shared convention down before you fan out.** When several agents implement the same kind
of change, one committed pattern doc — data source, error handling, empty states, which files are
shared — stops four divergent implementations. Minutes to write, and it saves the reconciliation.

Merge the branches into the integration branch, resolve the conflicts you predicted, then verify on
the MERGED tree: build, boot, suite. Per-branch green is not integration green.

`references/parallel-isolation.md` has the allocator recipe (worktree, ports, DB-from-template,
allocation map, teardown).

## 3. Verify before you report — child summaries are self-reports

A child saying "done, 48 routes mapped" is a claim, not a fact. Before it reaches the human:

- re-run the child's headline counts yourself (recipes in `references/verification-recipes.md`);
- for anything with a rendered surface, compare what a browser actually renders — text-stripping
  HTML invents differences that do not exist (recipes, same file);
- for a UI port, verify BEHAVIOUR alongside appearance: rendered-text parity cannot see a missing
  interaction, so diff the handler surface against the original and require a click-level check
  (recipes, same file);
- confirm every artifact exists and is non-trivial (`ls -l`, `wc -l`);
- prove the read-only constraint held (target mtimes vs dispatch time);
- grep the artifacts for leaked secret values;
- parse each handoff JSON, so a malformed handoff fails here and not downstream.

If a child's declared total disagrees with your own enumeration, re-fetch and reconcile in
writing. Never average two numbers and never quietly pick one.

## 4. Coverage is a basis, not a percentage

Never assert "100% covered" on a child's behalf. Report what was read in full, what was skipped,
and what was not analysed, plus the entry-point census behind the number. Two passes over the
same code often count the same thing differently (one counts events, another counts events plus
lifecycle hooks) — state each basis and reconcile explicitly, or the mismatch resurfaces later
as a "contradiction" in your own docs. When a later pass corrects an earlier pass's figure, say
so in the next round's briefs and mark the superseded figure as superseded, in the docs and in
the state file. Two passes that independently reach the same correction are strong evidence; one
pass contradicting an earlier one is a finding you must resolve, not a footnote.

## 5. Open questions are a deliverable

Collect what the code cannot answer and carry it to the human, split into **blocking** and
**non-blocking**. For every non-blocking question state the default you chose and why, so work
is not stalled on trivia. Never guess business intent from code.

## 6. Stop at the human gate

A pipeline phase ends with a STOP and a report, not with the next phase. Never merge, deploy,
run migrations against non-local DBs, or touch production. If the goal itself is still a template
placeholder, the read-only discovery phase is still goal-independent and worth running — but do
not start design, and surface the placeholder as the top blocking question.

## Reporting to the human

- Plain text, one phase-prefixed line per change: `[PHASE] task — result — next`.
- Lead with what was produced and where (absolute paths), then verified evidence, then blockers,
  then the single next action you need from them.
- State the deviations from the repo's own AGENTS.md that you made, and why.
- Keep it short; do not replay the process.
- **When the deliverable is runnable, actually start it and hand over the URL**, with the ports and
  the data source it is running against. "Can I see it running?" is answered by bringing it up, not
  by describing commits — lead with the URL and put the commit list second.
- **Re-check that handover server immediately before you report.** A long-lived background server can
  be reaped between turns, and a demo whose API has gone shows its offline state to the human opening
  the URL you just gave them. Restart both halves, re-verify the status codes, and report only what is
  actually up at that moment — an app handed over as running when it is not costs more trust than one
  that was never started.
- **Say plainly which parts are live and which are not wired yet.** A screen rendering identical
  content from mock data is not integrated; presenting it as working is a claim the next session
  inherits as fact.
- **When you hold work behind a gate, give the blocker and the one recommended path in a single
  line**, so a one-word reply unblocks the next wave. A hold with no actionable default stalls the
  whole pipeline.

## Pitfalls

- **Blaming your agents for pre-existing repo dirt.** A read-only target can already have
  uncommitted changes and untracked files at session start. Compare the dirty file's mtime with
  your dispatch time before attributing it to a child; if it predates dispatch, record it as a
  known gotcha instead. Your own `git status` / `git diff` bump `.git` metadata mtime — that is
  not a modification.
- **Overwriting a checkpoint file you only `cat`-ed, or that you have patched since you last wrote
  it.** The write tool refuses to replace an existing file this task has not loaded with `read_file`
  — a `cat` in the terminal does NOT satisfy that guard, and neither does your own earlier
  `write_file` if you have since patched the file, committed, or lost the content to a context
  compaction. A file `cp`-ed into the target in this same task arms it too. The guard re-arms; it does
  not remember. Load it with `read_file` (every page) immediately before the `write_file`, or prefer a
  targeted `patch` for anything smaller than a rewrite. For a file you intend to replace wholesale,
  `rm` it first and write fresh — loading a file you are about to overwrite is a wasted round trip. A
  blocked write costs a full round trip in the middle of a checkpoint.
- **Filling the state file with intentions.** `.agent/STATE.md` is the resume point for a session
  with no memory: artifacts, coverage, verified evidence, decisions, open questions, deviations.
  Write it after the work lands, from verified facts.
- **`git init` to satisfy a checkpoint rule.** "Commit after every task" cannot run when the kit
  root is not a repo. Flag it to the human; do not initialise a repo unprompted.
- **Resuming by re-reading the repo.** On a new session, read `.agent/STATE.md` and only the docs
  it points to — never the whole tree.
- **Reading a secret-bearing file to inventory it.** Redact on the way in:
  `sed -E 's/=.*/=<redacted>/' .env` lists the variable NAMES without the values. Never `cat` it.
- **Creating a task database with a plain `CREATE DATABASE`.** It inherits only the default template,
  so a stack that needs an extension (`geography`, `vector`, `uuid-ossp`) dies at the ORM's
  schema-sync with a missing-type error that reads like a code bug. Create from a template that
  carries the extension and assert the type exists in the new DB.
- **Auto-detecting the database server by "any postgres container on this host".** The host may be
  running someone else's project. Restrict detection to an image you can prove is the right one —
  never write into an arbitrary container.
- **Running a DB-asserting suite with only its base URL set.** If any test reads the database
  directly, its DB env must point at the SAME database the server under test uses, or the spec falls
  back to a config file, reads a different database, and fails one test for no visible reason. Export
  the DB vars alongside the URL.
- **Trusting the numbers attached to a child's conclusion.** A child can conclude correctly while its
  supporting counts are sloppy. Re-run the comparison yourself; when your figure differs but the
  conclusion holds, quote your figure.
- **Treating appearance parity as the deliverable in a migration or rebuild.** Faithfully reproducing
  the old app's screens passes every visual diff and still fails UAT, because the ported controls do
  nothing. Measure the original's interactivity before porting: `grep -c onClick` and `grep -c useState`
  against the source tree are the floor you must carry across, and a UI can be a click-dead shell with
  dozens of buttons that never had handlers. Fix the acceptance bar with the human early — "could a tester
  actually use this?" beats "does it match the screenshots?" — and treat everything the UI advertises but
  cannot do (a Create button with no handler, a leaderboard with no endpoint, a "my teams" tab with no
  identity) as a UAT liability rather than parity to be proud of. Reads without writes leave an app that
  cannot be exercised end to end. Put the resolution in every page-owning brief, verbatim: make it
  real against the live API; if you cannot, render the control DISABLED with a visible reason — never
  fabricate data and never leave a control that silently does nothing. That single clause is what
  separates an honest gap (acceptable, reviewable) from a fabricated one (a defect that survives
  review) and from a dead control (the original complaint).
- **Exporting env in your own shell and assuming your children start clean.** Children inherit the orchestrator's exported environment, and terminal state persists across your own calls: after
  `set -a; . ./.env; set +a` in one app's directory, that file's `NODE_ENV` and the PREVIOUS task's
  `DB_DATABASE` stayed live for every later call and every child. The symptoms looked unrelated and
  were both mis-diagnosed as pre-existing — a web build failing inside the framework's own
  `/_global-error` prerender, and a child's cleanup helper truncating the last task's database because
  dotenv does not override an already-exported variable. Pass connection details explicitly in every
  brief, set them inline per command, and read your own env back (`echo $NODE_ENV`) before blaming the
  repo. When a child reports a "pre-existing" failure, reproduce it under a clean env
  (`env -u NODE_ENV`) before accepting that label.
- **A mutating spec suite that leaves its rows behind in a shared database.** Verification specs that
  create users/teams/matches as fixtures and do not clean up inflate the very database the demo points
  at: the row count the human sees drifts upward run after run (33 teams where the seed defines 28), and
  the seed cannot fix it because it only owns its own rows. Delete the strays when preparing a handover,
  count the rows you are handing over against the seed's own totals, and treat "spec does not clean up"
  as a named follow-up in the QA report rather than silently reseeding around it.
  Clean them by DIFFING against the loader's own declared identities, not by eyeballing ids: extract the
  addresses (or keys) the loader creates straight out of the loader's source, diff that set against the
  live table, and delete everything not in it. Delete through the app's OWN endpoints wherever one
  exists — read the controller for a `Delete` route before reaching for SQL, because an endpoint you did
  not know about carries the cascade, the authorisation and the audit path that a raw `DELETE` bypasses.
  Re-count against the loader's totals afterwards and report the numbers you are handing over.
- **A secret a child adds to a gitignored `.env` never reaches the integration branch.** Worktrees
  materialise only TRACKED files, so a child that "adds a dev value to `.env`" writes it into its own
  worktree, and the merge cannot carry it. The integration tree then boots without it — and if the
  app reads that secret lazily (at first use rather than at boot), you get a 500 on a working feature
  and a hunt for a code bug that does not exist. When a wave introduces a new secret: add the value to
  the MAIN checkout's env file yourself as part of integration, and put "copy `.env` from the main
  checkout before you run anything" in every later brief. Prefer boot-time fail-fast for required
  secrets — a lazy check converts a missing-config error into a runtime 500.
- **A rebuilt artifact does not change a RUNNING process.** Verifying a merged wave against a server
  that was started before the build is verifying the OLD code: a Node process has its modules in
  memory, so `dist` being fresh on disk is irrelevant to it. I "found" an auth regression this way — a
  stale process still holding the port (my new launch died silently) served the pre-merge behaviour and
  the code was correct all along. Before verifying on a merged tree: kill the listener by PID
  (`ss -ltnp | grep :<port>`), confirm the port is FREE, relaunch, and check the process start time is
  AFTER the build time. A launch that dies without an obvious error is the tell — check whether the old
  process is still bound before you read anything into the response.
- **A child that "mirrors its handoff into the main checkout" blocks the merge.** An untracked file
  written into the integration tree (`git` refuses to overwrite it) aborts `git merge` with
  "Please move or remove them before you merge" — and because the merge prints a normal diff stat
  first, a quick read looks like success. Tell children to write ONLY inside their own worktree, and
  after every merge verify the branch is genuinely an ancestor of HEAD
  (`git merge-base --is-ancestor <branch> HEAD`) instead of trusting the absence of a conflict.
- **A child's "blocked" honest report is a to-do for you, not a failure.** W5 shipped its pages,
  reported that the parallel W3B endpoints did not exist in its worktree so it could not demonstrate
  the success path, and left the pages surfacing the 404 honestly. That is the correct behaviour: the
  integration test (register → emailed link → verify → login → gated page) is the ORCHESTRATOR's to
  run on the merged tree, because only the merged tree has both halves.
- **A child will edit outside its owned list to keep a gate green.** W3 and W3B both touched the
  user DTO / the users specs beyond their briefs, for defensible reasons, and flagged it. Read those
  flags; they mark the real seams between tasks, and a merge that silently accepts the edit is how a
  shared file becomes ownerless.
- **Reading an empty gate output as a pass.** Never infer a gate passed from silence. A check whose
  output you piped through `tail` can print a blank line and still exit non-zero — capture and READ
  the code (`cmd; echo EXIT=$?`, or `${PIPESTATUS[0]}` after a pipe). Then re-run EVERY gate on the
  MERGED tree: two children can each watch a gate go green on their own branch and the merge still
  breaks it, because one child adds a line to a file the other child's verified tree never had. A
  gate verified before a merge is not evidence about after it, and the failure surfaces in whatever
  file the merge touched last.
- **Two sibling files that compile alone and collide once merged.** A file with no top-level
  `import`/`export` is a global script, so its top-level `const`s sit in SHARED global scope: two
  independently-authored spec files that each declare helpers like `request` / `BASE` / `api`
  typecheck fine on their own branches and fail `tsc --noEmit` (TS2451, cannot redeclare) only once
  both are in one program. Each child's green was true and the merge still broke the gate. Fix by
  makes new spec files modules (`export {};` — no behaviour change, jest is unaffected) and giving
    their top-level helpers distinct names; never delete or weaken the older suite to make room. This
    is exactly why typecheck belongs in the set of gates you re-run on the MERGED tree, alongside the
    suites.
  - **Freezing a list contract without freezing its FILTERING semantics.** When several consumers are
    typed against one read endpoint you froze, the response shape is only half the contract. If the
    endpoint returns a SUPERSET of what a screen wants — every invite regardless of status, every row
    regardless of owner, all matches rather than the current user's — then each consumer must filter,
    and a missing filter never surfaces as an error. It surfaces as an unresponsive control: the write
    persists, the stored row changes, and the item stays in the list forever, which reads exactly like
    a broken button and sends you debugging a correct write path. State the subset each screen displays
    alongside the frozen shape, and when a UI action appears to have no effect, check the consumer's
    filter before the endpoint.
- **Handing over a demo whose fixture a suite has since mutated.** A merged integration suite that
  WRITES (accepting an invite, creating a row) changes the very rows the human is about to look at,
  so a demo verified before the suite run shows different data after it — a tab advertising a count
  goes empty, and the human reads that as your feature being broken. Re-run the seed on the demo
  database after any mutating suite run, confirm the counts you are handing over, and only then
  report the URL.
- **Accepting a fixture-dependent result without checking the fixture survived.** A child can verify
  a result against data that is not there afterwards — a seed run before the columns existed, a
  loader a later step overwrote, a database reset between its check and its handoff. When a
  deliverable depends on seeded rows, re-run the loader on the merged tree and verify the DATA STATE
  directly (query the rows the endpoint reads, not just the endpoint's response). "My endpoint
  returned 14 rows" is a claim about the moment the child tested, not about the artefact it left —
  and an endpoint returning `[]` because the fixture never landed looks exactly like a broken
  endpoint, which sends you debugging correct code.
- **A fixture loader that deletes children by the tuples it created.** The teardown phase must scope its
  deletes by PARENT, not by the exact rows the loader inserted: `DELETE FROM team_members WHERE team_id =
  ANY($owned_parent_ids)`, never `WHERE (team_id, user_id) IN (<the tuples I wrote>)`. A child row added
  to an owned parent by anything else — a spec, an API write, a person clicking accept — is invisible to
  a tuple-scoped delete, survives the reset, and then blocks the parent's own delete with a foreign-key
  violation. Such a loader passes for weeks and breaks the first time someone exercises the feature it
  seeds, which reads as "the seed is broken now" rather than as an ownership bug. Detach references you
  do not own (`UPDATE ... SET fk = NULL`) instead of deleting them, and prove idempotence by running the
  loader TWICE and diffing the per-table row counts.
  **When you fix the first instance, audit EVERY parent->child relation in that loader in the SAME pass.**
  Fixing only the reported site schedules the next failure: this exact bug recurred three times in ONE
  file (child rows of teams, then of chat rooms, then of matches), each surfacing only when a different
  feature was exercised, each costing a full round trip. Enumerate the parents the loader owns, then for
  every parent check how its children are deleted. Prefer a stable id as the parent's identity — a
  natural-key delete (`WHERE (name, sport) IN (...)`) silently stops matching the moment anyone edits a
  row through the app the loader seeds.
- **Re-dispatching over a child that died mid-run without looking at what it left.** When a child
  dies part-way (transport or budget failure, timeout, a hard stop) its worktree holds unverified
  partial work and nothing reports how far it got. Inspect first: `git -C .worktrees/<id> log
  --oneline -3` (no commits means nothing was checkpointed) and `git status --short` for the files it
  touched. Infer progress from artifact state — a database with no schema proves the server was never
  booted, so none of its code ever executed. Then re-dispatch with "audit this partial work as an
  untrusted draft, keep what is correct, finish the job" rather than blindly trusting or deleting it.
- **Teardown that deletes more than the dispatch created.** `--remove` style cleanup should keep the
  task branch (the branch IS the work — you still have to merge or discard it) and orphaned scratch
  databases are destructive to drop: ask, and treat a blocked approval as stop, not as a puzzle to
  route around.
- **Removing a worktree while a server a task started is still running.** The process outlives its
  worktree, keeps holding the port, and the next wave dispatched onto that port dies with a bind
  error while the allocation map says the port is free. Find them before reusing a block:
  `ss -ltnp | grep :<port>` for the pid, then `readlink /proc/<pid>/cwd` — a `(deleted)` suffix means
  it is running from a removed worktree and it is yours to kill. Sweep the whole tree, not just the
  port you noticed: `for p in $(pgrep -f '<server-pattern>'); do readlink /proc/$p/cwd; done` and kill
  every `(deleted)` hit.
- **The demo server you left running for the human, killed by your own children.** Children restart
  servers to test, and their kill patterns are broad (`pkill -f dist/main.js`, `pkill -f next-server`),
  so they take your handover process with them — and a launcher that kills the previous listener and
  starts the new server in the SAME shell shares its process group, so one stray signal takes both.
  Relaunching on every death notification is a thrash loop that produces nothing but churn: check what
  is actually listening, relaunch ONCE, say plainly that the demo may drop while the wave runs, and
  relaunch again as part of verifying the merge. Telling the human it may be down is honest; silently
  relaunching four times and reporting "it's up" is not.
- **Filing a 500 you caused yourself.** A mistyped REST path can match a parameterised route rather
  than 404: `GET /api/community/posts` lands on `@Get(':id')` with `id='posts'`, and the invalid id
  produces 500. Re-read the controller decorators and hit the real path before calling it a defect,
  or you hand the human your own typo as a bug report.
- **Treating a brief's premises as facts.** A brief asserting "there is no X endpoint" is your
  hypothesis, not evidence. A child that answers "your brief was wrong — the route is live and the
  real gap is Y" has improved the fixture: verify its correction against the running system, record
  it, and fix the premise in the next brief. Do not route it back as scope drift, and do not let the
  uncorrected premise propagate into the docs.
- **Inventing a contract's field names instead of reading them off the system of record.** When new
  state has to be stored, those keys are not yours to choose: an existing app's UI labels, an existing
  schema, or an already-frozen response ARE the vocabulary, and a guessed set costs a rename through
  every consumer later. Before writing the brief, open the source that already names it — the original
  page's markup, the existing DTO — and quote its exact keys into the contract. If you discover the
  mismatch after dispatch, `steer` that child at once with the corrected names ("my invented names are
  WRONG, discard them, use these"): a running child receives steering text at its next tool result and
  can still refactor cheaply, whereas a wrong vocabulary that lands is a migration.

## Verification

- [ ] Every artifact exists on disk with real content, not just a child's word.
- [ ] Headline counts independently reproduced.
- [ ] Read-only target proven untouched.
- [ ] No secret values in any artifact.
- [ ] Handoff JSONs parse and carry a `status`.
- [ ] Blocking questions surfaced; the phase ended with a STOP.
- [ ] Each parallel branch merged, then re-verified on the MERGED tree (build, boot, suite) —
      per-branch green is not integration green.
- [ ] Every gate's EXIT CODE read, never inferred from an empty or tail-truncated line.
- [ ] Fixture/data state re-queried on the merged tree, not just the endpoint that reads it.
- [ ] No two tasks in a wave wrote the same file.
- [ ] For a production-readiness handover: the composed stack was started from a CLEAN state and every
      service passed its healthcheck; each secret value was grepped out of the built artifacts; and
      every flow claimed (register/verify/login/reset) was exercised against that running stack with
      the resulting state read back.
