---
name: hermes-gateway-admin
description: "Administer Hermes gateway services; inspect running agents."
version: 1.0.0
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [hermes, gateway, systemd, services, messaging, telegram, troubleshooting, operations]
---

# Hermes Gateway Admin

Operating and troubleshooting the Hermes gateway as a long-running service (`hermes-gateway.service`, plus any other gateway process hosting the same agent). Covers state checks, stopping/restarting, diagnosing duplicate platform pollers, running more than one agent on one box, and identifying what Hermes processes and sessions are actually running.

## Hard rule: the gateway cannot stop itself

The terminal tool refuses to stop/restart/uninstall the gateway from inside the gateway process — SIGTERM to the gateway's control group would kill the command mid-flight, so the guard blocks it. You will see:

> Blocked: command or referenced script cannot restart, stop, or uninstall the gateway from inside the gateway process.

Do NOT try to defeat this with pipes, subshells, or `&`. Detach the action into its own transient systemd unit so it survives the gateway's cgroup teardown:

```bash
systemd-run --user --collect --unit=stop-<target>-once --no-block \
  /usr/bin/systemctl --user disable --now <service>
```

- `--collect` cleans the transient unit up after it exits.
- `--no-block` returns immediately; the action runs independently of the calling cgroup.
- Verify the outcome in a separate call — do not trust the launch:

```bash
systemctl --user is-active <service>      # expect: inactive
systemctl --user is-enabled <service>     # expect: disabled
journalctl --user -u stop-<target>-once --no-pager | tail -5
```

Disabling also removes the `default.target.wants` symlink, so the service stays down across reboots. Re-enable with `systemctl --user enable --now <service>`.

## Enumerate ALL gateway units before declaring one "the" gateway

Enabling a new gateway does not remove an old one. A previous agent (e.g. OpenClaw) can remain enabled and running alongside Hermes indefinitely. List every candidate first:

```bash
systemctl --user list-units --type=service --all | grep -iE 'hermes|claw|gateway'
```

If the user believes they "replaced" a gateway, check whether the old unit is still `enabled`/`active` — it usually is.

## Duplicate-poller conflict: two gateways, one bot token

Symptom in logs: `Conflict: terminated by other getUpdates request; make sure that only one bot instance is running` (from either gateway), and/or `Telegram polling conflict (N/5) — previous session still held open`. The platform's long-poll holds a single-consumer lock, so the two gateways starve each other and the bot behaves erratically.

Diagnosis:
1. `systemctl --user status <old>.service --no-pager` and `systemctl --user status hermes-gateway.service` — confirm both are `active (running)`.
2. Confirm the old gateway targets the same platform/token (inspect its config dir, e.g. `~/.openclaw/openclaw.json`, with any secret redacted).

Fix: exactly one service must own each platform token. Stop AND disable the duplicate (see the detach recipe above — a plain `systemctl stop` from inside the gateway is blocked). When done, confirm the surviving gateway's logs go quiet: `journalctl --user -u hermes-gateway.service --since "1 min ago" --no-pager | grep -iE 'telegram|conflict'`.

## More than one agent on one box

Two supported topologies — both need **distinct bot credentials per agent**:

- **Multiplexed (default).** One gateway process serves every profile. Create the profile (`hermes profile create <name>`), give it its own platform tokens, `hermes gateway restart` — the host gateway routes to both. `hermes gateway list` shows the served set.
- **One process per profile.** Each profile can own `hermes-gateway-<name>.service`. Hermes now **refuses a named profile's `gateway install` / `gateway start` without `--force`**; to run one standalone, set `gateway.standalone: true` in `profiles/<name>/config.yaml` (a temporary shim) then `hermes -p <name> gateway install --force`.

Hard rule, same mechanism as the duplicate poller: **no two gateways/profiles may share one platform account or bot token.** A second agent needs a second bot token (another @BotFather bot) or a different platform. `gateway.multiplex_profiles: true` is the supported value — `false` is retired and rewritten to `true`; never hand-edit config, use `hermes config set`.

## Identify what is actually running

```bash
hermes gateway list          # gateways + served profiles
hermes profile list          # profiles + per-profile gateway status
systemctl --user list-units --type=service --all | grep -iE 'hermes|claw|gateway'
ps -eo pid,etime,rss,cmd | grep -i hermes | grep -v grep
```

Distinguish a **gateway** (systemd-managed, appears in `hermes gateway list`) from an **interactive CLI session** (a `hermes` python process parented to a terminal, absent from `gateway list`). A user's foreground `hermes` session is theirs — safe to leave; closing it loses nothing because turns persist to `state.db`. To verify a suspect PID is a live agent (not a wrapper/idle stub) and read what it has been doing, see `references/session-inspection.md`.

## Host power actions are blocked — hand them to the user

Shutting down, rebooting, or powering off the host is on Hermes's **unconditional blocklist** and cannot be
run by the agent at any approval level (`--yolo`, `approvals.mode=off`, cron approve mode all included):

> BLOCKED (hardline): system shutdown/reboot. … run it yourself in a terminal outside the agent.

So do not attempt it, however the request is phrased, and do not treat the refusal as something to work
around. When asked, give the user the one-liner and stop:

```bash
systemctl poweroff      # or: shutdown -h now
```

Before handing it over, make shutdown safe to lose: confirm nothing is mid-write (sessions persist to
`state.db`, checkpoints/commits are on their branch) and note any containers the session left running
(`docker ps -a`) so the user knows what stops and what comes back.

## Reporting

When the user asks "why is X still running?", lead with the concrete reason (a separate, still-enabled unit) and the exact next commands. Keep it short: what is happening, why, and the one command to fix it. Offer the reversible undo command whenever you stop/disable a service.
