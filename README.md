# Datadog Site-Support Auditor — for Claude Code

A plug-n-play Claude Code skill that answers **"what does Datadog *not* support on
the government sites — US1-FED (`?site=gov`) and US2-FED (`?site=gov2`) — and where
are the docs?"** with accurate, HTTP-verified public doc URLs.

It packages the exact method behind the unsupported-features report: pull the
authoritative gating map from the docs repo, resolve each feature's doc URL
against the live docs **sitemap**, and HTTP-verify on both sites. And it fixes the
one failure that bites everyone — an AI declaring "no doc page exists" off a single
failed search when the page is live (a human finds it instantly in the docs search
box). See [The Gate](#the-gate).

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/jzstur-dd/datadog-site-support-kit/main/install.sh | bash -s -- --global
```

That's the whole thing. Restart Claude Code and it's available in every project.
No pip install, no API keys, no clone — the installer fetches itself, and the
helper is stdlib-only Python that talks only to the **public** docs site and the
**public** docs repo.

Drop `--global` to install into the current project's `.claude/` instead. Prefer to
clone first? `git clone https://github.com/jzstur-dd/datadog-site-support-kit &&
./datadog-site-support-kit/install.sh --global`.

## Use it

In Claude Code:

```
/site-support list gov              → authoritative list of features unsupported on US1-FED
/site-support list gov2             → same for US2-FED
/site-support Storage Management    → the verified public doc URL (on gov + gov2)
```

Or just ask naturally — "build me a table of everything unsupported on US1-FED
with doc links" — and the skill triggers on its own.

The helper also runs standalone:

```bash
python3 .claude/skills/site-support-auditor/site_support.py list --site gov
python3 .claude/skills/site-support-auditor/site_support.py find "Application Security"
python3 .claude/skills/site-support-auditor/site_support.py verify "https://docs.datadoghq.com/infrastructure/storage_management/"
```

## What's in the box

| File | Role |
|---|---|
| `.claude/skills/site-support-auditor/SKILL.md` | the methodology — sources, workflow, the gate, output format |
| `.claude/skills/site-support-auditor/site_support.py` | stdlib helper: `list` (gating map) · `find` (sitemap doc-finder) · `verify` (HTTP on gov+gov2) |
| `.claude/commands/site-support.md` | the `/site-support` slash command |
| `CLAUDE.snippet.md` | the **absence-of-evidence gate** as a standing rule, injected into your `CLAUDE.md` |

## The Gate

The lesson that makes the output trustworthy: **a failed search is not proof of
absence.** The helper's `find` searches the live docs **sitemap** (the
deterministic equivalent of the docs search box) before ever concluding a page
doesn't exist, then HTTP-verifies. The skill forbids recording "no doc page" until
the sitemap, URL conventions, *and* a `site:docs.datadoghq.com` web search have all
failed. The install also drops this discipline into your `CLAUDE.md` so it applies
beyond this one skill.

> Real example it fixes: `Storage Management` was once marked "no standalone doc
> page." It was live at `/infrastructure/storage_management/?site=gov` the whole
> time — and it's right there in the sitemap. `find "Storage Management"` returns it
> in one shot.

## Notes

- **gov vs gov2 differ.** A feature unsupported on US1-FED may be fine on US2-FED
  (and vice-versa). `list` filters by the actual site membership in the repo map —
  don't infer one from the other.
- **TLS-friendly.** If your machine's cert store is broken (common with python.org
  builds on macOS), the helper falls back through `certifi` and finally an
  unverified context for these two public hosts, with a one-line warning. Nothing
  sensitive is ever sent.
- **Requirements:** `python3` (3.8+) and `bash`. Outbound HTTPS to
  `docs.datadoghq.com` and `raw.githubusercontent.com`.
