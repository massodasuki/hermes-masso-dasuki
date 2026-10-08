# Reverse-engineering passes and how to dispatch them

Order matters: each pass narrows what the next one can assume. Dispatch independent passes in
parallel; never dispatch a synthesis pass before its inputs exist.

## The passes
1. **Inventory** — languages, framework versions from the manifest, build/scripts, module layout,
   dependencies (flag deprecated/unmaintained), config and env var NAMES, deployment/CI, size, and a
   complete ENTRY POINT census (bootstrap, route registrations, gateways, workers, schedulers, frontend
   route table).
2. **Features & flows** — every entry point traced `route -> handler -> service -> data -> response`,
   grouped by business feature, with auth requirement, validation, and response shape per entry point.
3. **Data model** — entities/tables with columns, nullability, defaults, relations and owning side,
   unique/index/FK/ON DELETE behaviour, enum-ish columns, query patterns (flag missing pagination and
   N+1), migrations, and a Mermaid ER diagram. Diff any checked-in SQL dump against the ORM entities.
4. **Business rules** — each rule with where it lives, what it does, edge cases; plus explicit GAPs
   where the domain needs a rule the code does not enforce (cite the absence).
5. **Integrations** — every external interface with observed DIRECTION (producer/consumer/both/none),
   message format, and whether it is reachable in a running system.
6. **Security & state** — authN (token lifetime, payload, guards per route, handshake auth), authZ
   (which routes are actually guarded, ownership checks, mass-assignment), session/revocation, secrets
   hygiene (name files and variables, never values), validation surface, transport controls.
7. **Risks & debt** — prioritised register: dead code, duplication, coupling, untested areas,
   hard-to-change parts, schema drift, missing operational tooling. Evidence + impact/likelihood
   labelled as JUDGEMENT.
8. **Backlog** — ordered slices with dependencies and the behaviour that must be preserved, not an
   implementation plan. For a migration, old and new run side by side and rollback is `switch back`.
9. **Open questions** — consolidate every question raised by passes 1-7 into ONE decision document
   for the human: id, one-sentence question, why it matters for the stated goal, the evidence that
   raises it, options with a recommended default, the cost of choosing wrong, and the owner. Group
   into blocking / scoping / deferrable, and end with a fill-in answer sheet.

Plus a repo map maintained alongside: folder -> purpose, key entry points, conventions.

## Dispatch rounds
- Round A: passes 1-2 in parallel. Round B: passes 3, 4+5, 6+7 in parallel (three children).
  Round C: 8 and 9 in parallel. Each child owns disjoint files.
- Keep the pairings above: 4+5 and 6+7 pair naturally (one child, two files) and keep the round to
  three children instead of seven.
- The synthesis round (8, 9) must receive the earlier handoff JSONs — they are compact and dense, so
  a child can orient from them instead of re-reading every doc.

## Evidence contract that makes the docs usable
- Every claim ends with `path/File.ext:LINE`.
- Anything not proven by execution is marked `UNVERIFIED`, with the reason (no build, no run, no DB).
- OBSERVED BEHAVIOUR and INTERPRETATION are labelled separately, so the reader knows which is proof.
- Business intent is never invented: unclear rationale becomes an open question.
- Coverage is stated as `X of Y` plus an explicit list of what was skipped and what was not analysed.

## Preserved-behaviour framing for migrations
Before changing anything, the existing system is the oracle: each slice needs characterization tests
written against the CURRENT behaviour first, then the change, then the same checks re-run. Make that
an explicit task in each slice rather than an afterthought.
