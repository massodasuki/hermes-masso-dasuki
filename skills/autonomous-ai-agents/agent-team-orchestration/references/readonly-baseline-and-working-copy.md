# Frozen tree → untouched baseline, and the working copy

For work where the target is FROZEN (`legacy/`, `rivalWeb/` — read-only, often the migration's
parity oracle) and every change must happen in a new tree beside it.

## 1. Capture the untouched baseline before the first dispatch

```
find <frozen> -not -path '*/node_modules/*' -not -path '*/.git/*' \
  -printf '%T@ %p\n' | sort -k2 > before.txt
```

Re-run after each round and `diff before.txt after.txt`. Empty diff = nothing was written. This is
the proof; a child's assurance that it only read is not proof.

Two things that look like damage and are not:
- your own `git status` / `git diff` bumps `.git` metadata mtimes;
- a tree that was ALREADY dirty at session start (uncommitted edits, untracked dirs). Compare the
  dirty file's mtime against your dispatch time; if it predates dispatch, record it as a known
  gotcha rather than a child's edit.

Also capture `git -C <frozen> status --porcelain` as text and compare it verbatim later — it is
cheaper than the mtime walk and catches deletions.

## 2. Creating the new repo (only once the human has approved it)

```
git init -b main
git config user.email '<repo-scoped>'   # repo-LOCAL: never touch the user's global identity
git config user.name  '<repo-scoped>'
```

`.gitignore` at minimum: `node_modules/`, `dist/`, `build/`, `.next/`, `out/`, `coverage/`,
`.env` plus `.env.*` with `!.env.example`.

**The gitlink trap.** If the frozen tree contains its own `.git`, `git add <frozen>` records a
gitlink — its HEAD commit, not its contents. Consequences: the code is absent from this repo's
history; a clone of this repo does not contain the oracle; and this repo reports permanently dirty
the moment the frozen tree is dirty. Making it a true vendored copy means deleting the frozen
`.git`, which the read-only constraint forbids. So git-ignore it, reference it by path, and put the
reason in the `.gitignore` itself so the next session does not "fix" it. Tell the user plainly that
this deviates from any instruction to commit the legacy tree, and that it is one line to reverse.

Branch before the first change: `git checkout -qb ai/<task>-<slug>`.

## 3. Copying an app out of the frozen tree

- Copy once, then change only the copy; the frozen tree stays the oracle for characterization.
- Exclude `node_modules/`, compiled output (`dist/`), and the REAL `.env`. Copy `.env.example`.
- Verify nothing secret came along: `git ls-files | grep -iE '(^|/)\.env'` → `.env.example` only;
  and no `node_modules`/`dist` path is tracked.
- Verify the copy is faithful — counts must match the source EXACTLY, not approximately:
  `find <copy>/src -type f | wc -l` and `find <copy>/src -name '*.ts' -exec cat {} + | wc -l`
  against the same numbers on the frozen source.
- Copy the repo-root files the app needs (`docker-compose.yml`, schema dumps). If the working-tree
  version of one differs from its committed version, copy the working tree and say so explicitly.
- Prove the build: `npm ci` (or the repo's real package manager) then the build script, capturing
  exit codes and produced artefacts. An unrun build is not evidence, and reusing the frozen tree's
  `node_modules` to fake a pass is worse.

## 4. Relative paths break on flattening — expect it, don't fix it here

Flattening `<frozen>/backend/*` into `apps/api/*` invalidates every path that was relative to the
old root:

- compose bind mounts (`./backend:/app`),
- init-script volume mounts (`./backend/init-postgis.sql:/docker-entrypoint-initdb.d/...`),
- `env_file: backend/.env`.

Report them as findings. Do NOT edit that file inside the copy task if another task owns it — the
diff stops being reviewable and you lose the "the copy is faithful" property.

To actually RUN the copy: put a throwaway infra-only compose in the scratch dir (`$TMPDIR`/scratch),
starting only the dependencies with corrected paths, and run the app on the host. Never
`docker compose up` a service whose bind mount points at a path that no longer exists — there is no
'sandbox container' unless the repo really provides one.

## 5. The executed-baseline gate

Before any change lands in the copy, a characterization pass records today's behaviour against a
RUNNING instance with the real dependency (DB, broker). Rules for that brief:

- Pin per route/command the status code and the RAW body, kept as files on disk, plus one summary
  doc. These raw captures are what the upcoming diffs are judged against.
- Name the specific behaviours the next tasks will change (a field that must disappear, a request
  that must be rejected, an endpoint that may be erroring) so the "before" side is unambiguous.
- Make the checks re-runnable (e2e specs) where possible, and require the exact command and its real
  output; if that is not achievable, the child must say the captures were by hand.
- State in the brief that a written-but-unexecuted test plan must NEVER be reported as a pass. If
  the stack will not come up, `blocked` with the exact command and error is the correct answer —
  that is a finding, not a failure, and it costs one round instead of poisoning the plan.

## 6. Surface time

Any of these that you decided yourself rather than being told — the gitlink workaround, an
infra-throwaway compose, a copy that excludes files the instruction implied you would take — goes
into the state file as a **deviation with its reason**, and into the report to the human. The next
session resumes from that file and will otherwise re-litigate or silently undo the choice.
