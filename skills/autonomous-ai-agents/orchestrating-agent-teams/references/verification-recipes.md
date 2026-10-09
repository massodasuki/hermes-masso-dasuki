# Verification recipes

Run these at the verify step (SKILL.md section 3) before reporting a phase done, substituting the
real paths, source globs and dispatch time. Each one reproduces or refutes something a subagent
claimed.

## Artifacts exist and are real

```sh
ls -la docs/legacy docs/REPO_MAP.md .agent/handoffs
wc -l docs/legacy/*.md docs/REPO_MAP.md
```

## Handoff JSONs parse and carry a status

```sh
for f in .agent/handoffs/*.json; do
  python3 -c "import json;d=json.load(open('$f'));print('$f',d.get('status'),d.get('task_id'))"
done
```

## Evidence density — does the doc actually cite code?

A prose-shaped doc that cites nothing is a summary, not reverse engineering.

```sh
grep -oE '[A-Za-z0-9_/.-]+\.(ts|tsx|js|jsx|py|go|rb|java|php|cs|sql|json|ya?ml|conf|vue):[0-9]+' docs/legacy/*.md | wc -l
grep -c 'UNVERIFIED' docs/legacy/*.md   # honest gaps, expect > 0
```

## Read-only proof — nothing under the target changed since dispatch

```sh
find <target> -not -path '*/.git/*' -newermt '<dispatch-time>' -printf '%TY-%Tm-%Td %TH:%TM %p\n' | sort -rn | head
```

Any hit is either your own doing or a violation. To settle a single suspicious file:

```sh
stat -c '%y %n' <suspect-file>            # mtime vs dispatch time
cd <target> && git status --porcelain      # what is dirty now
git diff --stat <suspect-file>             # is the change yours?
```

An empty `find` output plus a dirty `git status` means the tree was already dirty — check mtimes
before blaming an agent.

## Secret-leak check on produced artifacts

```sh
grep -nEi '(password|passwd|secret|token|api[_-]?key|private[_-]?key)[[:space:]]*[=:][[:space:]]*[^ <]' docs/**/*.md .agent/handoffs/*.json
```

Inventory a secret-bearing file without disclosing values:

```sh
sed -E 's/=.*/=<redacted>/' .env
```

## Re-derive the entry-point census the child reported

```sh
# HTTP routes per controller, and the total
grep -rcE '@(Get|Post|Patch|Put|Delete)\(' <src>/modules/*/*.controller.ts
grep -rhE '@(Get|Post|Patch|Put|Delete)\(' <src> | wc -l

# websocket gateways and message handlers
grep -rln '@WebSocketGateway' <src>
grep -rc '@SubscribeMessage' <src>

# scheduled work (a common "0 found" claim worth checking)
grep -rnE '@Cron|ScheduleModule|setInterval' <src>

# queue/worker truth: who consumes, and does anything publish?
grep -rnE 'enqueue|publish\(' <src>
```

## Re-derive the data-model census (entity classes vs schema dump)

```sh
find <src> -name '*.entity.ts' | wc -l                              # entity classes
find <src> -name '*.entity.ts' -exec basename {} \; | wc -l         # sanity
# duplicate table mappings — two classes claiming one table is a real defect
find <src> -name '*.entity.ts' -exec grep -hoE "@Entity\(['\"][a-z_]+['\"]\)" {} + \
  | sort | uniq -c | sort -rn
# tables declared in a hand-written schema dump
grep -c 'CREATE TABLE' <schema>.sql
grep -oE 'CREATE TABLE[^(]*' <schema>.sql | sed 's/CREATE TABLE //;s/ *//' | tr '\n' ' '
```

A class count that EXCEEDS the distinct table count means two classes map the same table — report
it as a finding, not as a miscount, and check whether their column definitions disagree. Also diff
the dump's columns against the entities: a dump that is not executed by any tooling is
documentation, not schema, and the two drift.

## Rendered-surface parity — compare what the browser renders, not the HTML

