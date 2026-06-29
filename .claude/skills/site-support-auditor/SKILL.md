---
name: site-support-auditor
description: >
  Audit Datadog feature/product availability on Datadog for Government sites --
  US1-FED (?site=gov) and US2-FED (?site=gov2) -- and produce an accurate table or
  CSV of unsupported features with VERIFIED public doc URLs. Use when asked "is X
  supported on US1-FED / US2-FED / GovCloud / gov / gov2", "what's unsupported on
  GovCloud", "feature availability on the gov site", "build a list of unsupported
  products", or to find/confirm the public doc URL for any Datadog feature.
---

# Site-Support Auditor

Produce a trustworthy answer to "what does Datadog NOT support on the government
sites, and where are the docs?" The method is mostly deterministic: pull the
authoritative gating map from the docs repo, resolve each feature's public doc
URL against the live docs site, and HTTP-verify. The hard-won lesson baked in
here: **never declare a doc page absent from a single failed search** (see The
Gate). A helper script does the mechanical parts; you handle judgment.

Helper (stdlib Python, no install, talks only to public docs + the public docs
repo): `.claude/skills/site-support-auditor/site_support.py`

## Sources, in authority order

1. **The gating map (ground truth for *what* is unsupported)** —
   `unsupported_sites` in `DataDog/documentation` →
   `config/_default/params.yaml`. Keys are `site_support_id`s; each maps to the
   list of sites where the feature is gated off. `gov` = US1-FED, `gov2` =
   US2-FED. The helper reads this live.
2. **The live docs sitemap (ground truth for *where* the doc is)** —
   `https://docs.datadoghq.com/sitemap.xml` (a gzipped sitemap index → `/en/`
   child). Searching it is the deterministic equivalent of using the docs search
   box, which is how a human finds pages an AI's code-search misses.
3. **Live HTTP status** — a page is real on a site iff `<url>?site=gov` (or
   `?site=gov2`) returns `200`.
4. **WebSearch** (`site:docs.datadoghq.com "<feature>"`) — last-resort discovery
   before you conclude a page does not exist.

## Workflow

### Step 1 — Pull the authoritative unsupported set
```bash
python3 .claude/skills/site-support-auditor/site_support.py list --site gov     # US1-FED
python3 .claude/skills/site-support-auditor/site_support.py list --site gov2    # US2-FED
```
This is the spine of the report. Do **not** hand-curate the list from memory or
from scraping banners — the map is the source of truth and it changes.

> gov vs gov2 nuance: a feature is unsupported on US1-FED only if `gov` is in its
> site list, and on US2-FED only if `gov2` is. Some keys are gated off *commercial*
> sites but fine on gov (e.g. a key listing `[us,us3,us5,eu,ap1,ap2]` is supported
> on gov/gov2). The `list` command already filters correctly — trust it, don't
> include a key just because it appears in the map.

### Step 2 — Resolve each feature's public doc URL
For every key, get the doc URL:
```bash
python3 .claude/skills/site-support-auditor/site_support.py find "storage_management"
python3 .claude/skills/site-support-auditor/site_support.py find "Application Security"
```
`find` searches the live sitemap first (deterministic), then falls back to URL
conventions, then HTTP-verifies the winner on both gov and gov2. It returns the
canonical product page (deprioritizing `/api/` and `/getting_started/` pages) plus
other real candidates. When several real pages exist, you pick the canonical
product doc — the script surfaces the options.

### Step 3 — THE GATE (read this twice)
**A failed search is not proof of absence.** The signature failure of this task is
an AI concluding "no doc page exists" because one code-search or one guessed URL
returned nothing — when the page was live and a human found it in seconds via the
docs search box. (Real case: `Storage Management` was marked "no standalone doc
page"; it was live at `/infrastructure/storage_management/?site=gov` the whole
time, and it's right there in the sitemap.)

Before you record **any** feature as "no public doc page", ALL of the following
must have failed:
1. `site_support.py find "<feature>"` (sitemap search + URL conventions) returns
   NOT FOUND, **and**
2. you tried the obvious display-name and snake/kebab slug variants, **and**
3. a `WebSearch` for `site:docs.datadoghq.com "<feature>"` returns nothing
   relevant.

Only after 1–3 do you write "no standalone public doc page (in-app / preview /
API-only)" — and say which of those it is. If `find` returns a URL, you are done;
do not second-guess a `200`.

### Step 4 — Preview / partial nuance
Some entries are GovPreview (early access, not GA) or partially supported. Don't
flatten these to "unsupported." If a feature is in preview on gov, label it
"GovPreview / not GA" rather than absent. If only part of a product is gated, say
which part.

### Step 5 — Verify a sample before shipping
Spot-check that your final URLs resolve:
```bash
python3 .claude/skills/site-support-auditor/site_support.py verify "<url>"
```
Every URL in customer- or manager-facing output must be a confirmed `200` on the
relevant site. Append `?site=gov` (US1-FED) or `?site=gov2` (US2-FED) to every
`docs.datadoghq.com` link in the final artifact.

### Step 6 — Output
Default to a two-column table (or CSV on request):

| Product / Feature | Public Doc URL |
|---|---|
| Storage Management | https://docs.datadoghq.com/infrastructure/storage_management/?site=gov |

Rules: collapse variants of the same product to one row (the map has both
`agentless-scanning` (api) and `agentless_scanning` (docs) — one product). State
the row count. Note any preview/partial/API-only entries explicitly. If asked for
both sites, add a column or produce two tables (gov, gov2) — they differ.

## Quick reference
```bash
site_support.py list   --site gov|gov2 [--json]   # authoritative unsupported set
site_support.py find   "<feature>"     [--json]   # resolve + verify the doc URL
site_support.py verify "<url>"         [--json]   # HTTP 200 check on gov + gov2
```

## Why this beats eyeballing it
- The unsupported set comes from the **repo config**, not from clicking around or
  trusting recall — it's complete and current.
- Doc URLs are resolved against the **live sitemap + HTTP status**, so "no doc"
  verdicts are earned, not assumed. That single discipline is what made the
  difference on the original task.
