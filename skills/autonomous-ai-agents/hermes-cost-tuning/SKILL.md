---
name: hermes-cost-tuning
description: Use when a run costs too much or needs a cheaper model.
---

# Cutting the cost of a Hermes run

Hermes bills per model call, so a long agentic session or a batch over many items costs real money.
Work in this order: measure, find the dominant line, then change the cheapest lever that moves it.

## 1. Measure before optimising

- `hermes insights` — token totals and spend per model for the recent window, so you can see whether
the cost is one runaway session or a standing pattern. It also reveals which models are already in
use.
- `hermes usage` — quota/limit windows for the current credentials.
- `state.db`, table `session_model_usage` — the real per-session breakdown, one row per auxiliary
task (`main`, `vision`, `approval`, `background_review`, `title_generation`) with call counts,
input/output/cache-read tokens and `estimated_cost_usd`:

```sql
select model, billing_provider, task, api_call_count, input_tokens, output_tokens,
       cache_read_tokens, estimated_cost_usd
  from session_model_usage where session_id = ? order by first_seen;
```

Prices come from `models_dev_cache.json` and the rows carry `cost_source=official_docs_snapshot`
with `actual_cost_usd=null`. These are estimates — say so, and give the basis, rather than quoting a
precise-sounding figure as billed fact.

## 2. Find the dominant line

For an agentic run the order is usually: **output tokens** (priced several times input) > fresh input
> cache reads. Images are negligible — a few hundred tokens per call. So the levers rank: output
price, output volume, then not re-sending context.

Calibration from a measured batch: a ~55-folder job on a low-cost paid model came to roughly $0.60 in
total, split output ~46%, fresh input ~35%, cache reads ~19%. Halving output volume was the single
largest saving available in that run.

## 3. The levers

1. `agent.reasoning_effort: low` — on a `medium` setting, reasoning was half of all output tokens.
2. **Your own verbosity.** Status prose is billed output. On a batch run, report status only.
3. **Route auxiliary traffic**: `auxiliary.<task>.provider` / `.model` / `.max_input_tokens` for
   `vision`, `background_review`, `approval`, `title_generation`. A cheaper model there is pure
   saving, and `max_input_tokens` stops a post-turn review re-reading an entire session.
4. `auxiliary.free_only: true` — keeps auxiliary traffic off paid lanes.
5. **Frequency of background forks**: `memory.nudge_interval` and
   `agent.skills.creation_nudge_interval` (the `agent` section, not top level) decide how often they
   fire.
6. **Command shape.** Heredocs and inline `python3 -c` are flagged and go through the approval
   classifier — worth ~20-30 extra model calls in a session. Write the script to a file and run the
   file.
7. **Batch size.** Keep work in batches of ~8-10 items so context stays under the compression
   threshold; every compression trip adds a summarisation call.
8. **Images are not the lever.** Do not thin out frames or samples to save money — measure first.

## 4. Do not economise on safety

Leave `auxiliary.approval` on a strong model: it decides whether a flagged command auto-approves, so
a weak model there is a security regression, not a saving. Treat anything that writes memory or
skills the same way unless the user has said quality does not matter there.

## 5. Verify the routing actually took effect

- `hermes config get <key>` for every change.
- Confirm on real traffic, not on config: the task's rows in `session_model_usage` must switch
  model/provider, and read `$0.000000` when the backend is free. A config value is a claim; the
  usage row is the evidence.
- **The CLI warns "not a recognized config key" for keys it does not know about — including keys
  Hermes itself reads.** Check `config_defaults.py` or the module that consumes the key before
  abandoning it, and remember keys read from the `agent` section must be written as
  `agent.<sub>.<key>`.

## 6. Free and cheap tiers come with strings

- **A listed model is not necessarily a callable model.** Send one real request before planning a
  run around it; an account without credit refuses paid models outright, and free tiers return
  capacity 429s.
- Free/preview models are rate-limited, slower (tens of seconds per call, worse under load) and can
  disappear mid-run. Validate on one or two items, keep the paid model as the fallback for the hard
  ones, and read a slow tail as saturation rather than failure.
- Giving the vision half of an image-heavy batch its own cheap model is the cleanest win: every
  image call becomes free while the main model keeps its quality for reasoning.

## 7. Report the trade-off, not just the number

Give the measured split and its basis, the before/after per change, and one line on what the saving
costs (latency, rate-limit risk, weaker output). A job costing well under a dollar often does not
justify a free setup that risks wrong output — state that and let the user decide.
