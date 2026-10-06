#!/usr/bin/env python3
"""Arms tools/check_recipe_status.py: every rule must catch its decoy, and a clean tree must pass.

The decoys are built here, in a temporary repository, so this file never touches the real one.
Run:  python tools/test_check_recipe_status.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_recipe_status as g  # noqa: E402

RECIPE = """# Read a thing and send it

```
CONTRACT      iaes
SIDE          ot
ACCEPTANCE    python ot/a/acceptance_a.py must end in PASS
STATUS        verified 2026-10-05 · against the demo organisation
```
"""
DOC = "# {t}\n\n{b}\n\n" + g.BEGIN + "\nPLACEHOLDER\n" + g.END + "\n\n[a link](ot/a/r.md)\n"


def make(tmp: Path, recipe: str = RECIPE, extra: dict[str, str] | None = None) -> None:
    (tmp / "ot" / "a").mkdir(parents=True, exist_ok=True)
    (tmp / "it").mkdir(exist_ok=True)
    (tmp / "ot" / "a" / "r.md").write_text(recipe, encoding="utf-8")
    for doc in g.DOCS:
        p = tmp / doc
        p.parent.mkdir(parents=True, exist_ok=True)
        link = "[a link](ot/a/r.md)" if doc in ("README.md", "AGENTS.md") else "[a link](../README.md)"
        p.write_text(DOC.replace("[a link](ot/a/r.md)", link).format(t=doc, b=""), encoding="utf-8")
    for rel, text in (extra or {}).items():
        (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp / rel).write_text(text, encoding="utf-8")
    g.check(tmp, write=True)                       # a clean, generated baseline


def rules(tmp: Path) -> set[str]:
    return {r for _f, r in g.check(tmp)}


failures: list[str] = []


def expect(label: str, got: set[str], must: str | None) -> None:
    ok = (not got) if must is None else (must in got)
    print(f"  {'OK ' if ok else 'BAD'} {label}" + ("" if ok else f"   got {sorted(got)}"))
    if not ok:
        failures.append(label)


def case(label: str, mutate, must: str | None) -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make(tmp)
        mutate(tmp)
        expect(label, rules(tmp), must)


def edit(tmp: Path, rel: str, old: str, new: str) -> None:
    p = tmp / rel
    t = p.read_text(encoding="utf-8")
    assert old in t, (rel, old)
    p.write_text(t.replace(old, new, 1), encoding="utf-8")


print("check_recipe_status — decoys")
case("a clean tree passes", lambda t: None, None)
case("a stale generated count is caught", lambda t: edit(t, "README.md", "1 recipe", "9 recipes"), "generated-block-is-stale")
case("a recipe missing from a table is caught", lambda t: (t / "ot" / "a" / "r2.md").write_text(
    RECIPE.replace("# Read a thing", "# Another"), encoding="utf-8"), "generated-block-is-stale")
case("a hand-written 'five recipes verified' is caught",
     lambda t: edit(t, "ot/README.md", "# ot/README.md", "# ot/README.md\n\n> **STATUS: five recipes verified.**"),
     "hand-written-count")
case("a hand-written 'first recipe verified' is caught",
     lambda t: edit(t, "README.md", "# README.md", "# README.md\n\n**STATUS: first recipe verified**"),
     "hand-written-first-recipe-claim")
case("a hand-written 'everything else is still planned' is caught",
     lambda t: edit(t, "README.md", "# README.md", "# README.md\n\nEverything else is still `planned`."),
     "hand-written-everything-else")
case("a missing marker is caught", lambda t: edit(t, "AGENTS.md", g.BEGIN, ""), "markers-missing")
case("a broken relative link is caught", lambda t: edit(t, "README.md", "(ot/a/r.md)", "(ot/nope/x.md)"), "broken-link")
case("a missing document is caught", lambda t: (t / "it" / "README.md").unlink(), "document-missing")
case("a recipe with no STATUS is caught",
     lambda t: (t / "ot" / "a" / "r.md").write_text(RECIPE.replace("STATUS        verified 2026-10-05 · x\n", "")
                                                    .replace("STATUS        verified 2026-10-05 · against the demo organisation\n", ""),
                                                    encoding="utf-8"), "recipe-without-status")
case("an unknown status word is caught",
     lambda t: (t / "ot" / "a" / "r.md").write_text(RECIPE.replace("verified 2026-10-05", "works 2026-10-05"), encoding="utf-8"),
     "unknown-status-word")
case("'verified' without a date is caught",
     lambda t: (t / "ot" / "a" / "r.md").write_text(RECIPE.replace("verified 2026-10-05", "verified"), encoding="utf-8"),
     "verified-without-a-date")
case("'verified' without an ACCEPTANCE is caught",
     lambda t: (t / "ot" / "a" / "r.md").write_text(
         RECIPE.replace("ACCEPTANCE    python ot/a/acceptance_a.py must end in PASS\n", ""), encoding="utf-8"),
     "verified-without-acceptance")
case("a recipe in the wrong side's folder is caught",
     lambda t: (t / "ot" / "a" / "r.md").write_text(RECIPE.replace("SIDE          ot", "SIDE          it"), encoding="utf-8"),
     "side-differs-from-folder")

# the table tells a script acceptance from one done by hand (the template wants an executable one)
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    make(tmp, RECIPE.replace("python ot/a/acceptance_a.py must end in PASS", "by hand (no command line here): import it and run once"))
    table = (tmp / "ot" / "README.md").read_text(encoding="utf-8")
    expect("a by-hand acceptance is shown as such in the table", {"by hand"} if "| by hand |" in table else set(), "by hand")

# a repository with no recipe at all is refused, not reported clean
with tempfile.TemporaryDirectory() as d:
    tmp = Path(d)
    for doc in g.DOCS:
        (tmp / doc).parent.mkdir(parents=True, exist_ok=True)
        (tmp / doc).write_text(DOC.format(t=doc, b=""), encoding="utf-8")
    g.check(tmp, write=True)
    real_root, g.ROOT = g.ROOT, tmp
    try:
        import io
        from contextlib import redirect_stdout
        with redirect_stdout(io.StringIO()):
            code = g.main([])
    finally:
        g.ROOT = real_root
    expect("a repository with zero recipes is refused, not reported clean", {"refused"} if code == 1 else set(), "refused")

print("RESULT:", "PASS" if not failures else f"FAIL ({len(failures)})")
sys.exit(1 if failures else 0)
