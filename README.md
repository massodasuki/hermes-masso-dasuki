# hermes-masso-dasuki

My [Hermes Agent](https://github.com/NousResearch/hermes-agent) **skills directory**, published on its own.

This repo is the contents of `~/.hermes/skills/` — the reusable procedures my agent loads on
demand: how to triage an inbox, drive a browser, find a product on Shopee, author a document, and
so on. Each skill is a folder with a `SKILL.md` (YAML frontmatter + instructions) plus optional
`references/`, `scripts/`, `templates/` and `assets/`.

## Layout

    <category>/<skill-name>/SKILL.md
    <category>/<skill-name>/references/*.md
    <category>/<skill-name>/scripts/*
    <category>/<skill-name>/templates/*

## What is NOT here

Nothing else from `~/.hermes` is tracked. The repo uses a default-deny `.gitignore`, so
`config.yaml`, `.env`, `auth.json`, session history, logs, databases, memories and the credential
vault can never be committed by accident.

## Using a skill

Drop a folder into your own `~/.hermes/skills/<category>/` and it is picked up on the next
session. Read the skill's `SKILL.md` — the frontmatter `description` is what the agent matches
tasks against, and the body is the procedure.
