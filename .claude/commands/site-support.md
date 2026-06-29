---
description: Audit Datadog feature availability on US1-FED / US2-FED with verified doc links
argument-hint: <feature name, or "list gov" / "list gov2">
allowed-tools: Bash(python3:*), WebSearch, WebFetch
---
Use the **site-support-auditor** skill to answer this Datadog government-site
availability question, with verified public doc URLs.

Request: $ARGUMENTS

Run the helper at `.claude/skills/site-support-auditor/site_support.py`:
- "list gov" / "list gov2" → `list --site gov|gov2` (authoritative unsupported set)
- a feature name → `find "<feature>"` (resolve + HTTP-verify the doc URL)
- a URL → `verify "<url>"`

Honor THE GATE from the skill: never report "no doc page" until the sitemap
search, URL conventions, AND a `site:docs.datadoghq.com` WebSearch have all
failed. Append `?site=gov` (US1-FED) or `?site=gov2` (US2-FED) to every doc link
in the output, and collapse product variants to one row.
