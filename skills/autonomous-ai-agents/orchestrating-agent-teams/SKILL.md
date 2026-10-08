---
name: orchestrating-agent-teams
description: "Use when orchestrating subagent teams over a repo."
version: 1.1.0
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
  paths to write.
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
   produce failures neither can explain.
3. **Its own `.env`.** A worktree materialises only tracked files, so a gitignored `.env` is absent
   and anything that fails fast on a missing secret aborts at boot. Copy it in and override the
   task's DB name and port.
4. **Hardlinked dependencies, never a fresh install.** `cp -al` the main checkout's `node_modules`
   into the worktree's app dir — seconds instead of tens of minutes. Then put "dependencies are
   already installed, do NOT run install commands" in every brief.
5. **Write targets partitioned per file.** Give each task an ownership list AND a "do not touch"
   list. A shared helper module is a collision waiting to happen: if several tasks need the same new
   capability, make adding it its own task in an earlier round rather than letting them all edit it.

**Fixtures, oracles and contracts land in an earlier round than their consumers.** A seed script, a
captured baseline, or a shared typed contract must be merged before the tasks that are verified
against it are dispatched, so every consumer measures against identical data.

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
  compaction. The guard re-arms; it does not remember. Load it with `read_file` (every page)
  immediately before the `write_file`, or prefer a targeted `patch` for anything smaller than a
  rewrite — a blocked write costs a full round trip in the middle of a checkpoint.
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
- **Teardown that deletes more than the dispatch created.** `--remove` style cleanup should keep the
  task branch (the branch IS the work — you still have to merge or discard it) and orphaned scratch
  databases are destructive to drop: ask, and treat a blocked approval as stop, not as a puzzle to
  route around.

## Verification

- [ ] Every artifact exists on disk with real content, not just a child's word.
- [ ] Headline counts independently reproduced.
- [ ] Read-only target proven untouched.
- [ ] No secret values in any artifact.
- [ ] Handoff JSONs parse and carry a `status`.
- [ ] Blocking questions surfaced; the phase ended with a STOP.
- [ ] Each parallel branch merged, then re-verified on the MERGED tree (build, boot, suite) —
      per-branch green is not integration green.
- [ ] No two tasks in a wave wrote the same file.
