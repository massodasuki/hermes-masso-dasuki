---
name: agent-team-orchestration
description: "Use when running a multi-agent SDLC pipeline over a repo."
version: 1.0.0
metadata:
  hermes:
    tags: [Multi-Agent, Orchestration, Delegation, Reverse-Engineering, Code-Review, Gates]
    related_skills: [claude-code, codex, opencode, requesting-code-review, codebase-inspection]
---

# Agent Team Orchestration

Driving a team of specialised agents (reverse-engineer / architect / developer / qa, or any
`agents/*.md` set a repo ships) through a gated pipeline over an existing codebase, and reporting
to one human owner.

You are the orchestrator: you decompose, dispatch, verify and gate. You do not write the
production code, and you do not accept a child's word for anything you can check yourself.

## Procedure

### 1. Recon before dispatching anything
- Locate the team's briefs (`*.claude/agents/*.md`, `agents/*.md`, `AGENTS.md`) and the checkpoint
  file (`.agent/STATE.md` or equivalent). Read them; they define the roles, the output shape and
  the pipeline order.
- **Verify the literal paths the request names.** Briefs and prompts routinely get paths, package
  managers and stack details wrong (a lowercase `./legacy` that is really `rivalWeb`, pnpm that is
  really npm). A wrong path costs a whole dispatch.
- Check the legacy tree's cleanliness BEFORE dispatch (`git -C <repo> status --porcelain`, store the
  output), and snapshot its file mtimes
  (`find <tree> -not -path '*/node_modules/*' -printf '%T@ %p\n' | sort -k2 > before.txt`). That
  snapshot, re-run and `diff`-ed after each round, is the only real proof a child honoured
  read-only — a child's assurance is not. Expect the tree to already be dirty at session start;
  compare the dirty file's mtime with your dispatch time before blaming a child.
  Recipes: `references/readonly-baseline-and-working-copy.md`.
- Answer environment questions yourself rather than leaving them as open questions: `command -v`
  the runtimes the plan depends on (container/DB runtime, node/npm, the package manager the docs
  claim). One `command -v` turns a blocker into a settled fact.

### 2. Plan rounds, not a flat fan-out
- Round 1..N in parallel: passes that are independent of each other.
- A final synthesis round, serialised after the others: backlog/ordering, open-questions, and any
  pass whose job is to read the earlier outputs. These cannot start until the rest land.
- **Partition the output files** so no two children ever write the same path. Concurrent writers to
  one file lose one of the two updates silently.
- Cap the fan-out to the repo's real size; one child per pass beats one giant child, because each
  stays inside one context window and a single timeout does not lose the whole run.
- **Parallel is the default; sequential is the exception and needs a reason.** Only a real dependency
  serialises work: a contract before its consumer, an oracle before the port, a baseline before the
  change it judges, a design decision before its implementation, and merge order on a shared file.
  Everything else that looks like a reason to serialise is a *collision* you can engineer away —
  see `references/parallel-task-isolation.md`.
- **Isolate every task on three axes:** its own git worktree + branch (its own index, so children may
  commit freely), its own port block, and its own database. Never run two children in one working
  tree — and never make yourself the single committer. A shared index is the most common reason
  people serialise dispatch, and it is entirely self-inflicted.
- **Split baselines per surface, not one monolithic sweep.** A single characterization pass that
  gates N dependent tasks is the most expensive serialisation available: capture the baseline per
  module/route/surface and unblock each task as soon as ITS section exists.
- **Batch mechanical work into ONE child.** Agent count, not wall-clock, is the cost unit: several
  small unrelated low-risk edits belong in one brief. Spend separate children only on separate reasoning.
- **Stagger heavy downloads.** Concurrent large installs and image pulls starve each other on one
  link; a starved pull looks exactly like a hang and costs more wall-clock than queueing it would have.

### 3. Brief each child self-contained
Children know nothing of your conversation. Every brief carries: task id, the output path(s) it may
write, the read-only roots it must not touch, the acceptance shape, and the previous round's
findings it must build on instead of re-deriving.
- Pass the repo's own agent brief as context verbatim, and say "follow this brief".
- Give a child the SKIPPED list too (`node_modules`, compiled `dist`, lockfile-only dirs). Otherwise
  it burns its budget scanning a compiled duplicate of the source it should be reading.
- **Override the brief's stack defaults against the actual repo.** Generic agent briefs ship
  defaults (an ORM, a package manager, a queue library, a monorepo layout) that may contradict the
  target. Name the conflict explicitly, state which one wins and why, and require the child to
  record the override as an ADR. Left implicit, the child invents a migration onto a stack the user
  never agreed to.
- Require evidence in the output: `path/File.ext:LINE` for every claim, an explicit `UNVERIFIED`
  marker for anything not executed, and `what was NOT analysed` alongside the coverage statement.
- Ask for the coverage statement in the enumerable form (`X of Y entry points`), never a percentage.

