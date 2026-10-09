# The completeness pass: making every control real

Use when the acceptance bar is "usable at UAT", "make it complete for each button", "every control
must work", or any request whose definition of done is behavioural rather than visual. A ported or
freshly-integrated app is the usual case: the screens match, and a large share of the controls do
nothing.

Skipping straight to "polish the pages" fails, because the real blocker is usually a missing endpoint,
not missing UI wiring. Do it in this order.

## 1. Inventory before you plan

Build a real list. A guessed list is how controls get missed.

- Walk the RUNNING app, not the source, and enumerate every `button`, `input`, `select`, `textarea` and
  `a[href]` per route.
- **Click every tab and every opener before dumping, then dump again.** A single first-pass DOM scan
  misses everything behind a tab and every field behind a form-opener (a `+ Create` button reveals a
  form that did not exist in the DOM a moment earlier). Re-scan after each reveal.
- Record per control: route, visible label, tag/type, `disabled` state, and whether it sits inside a
  form (a submit button needs its form's fields, not just the button, to be judged).
- Then read the ORIGINAL implementation to learn INTENT, and — critically — the exact option labels and
  storage keys. Guessing those costs you a rename later (see the vocabulary pitfall in the umbrella).
- Write the inventory to a checked-in matrix doc, one row per control. The wave briefs cite it, and the
  final verification walks the SAME list, which is what makes "complete" a falsifiable claim instead of
  a feeling.

## 2. Classify every control, then order the waves by the classification

| disposition | state | action |
|---|---|---|
| DONE | already real and verified | keep; re-verify after every merge |
| WIRE | the endpoint exists; the UI does not call it | UI wave |
| BUILD | no endpoint exists for it | BACKEND wave first, then WIRE |
| LABEL | cannot be real (no data source, no column, no route) | render honestly: disabled with a specific reason, or a redefined meaning that IS true |
| BLOCKED | deliberately not implemented (auth-model change, destructive op needing approval) | leave visibly disabled with the reason, and name it to the human |

Rules that fall out of the table:

- **Count the BUILD rows first.** If any exist, the next wave is backend and the UI wave follows it.
  A UI agent cannot finish a control whose endpoint is missing, and dispatching it anyway produces a
  plausible, non-functioning control. This is dependency ordering, not preference.
- **`LABEL` must never quietly become a fake.** "Disabled with the reason" is a pass. An invented filter,
  a fabricated attendee list, or a settings form still showing the original's mock person is a defect
  that survives review. Ported apps hide their mock data in the least-exercised screen — settings and
  profile pages are the usual hiding place, so grep the rendered page for the original's placeholder
  strings rather than trusting that the port wired them.
- **A derived meaning is fine when it is true and the UI says so.** "Hosted matches" redefined as "your
  team is the home side" is honest when there is no host column and the label says what it means.
- **Count controls the ORIGINAL never wired either.** A button that was dead before the port still
  counts: the bar is "does something", not "matches the original".
- **A destructive control (delete account, delete team) is implemented, not hidden** — behind an
  explicit confirmation — as long as the destructive step itself carries the human's approval. Where the
  fixture recreates the record, prove it works and then restore the fixture.

## 3. Off-limits by design, and how to say so

One or two controls will legitimately stay dead, usually because they need an auth-model change or a
human approval. Do not implement them to make the page look finished. Render them disabled with the
concrete reason, and tell the human explicitly which ones and why in the report — a visible, explained
hold reads as engineering judgement; a silently dead button is the original complaint.

## 4. Verification that actually closes the loop

- Re-run the inventory against the MERGED app and exercise every DONE and WIRE row.
- For each WRITE: click it, read the state back from the API AND the store, then reload and show the UI
  agrees. A screenshot, a code reading, or a 200 response alone is not evidence.
- For each NAVIGATION control: assert the pathname actually changed.
- For each TAB: capture the panel before and after.
- Confirm a reload does not lose what was saved (persisted state, not local state).
- Compare any filtered/counted view against the raw API response for that filter, at least twice.
- Report the BLOCKED and LABEL rows with their reasons and any gap you could not close. A visible gap is
  acceptable; a fabricated one is not.
