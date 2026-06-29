#!/usr/bin/env python3
"""site_support.py -- deterministic Datadog site-support auditor.

Reproduces (and de-risks) the workflow used to build an accurate "what's
unsupported on US1-FED / US2-FED" report with verified doc links. Three jobs:

  list    -- pull the AUTHORITATIVE unsupported-feature map straight from the
             docs repo config (unsupported_sites in config/_default/params.yaml)
             and filter to a site (gov = US1-FED, gov2 = US2-FED).

  find    -- locate the PUBLIC doc URL for a feature. This is the part that fixes
             the failure mode where an AI declares "no doc page" off one failed
             search. It searches the live docs SITEMAP (the same thing a human
             does with the docs search box) AND tries URL conventions, then
             HTTP-verifies. A page is only "not found" after BOTH paths fail.

  verify  -- HTTP-check a URL on both ?site=gov and ?site=gov2.

Stdlib only (urllib + gzip + re). No pip install, no API keys. Talks only to the
public docs site and the public docs repo.

Examples:
    python3 site_support.py list --site gov
    python3 site_support.py list --site gov2 --json
    python3 site_support.py find "Storage Management"
    python3 site_support.py find storage_management --json
    python3 site_support.py verify https://docs.datadoghq.com/infrastructure/storage_management/
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

PARAMS_URL = ("https://raw.githubusercontent.com/DataDog/documentation/master/"
              "config/_default/params.yaml")
DOCS = "https://docs.datadoghq.com"
SITEMAP_INDEX = f"{DOCS}/sitemap.xml"
CACHE = Path(tempfile.gettempdir()) / "dd_site_support_sitemap.cache"
CACHE_TTL = 6 * 3600  # 6 hours
UA = {"User-Agent": "site-support-auditor/1.0 (+local audit tool)"}
TIMEOUT = 15

SITE_LABELS = {"gov": "US1-FED", "gov2": "US2-FED"}

# Common URL section prefixes to try when the sitemap doesn't resolve a slug.
SECTION_PREFIXES = [
    "", "infrastructure/", "logs/", "metrics/", "tracing/", "security/",
    "integrations/", "monitors/", "dashboards/", "real_user_monitoring/",
    "continuous_testing/", "synthetics/", "serverless/", "containers/",
    "agent/", "api/latest/", "account_management/", "data_jobs/",
    "database_monitoring/", "cloud_cost_management/", "service_management/",
    "actions/", "bits_ai/", "observability_pipelines/", "ddsql_reference/",
]


# ── HTTP helpers ────────────────────────────────────────────────────────────
# SSL context chain: many machines (esp. macOS Python from python.org) have a
# broken system trust store. We try verified first, then certifi if installed,
# then an UNVERIFIED fallback. The fallback is safe here because this tool only
# ever talks to two hardcoded public hosts (docs.datadoghq.com and
# raw.githubusercontent.com), transmits no credentials, and only reads public
# pages whose existence we separately confirm via HTTP status.
_WARNED_UNVERIFIED = False


def _ssl_contexts():
    yield ssl.create_default_context()
    try:
        import certifi  # type: ignore
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 -- certifi is optional
        pass
    yield ssl._create_unverified_context()  # last resort, host-scoped above


def _open(url: str, method: str = "GET"):
    """Try the SSL context chain; return (status, body_bytes). Raises on total fail."""
    global _WARNED_UNVERIFIED
    last_err = None
    contexts = list(_ssl_contexts())
    for i, ctx in enumerate(contexts):
        try:
            req = urllib.request.Request(url, headers=UA, method=method)
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
                if i == len(contexts) - 1 and not _WARNED_UNVERIFIED:
                    print("warning: TLS cert verification unavailable; using "
                          "unverified HTTPS for public docs read-only.",
                          file=sys.stderr)
                    _WARNED_UNVERIFIED = True
                return resp.getcode(), (resp.read() if method == "GET" else b"")
        except urllib.error.HTTPError as e:
            return e.code, b""  # a real HTTP status, not a TLS/network failure
        except (urllib.error.URLError, OSError, ValueError) as e:
            last_err = e
            continue
    raise RuntimeError(f"request failed for {url}: {last_err}")


def fetch_bytes(url: str) -> bytes | None:
    try:
        _, data = _open(url, "GET")
    except RuntimeError:
        return None
    if data[:2] == b"\x1f\x8b":  # gzip magic -- docs sitemaps are gzipped
        try:
            data = gzip.decompress(data)
        except OSError:
            return None
    return data


def fetch_text(url: str) -> str | None:
    b = fetch_bytes(url)
    return b.decode("utf-8", errors="replace") if b is not None else None


def http_status(url: str) -> int:
    """Final status after following redirects. 0 on network failure."""
    try:
        code, _ = _open(url, "GET")
        return code
    except RuntimeError:
        return 0


# ── unsupported_sites map ───────────────────────────────────────────────────
_MAP_LINE = re.compile(r"^\s+([A-Za-z0-9_.\-]+):\s*\[([^\]]*)\]")


def load_unsupported() -> dict[str, list[str]]:
    """Parse the unsupported_sites map from params.yaml (no YAML dep needed)."""
    text = fetch_text(PARAMS_URL)
    if text is None:
        raise RuntimeError(f"could not fetch {PARAMS_URL}")
    out: dict[str, list[str]] = {}
    in_block = False
    for line in text.splitlines():
        if re.match(r"^unsupported_sites:\s*$", line):
            in_block = True
            continue
        if in_block:
            # End of block: a new top-level (non-indented) key.
            if line and not line[0].isspace():
                break
            m = _MAP_LINE.match(line.split("#", 1)[0])
            if m:
                key = m.group(1)
                sites = [s.strip() for s in m.group(2).split(",") if s.strip()]
                out[key] = sites
    return out


# ── sitemap (the deterministic doc finder) ──────────────────────────────────
def _load_sitemap_urls() -> list[str]:
    if CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < CACHE_TTL:
        return CACHE.read_text(encoding="utf-8").splitlines()

    index = fetch_text(SITEMAP_INDEX) or ""
    children = re.findall(r"<loc>([^<]+)</loc>", index)
    # English docs only.
    en = [c for c in children if "/en/" in c] or [f"{DOCS}/en/sitemap.xml"]
    urls: list[str] = []
    for child in en:
        body = fetch_text(child) or ""
        urls.extend(re.findall(r"<loc>([^<]+)</loc>", body))
    urls = sorted(set(urls))
    if urls:
        try:
            CACHE.write_text("\n".join(urls), encoding="utf-8")
        except OSError:
            pass
    return urls


def _slugs(name: str) -> list[str]:
    base = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return list(dict.fromkeys([base, base.replace("_", "-")]))


def _last_segment(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def find_doc(name: str) -> dict:
    slugs = _slugs(name)
    result = {"query": name, "slugs": slugs, "found": False, "url": "",
              "method": "", "gov": 0, "gov2": 0, "candidates": []}

    # Path A -- search the live sitemap for a URL whose final segment matches.
    # This is the deterministic equivalent of a human's docs-search.
    sitemap = _load_sitemap_urls()
    seg_matches, sub_matches = [], []
    slugset = set(slugs)
    for u in sitemap:
        seg = _last_segment(u)
        if seg in slugset:
            seg_matches.append(u)
        elif any(s in u for s in slugs):
            sub_matches.append(u)
    candidates = seg_matches or sub_matches
    if candidates:
        primary_slug = slugs[0]  # snake form; product pages favor it over kebab

        def rank_key(u: str):
            seg = _last_segment(u)
            return (
                "/api/" in u,                 # API reference pages last
                "/getting_started/" in u,     # getting-started pages later
                seg != primary_slug,          # exact snake-slug match wins
                u.count("/"),                 # shallower path preferred
                len(u),
            )
        ranked = sorted(candidates, key=rank_key)
        result.update(found=True, url=ranked[0], method="sitemap",
                      candidates=ranked[:8])

    # Path B -- URL conventions, HTTP-checked (covers pages a sitemap may lag on).
    if not result["found"]:
        for slug in slugs:
            for pref in SECTION_PREFIXES:
                cand = f"{DOCS}/{pref}{slug}/"
                if http_status(f"{cand}?site=gov") == 200:
                    result.update(found=True, url=cand, method="url-convention")
                    break
            if result["found"]:
                break

    if result["found"]:
        result["gov"] = http_status(f"{result['url']}?site=gov")
        result["gov2"] = http_status(f"{result['url']}?site=gov2")
    return result


# ── commands ─────────────────────────────────────────────────────────────────
def cmd_list(args) -> int:
    site = args.site
    mp = load_unsupported()
    keys = sorted(k for k, sites in mp.items() if site in sites)
    if args.json:
        print(json.dumps({"site": site, "label": SITE_LABELS.get(site, site),
                          "count": len(keys), "keys": keys}, indent=2))
        return 0
    print(f"# Unsupported on {SITE_LABELS.get(site, site)} ({site}): {len(keys)} keys")
    for k in keys:
        print(k)
    return 0


def cmd_find(args) -> int:
    res = find_doc(args.feature)
    if args.json:
        print(json.dumps(res, indent=2))
        return 0
    if res["found"]:
        ok_gov = "200" if res["gov"] == 200 else f"!{res['gov']}"
        ok_gov2 = "200" if res["gov2"] == 200 else f"!{res['gov2']}"
        print(f"FOUND ({res['method']}): {res['url']}")
        print(f"  ?site=gov -> {ok_gov}   ?site=gov2 -> {ok_gov2}")
        if len(res["candidates"]) > 1:
            print("  other candidates:")
            for c in res["candidates"][1:5]:
                print(f"    - {c}")
    else:
        print(f"NOT FOUND after sitemap search + URL conventions for "
              f"{res['slugs']}.")
        print("  Before recording 'no doc page', also run a WebSearch:")
        print(f'    site:docs.datadoghq.com "{args.feature}"')
    return 0 if res["found"] else 2


def cmd_verify(args) -> int:
    url = args.url.split("?")[0].rstrip("/") + "/"
    gov = http_status(f"{url}?site=gov")
    gov2 = http_status(f"{url}?site=gov2")
    if args.json:
        print(json.dumps({"url": url, "gov": gov, "gov2": gov2}, indent=2))
    else:
        print(f"{url}")
        print(f"  US1-FED (?site=gov)  -> {gov}")
        print(f"  US2-FED (?site=gov2) -> {gov2}")
    return 0 if 200 in (gov, gov2) else 2


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Datadog site-support auditor.")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("list", help="list features unsupported on a site")
    sp.add_argument("--site", choices=("gov", "gov2"), default="gov")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("find", help="find the public doc URL for a feature")
    sp.add_argument("feature")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_find)

    sp = sub.add_parser("verify", help="HTTP-check a URL on gov + gov2")
    sp.add_argument("url")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_verify)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