For a UI port, a migrated page, or any "must be identical" claim, read the rendered text in a real
browser (`document.body.innerText`, or the platform's equivalent) and diff that against the oracle.
Stripping tags to text invents differences that do not exist — two traps, both of which produced a
page of false diffs on a port that was in fact exact:

- **CSS `text-transform`.** `innerText` reflects the rendered case; a tag-stripper returns the source
  case, so `ACTIVITY TIME` reads back as `Activity Time`.
- **Inline element boundaries.** `innerText` breaks the line between inline nodes where tag removal
  concatenates them: `vs Thunder` reads back as `vsThunder`, `Futsal 8/10` as `Futsal8/10`.
- **A wrong selector or label reports real data as MISSING.** Locating a section by the name you
  expect — the SPA's copy, the brief's wording — rather than by the DOM's actual heading fabricates a
  "this block is not implemented" finding: a panel headed `Leaderboard` is invisible to a search for
  `Standings`, and an action button labelled `Create Team` is skipped by a filter that excludes that
  literal string. Dump what is actually there before asserting anything:
  `[...document.querySelectorAll('h1,h2,h3')].map(h => h.textContent)` and
  `[...document.querySelectorAll('button')].map(b => [b.type, b.textContent.trim()])`. Prefer stable
  hooks (form `id`, `button[type=submit]`) over text matching, and when a check says a feature is
  absent, re-run it against the discovered labels BEFORE filing the defect — a wrong selector
  fabricates the same class of false finding as a tag-stripper, and it will have you debugging
  correct code.

Capture the oracle and verify it the SAME way. A different extraction method is a different
measurement, not a second opinion. Compare line-exact first, normalise whitespace only after, and
report the result as a line diff with counts.

## Behaviour parity — a port can be textually exact and click-dead

Rendered-text parity proves APPEARANCE only. A port that copies markup and drops the handlers passes
every diff in the section above while doing nothing when clicked, and no screenshot or text comparison
will show it. Diff the interaction surface against the original before declaring a UI port done:

```sh
# handlers and state in the ORIGINAL vs the PORT — a port at 0 is a red flag
for d in <original-src> <port-src>; do
  printf '%s: onClick=%s useState=%s client-components=%s\n' "$d" \
    "$(grep -rho 'onClick'  $d | wc -l)" \
    "$(grep -rho 'useState' $d | wc -l)" \
    "$(grep -rl "^'use client'" $d | wc -l)"
done
```

Then classify every control in the ORIGINAL — not in the port — as worked or already dead, because
the two have opposite consequences. Check each button for a handler in the original source:

```sh
grep -n '<button' <original-page>.tsx | while IFS=: read -r n rest; do
  case "$rest" in *onClick*) echo "line $n HANDLED";; *) echo "line $n dead in the original";; esac
done
```

Handlers that already did nothing are parity and stay inert. Handlers that worked are a REGRESSION when
the port lacks them, and restoring them is in scope. Report the split with counts — "N handlers in the
original, 0 in the port, of which M were dead in the original too" — because it separates "the port is
faithful" from "the app feels broken", and it tells the human which dead controls are a missing feature
rather than a missing port. Never satisfy this check with a code-only claim: require a real click whose
before/after panel text is captured.

## An integrated page: cross-check the rendered text against the live payload

Once a page reads from an API, "it is wired" is verified by comparing the two directly — never by
reading the page component, which will look correct either way. Capture the rendered page text, fetch
every endpoint the page uses, and assert that everything the API returns appears on the page:

```py
# for each resource the page consumes:
#   names = [row['name'] for row in GET /api/<resource>]
#   assert every name is present in the captured page text; print present/total
```

Report it per resource as `N/N` — all team names, all captain names, all match names, every room name
and every message. A page rendering 3 of 30 rows, or silently dropping a relation it could not
hydrate, looks completely normal in a screenshot.

Then sweep the captured text for the artefacts of a broken binding, in every integrated page:

```sh
for f in <captured-page-texts>; do
  printf '%s: ' "$f"
  grep -oE 'undefined|null|NaN|\[object Object\]|Invalid Date' "$f" | sort | uniq -c
done
```

No misses and no artefacts IS the evidence; "the page looked right" is not.

## A write path is verified at the source of truth, then rolled back

For a control that WRITES — create, join, post, send, accept — the rendered page is the worst possible
oracle, because the component updates its own state optimistically and looks identical whether the
request persisted, 400'd, or never fired. Capture the baseline count, perform the action with a real
click, then assert it at the source of truth and clean up:

```sh
# 1. baseline BEFORE the click
curl -s localhost:<port>/api/<resource> | python3 -c "import sys,json;d=json.load(sys.stdin);print(len(d))"
# 2. click through the real UI (fill the form with the native setter so the framework sees the change,
#    submit via form button[type=submit] — a text filter can match the OPENER button instead)
# 3. assert the row exists and carries the fields you expect
curl -s localhost:<port>/api/<resource> | python3 -c "import sys,json;d=json.load(sys.stdin);print([r for r in d if r['name']=='<probe>'])"
# 4. DELETE the probe row and re-count, so the next verification starts from the same baseline
```

Assert the field that proves identity (the owner/captain/author id is the acting user, not just that a
row appeared) and quote the baseline→after counts. Roll back what you created: a verification that
leaves probe rows behind corrupts the next count and the human's demo. Rows you cannot delete (a
pre-existing FK-constrained DELETE) are a real defect to report, not a reason to skip the cleanup step.

