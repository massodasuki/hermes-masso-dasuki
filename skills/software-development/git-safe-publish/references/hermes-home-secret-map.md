# Where secrets and private state live in a Hermes home

Use when deciding what is safe to publish from `~/.hermes` (or a profile under
`~/.hermes/profiles/<name>/`). Classify first, publish second.

## Live credentials — never publish

| Path | What it is |
|---|---|
| `.env` (0600) | provider API keys (`*_API_KEY`), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` |
| `auth.json` (0600) | OAuth access/refresh tokens and `agent_key` for the portal providers, plus a credential-pool list (the pool entry for an API-key provider stores only a `secret_fingerprint`, not the key) |
| `shared/nous_auth.json` (0600) | the same access/refresh tokens, duplicated |
| `vault/` (0700) | saved website logins, cards, addresses |
| `pairing/`, `install_id`, `gateway.sock`, `gateway.lock`, `gateway.pid` | install identity and a live daemon socket |

## Private but not credentials — publish only deliberately

`sessions/` (request dumps, `sessions.json`), `state.db` + `state.db-journal`,
`shared-state.db`, `kanban.db`, `cron/` (including `executions.db` and `cron/output/`),
`logs/`, `memories/` (`MEMORY.md`, `USER.md`), `migration/` (archived workspaces and memory
overflow dumps), `workspace/`, `channel_directory.json`, `gateway_state.json`,
`runtime/active_sessions.json`, `terminal-sessions/`, `pending_messages/`, `images/`,
`image_cache/`, `audio_cache/`, `backups/`, `sandboxes/`, `cache/`.

`channel_directory.json` / `runtime/active_sessions.json` / `gateway_state.json` carry the user's
chat IDs and platform handles — small files, easy to overlook, personal.

## Usually publishable

`skills/` (mark `skills/.*` and lock files as runtime metadata), `SOUL.md`, and `config.yaml` —
`config.yaml` holds model/agent/gateway settings and normally no raw keys, but read every line
before trusting that, and treat it as private if the user prefers.

## Scan recipe

```bash
# structural: modes reveal credential files
ls -la ~/.hermes

# patterns: provider key shapes, bot tokens, JWTs, PEM headers
#   and content patterns: "<key>":"<value>" JSON fields, Bearer literals
python3 - <<'EOF'
import os, re
PATS = [
 ('openai', re.compile(r'sk-[A-Za-z0-9_\-]{20,}')),
 ('anthropic', re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}')),
 ('google', re.compile(r'AIza[0-9A-Za-z_\-]{30,}')),
 ('github', re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}')),
 ('slack', re.compile(r'xox[baprs]-[A-Za-z0-9\-]{10,}')),
 ('telegram_bot', re.compile(r'\b\d{8,12}:AA[A-Za-z0-9_\-]{30,}')),
 ('aws', re.compile(r'AKIA[0-9A-Z]{16}')),
 ('jwt', re.compile(r'eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.')),
 ('private_key', re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')),
 ('assign', re.compile(r'(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*["\']([A-Za-z0-9_\-\.]{20,})["\']')),
]
# walk the tree, record path -> {pattern: count}; print paths and counts, never the values
EOF

# values: does a known secret appear outside its own file? search a PREFIX only
KEY=$(grep -o 'DEEPSEEK_API_KEY=.*' .env | cut -d= -f2 | tr -d '"' | head -c 12)
grep -rl --binary-files=text "$KEY" . --exclude-dir=<vendored-checkout>
```

The value sweep is the part that catches a real problem, so always do it for every secret found in
step one — and use `--binary-files=text` so sqlite files and logs are searched too.

## Reading the results

A hit is not automatically a leak. Read the match context and classify:

- prose matching a key regex — a word boundary inside normal text (e.g. `sk-concu…` out of
  "task-concurrency-diagnosis") is a regex artefact
- documentation placeholders — `sk-xxx...xxxx`, `ghp_xx...xxxx`, `your-webhook-secret-here`,
  `Bearer sk-xxx...xxxx` in example configs
- emails inside doc examples and search-syntax references are expected in skill text

What you report to the user is the set of *live* secrets with their file paths and a masked prefix
(4-6 characters), never the value.