### 4. Verify on return — the child's summary is a claim, not evidence
- Confirm the artifacts exist and are non-empty (`ls -l`, `wc -l`), and that handoff JSON parses.
- **Re-derive every declared total with your own command.** `grep -c` the routes, the handlers, the
  `CREATE TABLE`s, `find | wc -l` the entity files. A child's count is a self-report; a wrong one
  silently propagates into every doc built on it.
- When two children disagree on a count, reconcile the *bases* rather than overwriting one with the
  other (13 entity classes vs 12 tables is not a conflict when two classes map one table). Write the
  reconciliation into the state file so the discrepancy is not re-litigated next session.
- Probe doc quality cheaply: `grep -oE '[A-Za-z0-9_/.-]+\.(ts|tsx|json|sql|yml|conf):[0-9]+' <doc> | wc -l`
  for citation density and `grep -c UNVERIFIED <doc>` for honest uncertainty. A doc with no citations
  is not evidence-based, however confident it reads.
- Verify the read-only tree is still clean. Compare against the baseline from step 1. Note that
  `git status` itself refreshes `.git/index` mtimes — do not read that as a child's edit; check
  tracked-content diff and source-file mtimes instead.
- Spot-check the one or two load-bearing technical claims yourself, in source. If a doc's central
  finding (a leak path, a broken query) is wrong, the whole plan built on it is wrong.
- **Inspect every child's commit before merging it: `git show --stat <sha>`.** Once children commit
  freely on their own branches, the failure to look for is a commit that swept in files another child
  was still writing — it makes the history, the PR and the blame all lie about who did what when, and
  nothing else will surface it. A clean child's commit contains only the paths it owns; anything else
  is a finding to raise, not a merge to proceed with.
- **After merging a wave, prove the merged result yourself — never infer it from the children.** Build
  the merged tree, boot it against a **freshly created** database (not one a child left half-migrated),
  and run the full suite against that. Expect conflicts only where two children rewrote the same
  verification artifact — the shared characterization spec is the usual culprit, because every task
  that flips a pinned behaviour edits it. Resolve that file yourself (keep the newest behaviour
  assertions, re-point the paths the other task moved) and re-run. N individually-green branches are
  not a green merged tree.
- **Run that suite with the SAME environment the server under test uses.** A suite whose assertions
  read the datastore directly (not only over HTTP) also needs the DB host/name/user exported — run it
  with the base URL alone and it silently falls back to parsing whatever `.env` it can find, asserting
  against a *different* database than the running server. The result is one lone failure that looks
  exactly like a regression: the tell is `undefined` coming back for a fixture the suite itself just
  created. Re-run with the full env before reporting anything, and if it goes green the bug was your
  invocation, not the code — say so plainly rather than filing it as a finding, and make the suite's
  env requirement explicit in CI.
- **Prove a write-path or security fix at the datastore, not from the response body.** A response that
  refuses a write and a response that refuses it *after* writing look identical from the body alone.
  For any claim of the form "this hole is closed", require the child — and check yourself — to re-read
  the stored row before and after and compare it (a hash of the column is enough; never print the
  secret). Put that requirement in the brief: otherwise the child hands back an HTTP status code and
  calls it proof.
- **Re-verify a rendered-output claim with the instrument that captured the oracle.** A ported screen's
  parity is a claim about rendered text, so re-read it in a real browser (`document.body.innerText`)
  the way the oracle was captured, and diff line by line. Stripping the served HTML to text cannot see
  CSS `text-transform` and drops the separators layout puts between adjacent inline nodes, so a
  *correct* port reports dozens of phantom deltas. When a cheap instrument disagrees with the capture
  instrument, the instrument is wrong until proven otherwise —
  `references/ui-port-parity-verification.md`.

### 5. Checkpoint and gate
- After each round, update the state file: phase, task ids, done-with-evidence, next 3 steps,
  decisions, deviations from the repo's own process docs, open questions, gotchas.
- Record deviations **as deviations** with the reason. Do not silently absorb them, and do not fix
  the repo's process docs unless the user asked.
- Batch the human gate into ONE prompt: every blocking question together, each with a recommended
  default listed first and the evidence that raises it. Ask before spending an expensive run when
  the answer would change what that run produces.
- "Follow the recommendations" is a valid blanket answer: apply every default, then **write the
  answers into the decision file** so the acceptance is auditable rather than implied.
- When the human asks what has been done so far, answer with a compact plain-text tally — artifacts
  and their paths, commits, what is in flight, what is next — not a narrative of the process. It is
  usually a sign they lost track while a slow phase ran; fix the phase, not just the report.

## Pitfalls
- Don't dispatch before reading the team's briefs — you will brief the children wrong and lose a round.
- Don't let a child touch the read-only source tree, and don't trust that a child honoured it: prove
  it from the baseline. A child asked to analyse a repo will happily "tidy" it.
- Don't accept a child's claim about an external side effect or a design decision it made on your
  behalf; read the artifact, or ask the user.
- Don't restate the repo's own map or the tool's parameter list back into the child briefs — pass the
  path and let it read. Briefs are for scope, constraints and prior findings.
- Don't leave a child's "next_recommended" as the routing decision without checking it against the
  pipeline order and the human gates.
