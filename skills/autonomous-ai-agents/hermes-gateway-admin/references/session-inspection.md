# Inspecting a running Hermes session

How to prove a suspect PID is a live agent (not a wrapper, stub, or dead process) and read what it has
been doing. Used when the user asks "what is that other `hermes` process?", "what is it doing?", or "are
there other agents running?".

Path assumed below is `$HERMES_HOME/state.db` (default `~/.hermes/state.db`); resolve the real home from
`$HERMES_HOME`, never hardcode it.

## 1. Classify the process: gateway vs interactive CLI vs subagent

```bash
ps -eo pid,etime,rss,cmd | grep -i hermes | grep -v grep
hermes gateway list      # only gateways appear here
```

A process absent from `hermes gateway list` but running `.../hermes-agent/hermes` is an **interactive CLI
session** (parented to a terminal), not a gateway. It is the user's own — safe to leave; closing it loses
nothing because turns persist to `state.db`.

## 2. Verify it is a live agent

`ps -o pid,stat,etime,pcpu,pmem,rss,cmd -p <pid>` — read the STAT column:

- `Sl+` / `S+` — sleeping/idle and in the **foreground process group** of its controlling terminal
  (the `+` means an interactive session waiting at the prompt). This is what an idle, healthy session
  looks like.
- Non-zero `%CPU` averaged over a long `etime` means it has done real work, not just parked.

Then read `/proc/<pid>/` for the ground truth a wrapper or stub cannot fake:

```bash
ls -l /proc/<pid>/cwd                                   # working directory = the project it operates on
tr '\0' '\n' < /proc/<pid>/environ | grep -iE 'HERMES_HOME|HERMES_SESSION|HERMES_PROFILE|^TERM='
ls -l /proc/<pid>/fd | grep -iE 'state.db|agent.log|errors.log|sessions|.jsonl'
pgrep -aP <pid>                                          # children = a tool call in flight; none = idle
```

Open fds on `state.db` and `agent.log`/`errors.log` confirm it is a real agent with the session store
attached. Live children mean it is mid-turn; no children means it is waiting for input.

To walk up to the terminal that owns it:

```bash
P=<pid>; for i in 1 2 3 4; do ps -o pid,ppid,cmd -p $P | tail -1; P=$(ps -o ppid= -p $P | tr -d ' '); [ -z "$P" ] && break; done
```

## 3. Read what it has been doing, from state.db

Query it **read-only** so the live gateway's writes are never touched. The `sqlite3` CLI is often absent —
use Python's stdlib instead:

```python
import sqlite3, datetime
con = sqlite3.connect("file:/home/masso/.hermes/state.db?mode=ro", uri=True)
con.row_factory = sqlite3.Row
```

Key tables: `sessions` and `messages`. Useful `sessions` columns: `id, source, cwd, title, model,
profile_name, message_count, tool_call_count, api_call_count, input_tokens, output_tokens, started_at,
last_activity_at, archived`. `source` distinguishes `cli` / `subagent` / gateway sessions — subagent rows
are the fan-out children of a delegation.

Find the session behind a PID by matching **cwd** (from `/proc/<pid>/cwd`) and start time:

```python
cur = con.execute("""SELECT id, source, cwd, title, message_count, tool_call_count,
                            started_at, last_activity_at, model, profile_name
                     FROM sessions WHERE cwd LIKE ?
                     ORDER BY last_activity_at DESC LIMIT 20""", ("%<project-dir>%",))
```

The session whose `started_at` matches the process start is the interactive one; the `source=subagent`
rows beside it are the tasks it dispatched.

Read the tail of a session:

```python
for m in con.execute("SELECT role, tool_name, content, timestamp FROM messages
                      WHERE session_id=? ORDER BY timestamp DESC LIMIT 15", (sid,)):
    print(ts(m["timestamp"]), m["role"], m["tool_name"], (m["content"] or "")[:200])
```

`timestamps` are epoch floats — convert with the user's timezone, e.g.
`datetime.datetime.fromtimestamp(x, datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")`.
Reading the `role='user'` rows in order gives the human's actual instructions and corrections — the best
summary of intent.

## 4. Confirm real side effects

A session's own summary is a self-report. Confirm with external evidence before repeating it:

```bash
git -C <cwd> log --oneline -15 --pretty='%h %ad %s' --date=short
# or the project's checkpoint file, e.g. .agent/STATE.md
docker ps -a          # containers the run started and left up
```

If the process wrote no commits and started no containers, say so plainly rather than paraphrasing its
closing message as fact.

## Pitfalls

- Do not treat "no children" as "dead" — an idle interactive session is healthy; check STAT and fds too.
- Do not open `state.db` read-write while the gateway is running; always `?mode=ro`.
- Do not report a session's activity purely from its own final message; verify with git/containers.
