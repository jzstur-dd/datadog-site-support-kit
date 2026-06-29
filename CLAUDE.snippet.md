# Verification Discipline — Absence-of-Evidence Gate

A failed search is **not** proof of absence. Before stating that something does
not exist — a doc page, a config key, an API endpoint, a feature, a file — you
must exhaust more than one retrieval path:

1. Try the obvious lookup (code search, a guessed URL, one query).
2. If it comes back empty, try the **authoritative** source through a **different
   path**: the live site / sitemap / search box, the actual repo config, an HTTP
   status check, or a web search — not a second variation of the same failed
   query.
3. Only after multiple independent paths fail do you report "does not exist," and
   you state what you checked.

A `200` from the live source beats any amount of "I couldn't find it." When a
human can find something with the site's search box that you missed with a code
search, that's this failure mode — engineer around it by checking the live source,
not by trusting the first empty result.

For Datadog government-site availability work specifically, use the
**site-support-auditor** skill: the `unsupported_sites` repo map is the source of
truth for *what's* unsupported, and the live docs sitemap + HTTP status is the
source of truth for *where the doc is*. Append `?site=gov` (US1-FED) or
`?site=gov2` (US2-FED) to every `docs.datadoghq.com` link.
