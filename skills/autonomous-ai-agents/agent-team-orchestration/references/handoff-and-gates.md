# Handoff JSON, coverage, question sheets, and the state file

## Handoff JSON — require this shape from every child

```json
{
  "agent": "reverse-engineer|architect|developer|qa",
  "task_id": "T-012",
  "status": "done | blocked | needs_clarification | failed",
  "summary": "what was done, <=5 lines",
  "artifacts": ["docs/design/T-012.md"],
  "evidence": ["pnpm test -> 42 passed"],
  "risks": ["..."],
  "next_recommended": "qa | developer | architect | human"
}
```

Validate it parses, confirm every path in `artifacts` exists, and treat `summary`/`risks` as claims
to be tested rather than facts. `next_recommended` is advice; the pipeline order and the human gates
decide routing.

## Coverage statement
Demand the enumerable form and the holes, every time:
- `48 of 48 HTTP routes, 13 of 13 socket handlers, 3 of 3 queue workers mapped`
- `0 schedulers exist` (a negative is a finding, state it)
- `Not analysed: <dirs skipped>, no build/DB/app executed`
A bare percentage is unverifiable and must be sent back.

## Question sheet for the human gate
One file, every decision, each entry carrying: id, the question in one sentence, why it matters for
the stated goal, evidence (`path:line`), options with the RECOMMENDED one first and a reason, the
cost of choosing wrong, and the owner. Group into BLOCKING / SCOPING / DEFERRABLE. End with a
fill-in answer sheet keyed by id.
- State plainly which ids block the next agent.
- A recommended default per question is what makes "follow the recommendations" a one-word answer.
- After the human answers, write the answers back into the sheet (id -> accepted option) instead of
  leaving the acceptance implied, and mirror them into the state file.

## State file sections that keep a fresh session productive
- Goal (the confirmed target, stated as a verb, with what is explicitly out of scope)
- Current phase / task id / branch / status
- Done, each item with the command output or handoff that proves it
- Next 3 steps
- Decisions made (with the ADR or answer-sheet reference)
- Deviations from the repo's own process docs — recorded, with reasons, not silently absorbed
- Open questions / blockers, with owner
- Known gotchas the next session would otherwise rediscover the hard way
- Last updated (author + what was completed)

Rule: the state file is the resume point. Anything a fresh session would need to know to avoid
re-doing or mis-doing work belongs in it, not only in the chat.

## Behaviour-difference ledger (migration / refactor work)

When tasks change behaviour that an earlier baseline pinned, the flips ARE the deliverable —
not a footnote to the summary. Keep one running ledger and carry it to the human gate as a batch:

- One line per flip, before -> after, stated concretely: a route that moved under a prefix, a status
  code that changed (a health endpoint that used to answer at `/` and now 404s there), a field removed
  from a response body, an endpoint that went from 500 to 200.
- **An endpoint that was broken and now works is still a behaviour difference.** A client may have
  worked around the break, so "it was a bug" does not exempt it from the ledger.
- Mark each entry deliberate (the intended fix) or consequential (a side effect of the mechanism), so
  the human approves the intent rather than discovering the side effects later.
- Anything a downstream client could reasonably depend on goes in the ledger even when the change is
  plainly an improvement.
- Get it approved at the gate and mirror it into the state file; a wave merged first and explained
  afterwards has already bypassed the gate.
- UI behaviour is included: a defect the port deliberately reproduces (or deliberately fixes) is a
  difference, and "reproduce or fix?" is a question for the human, not a call for the porter.