**Roll back the exact rows and fields you touched — do not assume the seed can re-run.** Once your
verification created a row that REFERENCES a seeded one (a membership, a participant, a child record),
re-running a seed that restores by deleting and reinserting its own rows can fail on the foreign key,
so "just re-seed it" is not always an available restore. Undo precisely what you changed — delete the
membership/participant row you added, reset the status column you flipped, re-check the count — and
run the seed afterwards only to CONFIRM the fixture is still intact, not as the rollback itself.

Prefer this over trusting an agent's `201` log line, and require it of children too: "the request
returned 201" is a claim about the transport, while a re-read is a claim about the artefact.

## Running an integration suite against a live server on a task database

```sh
# the server's env must reach the test process too, from THE SAME database
set -a; . ./apps/api/.env; set +a
export DB_DATABASE=<task-db>                     # match the running server exactly
BASE_URL=http://localhost:<task-port> npx jest --config <cfg> --runInBand
```

A suite with any direct-to-database assertion will otherwise fall back to a config file, read a
different database, and fail a single test for no visible reason — easy to misread as a regression
in the change you just merged.

A SECOND suite added later often resolves a different variable, or hardcodes a stock port. Check every
spec reads the same base-URL env var before trusting a failure: a new spec that defaults to a
framework's usual port dies with a bare `ECONNREFUSED` while the server is running perfectly on the
task port, and that reads like a broken endpoint rather than a wrong target. Also note whether the
suite only READS or also WRITES — a writing suite leaves the shared fixture altered, so re-run the
seed afterwards and confirm the counts before anyone looks at the demo.

## Counts will disagree between passes — normalise the basis

Before calling two numbers a contradiction, check what each counted. Typical split: `@SubscribeMessage`
events only, versus events plus `onConnection`/`onDisconnect` lifecycle hooks. Report both bases
and the reconciled figure; do not present one as the other's correction.

## A fixture (seed) is verified by running it twice

A seed that is not idempotent silently doubles the dataset on the second run, and every later count
becomes unstable. Run it twice and compare per-table counts exhaustively — identical output is the
proof, and the same command is the evidence you quote:

```sh
psql -Atc 'select count(*) from <table>'   # per table, before and after each run
```

Then prove it is non-destructive to rows it did not create: run whatever else writes to that database
(an integration suite, a manual POST) so foreign rows exist, re-run the seed, and confirm the seeded
counts return to their fixed values while the foreign rows survive — e.g. 13 seeded users plus 2 left
by the suite staying at 15 after a re-run, not 30. Also confirm the API actually SERVES the fixture
(status line plus a row count per endpoint) before merging it: an endpoint that 500s on populated data
rows and 200s on an empty table passes every empty-database check and fails the moment a page uses it.
