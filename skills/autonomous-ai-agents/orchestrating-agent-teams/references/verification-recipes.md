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

Capture the oracle and verify it the SAME way. A different extraction method is a different
measurement, not a second opinion. Compare line-exact first, normalise whitespace only after, and
report the result as a line diff with counts.

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

## Counts will disagree between passes — normalise the basis

Before calling two numbers a contradiction, check what each counted. Typical split: `@SubscribeMessage`
events only, versus events plus `onConnection`/`onDisconnect` lifecycle hooks. Report both bases
and the reconciled figure; do not present one as the other's correction.
