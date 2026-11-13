#!/usr/bin/env python3
"""Check that relative links in the docs resolve.

    python3 scripts/check-links.py [root]

External links are not fetched: this runs in CI on every push and a network
dependency would turn a documentation check into a flaky test. Anchors inside a
file are checked only for the file existing; heading anchors are not resolved,
because a rule that cannot be enforced cheaply gets disabled instead of fixed.

Exit 0 when every relative link resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def targets(text: str) -> list[str]:
    return [m.group(1) for m in LINK.finditer(text)]


def check(root: Path) -> list[str]:
    problems: list[str] = []
    for md in sorted(root.rglob("*.md")):
        if ".git" in md.parts:
            continue
        for raw in targets(md.read_text(encoding="utf-8", errors="replace")):
            if raw.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = raw.split("#", 1)[0]
            if not target:
                continue
            resolved = (md.parent / target).resolve()
            if not resolved.exists():
                rel = md.relative_to(root)
                problems.append(f"{rel}: {raw} -> not found")
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    problems = check(root)
    if problems:
        print(f"broken relative links: {len(problems)}")
        for p in problems:
            print(f"  {p}")
        return 1
    count = sum(1 for _ in root.rglob("*.md"))
    print(f"all relative links resolve ({count} markdown files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