- Don't let an expensive implementation run start while a Tier-0 prerequisite or a human-gated item
  (repo bootstrap, secret rotation, an unapproved scope creep) is still open.
- **Vendoring a frozen tree that has its OWN `.git`.** `git add <frozen>` records a gitlink, not the
  code: the new repo's history lacks it, a clone lacks it, and the new repo's `git status` sits
  permanently dirty following the frozen tree — so an instruction to "commit the legacy tree"
  cannot be honoured as written. Git-ignore it and reference it by path (state the reason in
  `.gitignore`, and tell the user it is a deliberate, reversible deviation); real vendoring would
  mean deleting the frozen `.git`, which a read-only constraint forbids.
- **Fixing a path that broke because you copied a tree.** Flattening `<frozen>/backend/*` into
  `apps/api/*` silently invalidates compose bind mounts, init-script volume paths and `env_file`
  paths. Report them as findings and leave the file to the task that owns it — editing it inside
  the copy task destroys the "the copy is faithful" property. To actually run the copy, stand up a
  throwaway infra-only compose in the scratch dir instead.
- **Promising a run whose dependency is not present.** Check while briefing (`docker images`,
  `command -v`) that the required image/binary/extension exists, and tell the child in the brief
  that `blocked` is an honest outcome if the stack will not come up. Otherwise you get a
  hand-written test plan returned as a "pass".
- **Reporting a copy as verified on file counts alone.** A copy is faithful only if the source file
  count and LOC match exactly on both sides — and only `.env.example`, never a real `.env`, is
  tracked in it.
- **`git add -A` while children are mid-flight.** Children writing into the main checkout are
  uncommitted work; a sweeping add-and-commit swallows their in-progress files into your checkpoint
  and makes the history lie about what was done when. Commit explicit paths, always.
- **A `{` `}` sequence anywhere in a `delegate_task` goal.** The dispatcher reads it as an unexpanded
  template marker and rejects the entire call, so a brief that quotes a shell format string
  (`curl -w '%{http_code}'`) fails to send — and the rejection is the whole batch, so every task in it
  must be re-sent. Give the child a brace-free substitute rather than prose, so the command stays
  exact: `curl -s -D - -o /dev/null <url> | head -1` prints the status line. Sweep every goal for
  braces before dispatching; on a large batch this is minutes of re-sending.
- **Reading `git diff <base>..<branch>` as "the child edited my tooling".** If you commit to the
  integration branch AFTER allocating a wave, each task branch still carries the pre-commit version of
  those files, so the diff renders your own later commits *in reverse* and looks exactly like a child
  reverting the harness, the allocator or the state file. The merge is still clean — only one side
  changed them, so git keeps yours. Read the diff as "what this branch would bring", confirm with
  `git show --stat`, and do not force, re-apply or re-implement anything on the strength of it.
- **`pkill -f <pattern>` whose pattern is in your own command line.** Cleaning up a server a child
  left running, the pattern also matches the shell executing the cleanup, and the command dies by
  SIGTERM with its own output missing. Kill the PID you observed (`ss -ltnp` reports it), or keep the
  pattern out of the command text.
- **Routing around a destructive cleanup step that was denied or left unanswered.** Teardown that
  deletes things — dropping a task database, removing a worktree, deleting a branch — can stop on an
  approval prompt. When approval is not granted, that IS the answer: do not rephrase the command, split
  it into innocent-looking pieces, or reach the same end state another way. Do the non-destructive
  parts of the teardown, leave the residue, and report it explicitly ("these task databases still
  exist; say the word and I'll drop them") so the human can grant it deliberately. Working around a
  consent gate silently converts it into a formality.
- **Believing either verdict from an unanchored grep for a forbidden pattern.** "No integration was
  added" and "no client component" are proven by grepping for `fetch(` / `axios` / `'use client'` — and
  the naive pattern also matches the JSDoc prose a careful child writes *about* not doing it, so a
  clean tree reads as a violation. Anchor the directive form (`grep -rn "^'use client'"`) and read the
  hits before believing either a pass or a failure.

## References
- `references/reverse-engineering-passes.md` — the pass catalogue for turning an undocumented
  codebase into evidence-cited docs, and how to group the passes into dispatch rounds.
- `references/handoff-and-gates.md` — the handoff JSON contract, the coverage statement, the
  question/answer sheet format, the behaviour-difference ledger for migration work, and the
  state-file sections that survive a fresh session.
- `references/readonly-baseline-and-working-copy.md` — proving a frozen tree stayed untouched,
  bootstrapping the new repo without a gitlink trap, copying an app out of the frozen tree,
  relative paths that break on flattening, and the executed-baseline gate.
- `references/parallel-task-isolation.md` — the collision taxonomy (index / ports / database /
  one-writer-per-file / network), the three isolation layers and the allocator contract, per-surface
  baselines, and the cost rules for deciding when a task deserves its own child.
- `references/ui-port-parity-verification.md` — verifying a re-implemented frontend against a captured
  oracle: the capture-instrument rule, why HTML-to-text produces phantom diffs, the route/tab diff
  procedure, the parity-not-improvement rule for the first port slice, and how to prove the
  "no integration added" negative claims.
