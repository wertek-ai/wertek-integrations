#!/usr/bin/env python3
"""No credential may be committed to this repository (docs/API_KEY_HANDLING.md).

Scans the tracked text files and fails with exit 1 when one holds something shaped like a credential, or
shows a key the way the rule forbids (a literal in a header, an assignment, or a command-line prefix).

It reports FILE:LINE and the NAME OF THE RULE. It never prints the matched text, so running it in CI
cannot itself leak what it finds.

Usage:  python tools/check_credentials.py [path ...]     (default: every tracked file)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# name -> regex. Each is armed by tools/test_check_credentials.py with a decoy built at run time.
RULES: dict[str, re.Pattern[str]] = {
    # `wk_` + 48 hex characters is the whole shape of a Wertek key.
    "wertek-key-shape": re.compile(r"\bwk_[0-9a-fA-F]{40,}\b"),
    # Header.Payload.Signature of a JSON Web Token.
    "jwt-shape": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."),
    "anthropic-key-shape": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}"),
    # `X-API-Key: <literal>` — a reference (`$VAR`, `${VAR}`, `os.environ`, `<...>`, `...`) is fine.
    "literal-api-key-header": re.compile(
        r"""(?ix)\bx-api-key["']?\s*[:=]\s*["']?(?![$<{\.…]|os\.|process\.|env[.\[(]|_?key\b)[A-Za-z0-9_\-]{16,}"""
    ),
    # api_key = "literal" / token: 'literal' / secret="literal"
    "literal-credential-assignment": re.compile(
        r"""(?ix)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password)\b["']?\s*[:=]\s*["'][A-Za-z0-9_\-/+=]{16,}["']"""
    ),
}

# `WERTEK_API_KEY=<something>` on a command line leaves the value in history. Allowed: empty, or a reference.
INLINE_ENV = re.compile(r"\bWERTEK_API_KEY=(?P<v>\S*)")
INLINE_OK = re.compile(r"""^(?:["']?\$|["']?\$\(|["']?\$\{|$)""")

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
TEXT_SUFFIXES = {
    ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".txt", ".sh", ".ps1", ".toml", ".cfg", ".ini",
    ".html", ".env", ".example", "",
}
ALLOW_MARK = "credential-guard: ok"  # a line that must show such a shape on purpose
# The guard and its test have to contain the very shapes they detect (the decoys are built at run time,
# but the patterns and the safe samples are text). Exactly these two files, nothing else.
SELF = {"tools/check_credentials.py", "tools/test_check_credentials.py"}


def tracked_files(paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p) for p in paths]
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    return [ROOT / p for p in out]


def scan_text(text: str) -> list[tuple[int, str]]:
    """(line number, rule name) for every violation. Never returns the matched text."""
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), 1):
        if ALLOW_MARK in line:
            continue
        for name, rx in RULES.items():
            if rx.search(line):
                hits.append((n, name))
        for m in INLINE_ENV.finditer(line):
            if not INLINE_OK.match(m.group("v")):
                hits.append((n, "literal-on-command-line"))
    return hits


def main(argv: list[str]) -> int:
    bad = 0
    scanned = 0
    for f in tracked_files(argv):
        if any(part in SKIP_DIRS for part in f.parts) or f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if f.resolve().relative_to(ROOT).as_posix() in SELF:
                continue
        except ValueError:
            pass
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for n, name in scan_text(text):
            try:
                shown = f.relative_to(ROOT)
            except ValueError:
                shown = f
            print(f"{shown}:{n}: {name}")
            bad += 1
    if scanned == 0:
        # Absence is not approval: a guard that read nothing proves nothing.
        print("check_credentials: read 0 files — refusing to report OK", file=sys.stderr)
        return 2
    print(f"check_credentials: {scanned} files, {bad} violation(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
