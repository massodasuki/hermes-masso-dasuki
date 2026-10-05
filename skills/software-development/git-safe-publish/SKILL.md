---
name: git-safe-publish
description: Use when publishing a local tree to git without secrets.
---

# Publishing a local tree to git without leaking secrets

For trees that mix publishable content with live credentials and private state — an agent home
directory, `~/.config`, a dotfiles checkout. The deliverable is a repo containing exactly the
intended subset that stays safe as the tool keeps writing new files underneath it.

## 1. Map the tree before deciding what to publish

Enumerate the real credential stores first; do not assume `.env` is the only one. Then prove where
each secret actually lives — a key duplicated into a second file is the one that leaks.

- `ls -la` the root: modes are a signal (`-rw-------` / 0600 files are credentials or tokens)
- pattern-scan the tree for provider key shapes (OpenAI/Anthropic/Google/xAI/GitHub/Slack/Telegram
  bot tokens/JWTs/PEM headers) **and** for the literal value of every secret you already found
- search by a short prefix, never the full key, so the secret stays out of your command line and
  out of the tool output you read back
- expect false positives and read the surrounding context before calling something a leak: prose
  matches key regexes (`sk-concu…` out of the word "task-concurrency"), and documentation
  placeholders (`sk-xxx...xxxx`, `ghp_xx...xxxx`, `your-webhook-secret-here`) are examples, not
  credentials

`references/hermes-home-secret-map.md` lists what lives where in a Hermes home and the exact scan
recipe, so the mapping step is a lookup rather than a re-discovery.

## 2. Default-deny the ignore file

Ignore everything at the root, then opt the wanted subtree back in. New files the tool drops at the
root are then excluded automatically and you never maintain the list again:

    /*
    !/.gitignore
    !/README.md
    !/skills/

`/*` matches root-level entries only, so once `!/skills/` re-includes the directory, its contents
are not ignored. Start from `templates/hermes-home.gitignore`, which carries this head plus an
explicit belt-and-braces list of credential and private-state paths.

**Anchor every ignore path with a leading `/`.** A pattern containing no slash matches at every
level, so `hermes-agent/` also swallows `skills/<category>/hermes-agent/` and silently drops a real
skill from the commit; `/hermes-agent/` matches the root directory only. Watch for a staged file
count that is short by a suspiciously skill-shaped number, and re-check any directory name you
ignored globally that could also exist inside the subtree you are publishing.

The same default-deny reasoning applies to patterns *inside* the kept subtree: exclude by explicit
filename (`.usage.json`, `*.lock`) rather than by broad glob, and confirm afterwards that the only
things dropped under the subtree are runtime metadata and dotfiles.

## 3. Stage, then audit before committing

Never `git add -A && git commit` on a tree like this. Run all four checks every time:

    git diff --cached --name-only | awk -F/ '{print $1}' | sort | uniq -c      # top-level shape
    git diff --cached --name-only | wc -l                                      # count
    git diff --cached --name-only | grep -E '(^|/)(\.env|auth\.json|state\.db|…)'
    git diff --cached --name-only | xargs -d'\n' du -ch | tail -1              # staged size

Probe each critical path directly, so a passing grep is not the only evidence:

    for f in .env auth.json config.yaml state.db …; do
      printf '%-28s ' "$f"; git check-ignore -q "$f" && echo IGNORED || echo '*** NOT IGNORED ***'
    done

Then reconcile counts rather than eyeballing them: compare `git diff --cached --name-only | wc -l`
against the on-disk file total for the published subtree and account for every difference.
`git status --ignored --short -- <subtree>` lists what inside the kept subtree was excluded.

## 4. Get credentials without receiving them in chat

Treat existing auth as a precondition, not a blocker: check `gh --version`, `ssh -T git@github.com`,
`git config --global credential.helper`, `ls ~/.git-credentials`, and whether the host keeps a token
in its own env file. If none is configured, use GitHub's device flow and let the *user* authorise in
their browser — do not stop and ask them for a token.

- POST `https://github.com/login/device/code` with `client_id=178c6fc778ccc68e1d6a` (the public
  GitHub CLI client id) and `scope=repo`
- show the user `user_code` and `https://github.com/login/device`, in one message
- poll `https://github.com/login/oauth/access_token` with
  `grant_type=urn:ietf:params:oauth:grant-type:device_code`, honouring `interval` and adding 5s on
  `slow_down`; codes expire in ~15 minutes
- run the poll loop as a **background** process so the turn ends and the user can act while it waits
- on success write `~/.git-credentials` (mode 600) with the token, then
  `git config --global credential.helper store`, or pipe into `gh auth login --with-token`
- never echo the token; redact it from any output you print (`sed -E 's#https://[^@]*@#https://REDACTED@#g'`)

A device code is safe to display in chat: it authorises nothing without the user's own
authenticated browser session. A password or a personal access token is not — never ask for one in
chat; if the user has one, have them add it to the credential store themselves.

## 5. Verify the remote, then say what is exposed

Read the pushed tree back from the API instead of trusting the push output:

    curl -s https://api.github.com/repos/<owner>/<repo>/contents/

A freshly created empty repo has no default branch until the first push, so `git init -b main` and
push `main` explicitly. Report the commit sha, the file count, what was excluded, and the repo's
visibility. Flag publishable-but-personal content (absolute home paths, the user's own handles in
docs) and offer to flip a public repo to private or scrub it — do not leave the user to discover it.

Check the auth surface you left behind: a stored `~/.git-credentials` is plaintext, so tell the user
how to remove it (`rm ~/.git-credentials && git config --global --unset credential.helper`).
