#!/usr/bin/env python3
"""Arms tools/check_credentials.py: every rule must catch its decoy, every safe pattern must pass,
and the guard must never print what it found.

Decoys are built here, at run time, so this file holds no credential-shaped string itself.
Run:  python tools/test_check_credentials.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_credentials as g  # noqa: E402

HEX48 = "a1b2" * 12                                   # 48 hex chars
KEY = "wk_" + HEX48
JWT = "eyJ" + "h" * 12 + ".eyJ" + "p" * 12 + "." + "s" * 12
ANT = "sk-" + "ant-" + "x" * 24

MUST_CATCH = {
    "wertek-key-shape": f"the key is {KEY} ok",
    "jwt-shape": f"token = {JWT}",
    "anthropic-key-shape": f"k={ANT}",
    "literal-api-key-header": 'headers = {"X-API-Key": "' + "q" * 20 + '"}',
    "literal-credential-assignment": 'api_key = "' + "z" * 20 + '"',
    "literal-on-command-line": f"WERTEK_API_KEY={'z' * 12} python run.py",
    "literal-on-command-line (placeholder form)": "WERTEK_API_KEY=wk_… python run.py",
}
MUST_PASS = [
    'headers = {"X-API-Key": KEY}',
    'headers = {"X-API-Key": os.environ["WERTEK_API_KEY"]}',
    "X-API-Key: $WERTEK_API_KEY",
    'curl -H "X-API-Key: ${WERTEK_API_KEY}" https://example.invalid',
    'export WERTEK_API_KEY="$(your-secret-store get wertek-api-key)"',
    "WERTEK_API_KEY=",
    "WERTEK_API_KEY is read from the environment (scope iaes.ingest)",
    "read -rs WERTEK_API_KEY; export WERTEK_API_KEY",
    'api_key = os.environ.get("WERTEK_API_KEY")',
    "write `<your key>` if you need a placeholder",
]


def main() -> int:
    failures: list[str] = []

    for name, line in MUST_CATCH.items():
        got = {r for _, r in g.scan_text(line)}
        if name.split(' ')[0] not in got:
            failures.append(f"decoy NOT caught: {name} (got {sorted(got)})")

    for line in MUST_PASS:
        got = g.scan_text(line)
        if got:
            failures.append(f"safe pattern flagged: {line!r} -> {got}")

    # an explicit allow mark silences a line on purpose
    if g.scan_text(f"{KEY}  # {g.ALLOW_MARK}"):
        failures.append("allow mark did not silence the line")

    # the guard must not print what it found
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "leak.md"
        p.write_text(f"oops {KEY}\n", encoding="utf-8")
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = g.main([str(p)])
        out = buf.getvalue()
        if rc != 1:
            failures.append(f"main() should fail on a leak, returned {rc}")
        if HEX48 in out or KEY in out:
            failures.append("the guard printed the secret it found")

        empty = Path(d) / "image.png"
        empty.write_bytes(b"\x89PNG")
        if g.main([str(empty)]) != 2:
            failures.append("a guard that reads zero files must not report OK")

    # and the repo itself is clean
    if g.main([]) != 0:
        failures.append("the repository contains something the guard flags (run check_credentials.py)")

    if failures:
        print("FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print(f"OK — {len(MUST_CATCH)} decoys caught, {len(MUST_PASS)} safe patterns passed, nothing printed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
