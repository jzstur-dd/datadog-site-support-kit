#!/usr/bin/env python3
"""Idempotently inject a managed markdown block into a target file (e.g. CLAUDE.md).

Usage: python3 _inject.py <target.md> <content.md> <MARKER>
Re-running replaces the block between the markers instead of duplicating it.
"""
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 1
    target, content_path, marker = sys.argv[1], sys.argv[2], sys.argv[3]
    tp = Path(target)
    content = Path(content_path).read_text(encoding="utf-8").rstrip()
    begin = f"<!-- {marker}:BEGIN (managed — re-run install to update) -->"
    end = f"<!-- {marker}:END -->"
    block = f"{begin}\n{content}\n{end}"
    existing = tp.read_text(encoding="utf-8") if tp.exists() else ""
    if begin in existing and end in existing:
        pre = existing.split(begin)[0]
        post = existing.split(end, 1)[1]
        new = f"{pre.rstrip()}\n\n{block}\n{post.lstrip()}".rstrip() + "\n"
    elif existing.strip():
        new = existing.rstrip() + f"\n\n{block}\n"
    else:
        new = block + "\n"
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.write_text(new, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
