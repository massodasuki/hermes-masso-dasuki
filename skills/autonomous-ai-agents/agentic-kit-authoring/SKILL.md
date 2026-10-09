---
name: agentic-kit-authoring
description: "Use when extracting or authoring an agentic dev starter kit."
version: 1.0.0
metadata:
  hermes:
    tags: [Boilerplate, Starter-Kit, Agent-Harness, Orchestration-Kit, Extraction]
    category: autonomous-ai-agents
    related_skills: [agent-team-orchestration, orchestrating-agent-teams]
---

# Agentic Kit Authoring

Packaging the harness an agent team runs on: turning a worked agentic project (AGENTS.md +
`.claude/agents/*` + `.agent/` protocol + task allocator) into a clean reusable starter, or
authoring and extending that harness itself. The kit is INSTRUCTIONS, not code — you edit
markdown and one bash script, and the deliverable is a folder a future session can dispatch
from without inheriting the original project's state.

## Procedure

### 1. Read the worked kit before packaging it
Read the whole harness first: AGENTS.md, the parallel protocol, every agent brief, the state
file, the allocator script. The state file records which brief sections were corrected in the
field (wrong package manager, wrong legacy path, allocator flags) — those corrections are the
most valuable content in the extraction, because they are the lessons the original project
paid for.

### 2. Copy into a NEW sibling folder; never modify the source
`mkdir` a sibling and `cp -r` the harness directories and root docs across. The source project
keeps its state, handoffs, branches and history untouched. "A new folder" means a new folder,
git-initialized — not a branch, not a subdirectory of the source repo.

### 3. Strip all per-project state
- `.agent/handoffs/*` — delete everything except `.gitkeep`
- `.agent/tasks/allocations.json` — reset to `{}` (in the allocator's own `json.dump` format,
  so a later allocation reads it cleanly)
- `.agent/STATE.md` — replace with a blank template (Goal / Current phase / Decisions /
  Environment gotchas / Done-with-evidence / Next steps / Blockers / Last updated)
- App trees, design docs, legacy docs the worked project accumulated — those are the project,
  not the kit

### 4. Genericize the SOP
- AGENTS.md § Project conventions becomes a FILL-IN template: package manager, layout, runtime
  versions, database + non-default port and user, exact gate commands, docs locations, gotchas,
  frozen-reference folder name. State plainly that updating this section when an agent gets
  something wrong IS its purpose.
- Rewrite the README for the boilerplate; keep `.gitignore` generic with the frozen-tree entry
  left as a commented placeholder, preserving the gitlink-reason comment.
- FIRST_PROMPT files: stack-agnostic, each pointing back at the conventions section.
- De-brand worked examples ("<project> example" → "measured example") so the lesson survives
  without the incident.

### 5. Fix the known stack hardcodes in the agent briefs
The recurring defect in any worked kit: a brief hardcodes the stack the original project ran
(a package manager command, an ORM, a framework port). The original project then carried that
as an override instruction in every dispatch. Encode the fix once, in the boilerplate: replace
the literal command with a pointer to the project-conventions section plus a rule to match the
repo's lockfile.

### 6. Smoke-test the harness's own machinery before handing it over
An allocator handed over unrun is a broken deliverable. Run the full cycle:
1. `git init`, initial commit of the kit.
2. Allocate one smoke task: worktree + branch + port block created, env block printed.
3. Probe-commit inside the worktree; verify the main checkout is untouched.
4. `--remove`, delete the probe branch explicitly (the allocator deliberately keeps branches),
   confirm `allocations.json` is back to `{}` and `git status` is clean.
5. Commit the allocator's own state-file format as a second commit.

### 7. Report the artifact with evidence
Deliverable = folder path, file inventory, what changed vs the source, and the smoke-test
output. The user expects the finished artifact plus verified commands, never a description of
the artifact.

## Pitfalls
- **Copying then rewriting files.** `write_file` refuses to overwrite a file this task has not
  loaded with `read_file` — and a `cp -r` into the target arms that guard for every copied
  file. For a file you intend to replace wholesale, `rm` it first and write fresh; for a
  partial change, `read_file` then `patch`.
- **Letting the smoke test touch the source project's infrastructure.** The allocator
  auto-detects a running database container; when the source project still has one up, it can
  create a task database inside it. Read the DB status token the allocator prints — "skipped
  (no container found)" is an honest pass; a "created" line against the source project's
  container is a side effect to undo before handing over.
- **Handing over the harness without running the allocator.** The smoke cycle above is the
  only proof the worktree / own-index / isolation claims are real in the new folder.
- **Shipping a state file with intentions.** The blank template stays blank — fill it only
  when the user starts a real project, never with example content.
- **Leaving the smoke branch behind.** The boilerplate's first branch list must be clean;
  delete the probe branch explicitly.

## Variant: a study guide of the kit
"Study the SOP / agent flow of this project" is the same class, documentation-only. Deliverable
is a guide at the PROJECT ROOT (never the agent workspace) covering: the pipeline state
machine, the team roles and where their briefs live, the handoff JSON contract, the
parallel/isolation protocol and allocator, the checkpoint protocol, the docs tree, the
verification culture, and the paid-for gotchas. Cite every file path so the guide doubles as
the recon list. The same session usually continues into the extraction procedure above — the
guide's file map is the extraction checklist.
