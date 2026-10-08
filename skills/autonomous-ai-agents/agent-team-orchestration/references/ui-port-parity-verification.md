# Verifying a UI port against a captured oracle

When a frontend is re-implemented on a new stack, "the screens are ported" is a claim about
*rendered* output. Verify it with the instrument that captured the oracle, or you will manufacture
differences that do not exist.

## Capture-instrument symmetry

The oracle (the frozen original's captured behaviour) and your verification must use the SAME
instrument. If the baseline was captured by reading `document.body.innerText` in a real browser, that
is what you re-read — not a regex over the served HTML.

Why the cheaper instrument lies: stripping tags out of HTML cannot see CSS, and it loses the node
boundaries that layout supplies.

- `text-transform: uppercase` is applied at paint time, so `innerText` yields `ACTIVITY TIME` while the
  markup holds `Activity Time`. A correct port then reports a difference on every styled label.
- Adjacent inline nodes get their separating space from layout, not from markup. Strip tags naively and
  `vs` + `Thunder` becomes `vsThunder`, `Futsal` + `8/10` becomes `Futsal8/10`, and a table cell reads
  `28 W84` where the oracle has `28W 84`.

Measured on one six-route port: ~30 phantom deltas per route from HTML-to-text, versus exact on all
six from the browser. When a cheap instrument disagrees with the capture instrument, the instrument is
wrong until proven otherwise.

## Procedure

1. Serve the BUILT app (production build, not the dev server) and wait for readiness on a real route.
2. Per route — and per captured tab state — navigate, let hydration settle (~1s), then read
   `js("document.body.innerText")` and write it to its own file named to match the oracle
   (`<route>.txt`, `<route>__<tab>.txt` for non-default tabs).
3. Line-diff the pair with trailing whitespace stripped: compare the line LISTS. A child's reported
   line count may be a couple off while the content identity holds — audit the diff, not the child's
   arithmetic.
4. Compare exact first, normalise whitespace only as a second pass. If normalising is what makes it
   pass, say so and keep the raw diff as the finding.
5. List every remaining difference explicitly. An unexplained difference is a failed port, not a
   rounding error.

## The port phase is parity, not improvement

The first implementation slice reproduces the original, defects included — a UI port's whole value is
that behaviour is unchanged while the stack is. Defects the oracle recorded (a tab that throws when
selected, a button that renders nothing) are reproduced as visible content and entered in the
behaviour-difference ledger; fixing them is a separate, human-approved change, and fixing them early
silently breaks the parity gate the task is about to be judged by.

Corollary: a port that renders only the default tab of a client-state tab set is not a regression.
The other tabs are interaction and belong to the interactivity slice — record the split rather than
adding `'use client'` to make a diff pass.

## Prove the negative claims too

"Zero integration" (a static port that calls no API) and "no client component" are the load-bearing
claims that keep a port reviewable, so prove them with an anchored grep, not a story:

```bash
grep -rn "^'use client'" <port-tree>                                    # the directive, anchored
grep -rnE "fetch\(|axios|socket\.io|XMLHttpRequest|EventSource" <port-tree>
```

The naive pattern matches the JSDoc prose a careful child writes ABOUT not integrating —
`RENDER MODEL: Server Component (no 'use client')`, `ZERO INTEGRATION: no fetch/axios/socket` — and
reads as a violation. Read the hits and classify them: a hit inside a comment is a pass, and only the
anchored directive form separates prose from code.

Confirm untouched-file claims by hash as well: when the brief said "do not restyle", the ported
stylesheet must be sha256-identical to the original's.
