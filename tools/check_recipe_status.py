#!/usr/bin/env python3
"""The status of this repository is READ from its recipes, never typed into a README.

Every recipe carries its own `CONTRACT`, `SIDE`, `ACCEPTANCE` and `STATUS` lines (docs/RECIPE_TEMPLATE.md). This guard:

  1. reads them, and fails when a recipe has no `STATUS`, an unknown status word, a `verified` without a date or
     without an `ACCEPTANCE`, or a `SIDE` that is not the folder it lives in;
  2. GENERATES the status summary and the recipe tables that README.md, AGENTS.md, ot/README.md and it/README.md show,
     between the markers <!-- recipes:begin --> and <!-- recipes:end -->, and fails when what is there differs;
  3. refuses a hand-written count or claim outside those markers ("five recipes verified", "first recipe verified",
     "everything else is still planned"): a number copied by hand diverges the day the next recipe is merged;
  4. fails when a relative link in those four files points at something that does not exist.

Usage:  python tools/check_recipe_status.py            check (exit 1 on any problem; prints FILE and the RULE)
        python tools/check_recipe_status.py --write    regenerate the blocks, then check
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGIN, END = "<!-- recipes:begin -->", "<!-- recipes:end -->"
STATUS_WORDS = ("verified", "draft", "planned")
SIDES = ("ot", "it")
DOCS = ("README.md", "AGENTS.md", "ot/README.md", "it/README.md")

FIELD = re.compile(r"^(CONTRACT|SIDE|ACCEPTANCE|STATUS)[ \t]{2,}(\S.*)$", re.M)
NEXT_FIELD = re.compile(r"^[A-Z][A-Z ]{2,}[ \t]{2,}\S", re.M)
DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")
CLAIMS = {
    "hand-written-first-recipe-claim": re.compile(r"(?i)\bfirst recipe verified"),
    "hand-written-everything-else": re.compile(r"(?i)\beverything else (?:on this side )?is still `?planned"),
    "hand-written-count": re.compile(
        r"(?i)\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|\d+)\s+recipes?\s+(?:is |are )?verified"),
}


@dataclass
class Recipe:
    path: str            # relative to the repository root, forward slashes
    side: str            # folder it lives in: ot | it
    title: str
    contract: str
    declared_side: str
    status_word: str
    status_text: str
    date: str
    acceptance: str      # script | by hand | other | missing
    problems: list[str]


def _acceptance_kind(text: str, field: re.Match | None) -> str:
    if field is None:
        return "missing"
    start = field.start()
    rest = text[field.end():]
    nxt = NEXT_FIELD.search(rest)
    block = text[start:field.end() + (nxt.start() if nxt else len(rest))]
    if re.search(r"acceptance\w*\.(?:py|sh)\b", block):
        return "script"
    if re.match(r"ACCEPTANCE\s+by hand", block):
        return "by hand"
    return "other"


def discover(root: Path) -> list[Recipe]:
    found: list[Recipe] = []
    for side in SIDES:
        base = root / side
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if p.name == "README.md":
                continue
            text = p.read_text(encoding="utf-8")
            fields: dict[str, re.Match] = {}
            for m in FIELD.finditer(text):
                fields.setdefault(m.group(1), m)
            if "CONTRACT" not in fields and "STATUS" not in fields:
                continue                                          # not a recipe (a note, a table)
            rel = p.relative_to(root).as_posix()
            problems: list[str] = []
            heading = re.search(r"^#\s+(.+)$", text, re.M)
            status_text = fields["STATUS"].group(2).strip() if "STATUS" in fields else ""
            word = status_text.split(" ")[0].lower().rstrip(":,.") if status_text else ""
            date = (DATE.search(status_text) or [None, ""])[1] if status_text else ""
            decl = fields["SIDE"].group(2).strip().split(" ")[0] if "SIDE" in fields else ""
            acc = _acceptance_kind(text, fields.get("ACCEPTANCE"))
            if "STATUS" not in fields:
                problems.append("recipe-without-status")
            elif word not in STATUS_WORDS:
                problems.append("unknown-status-word")
            if word == "verified" and not date:
                problems.append("verified-without-a-date")
            if word == "verified" and acc == "missing":
                problems.append("verified-without-acceptance")
            if "CONTRACT" not in fields:
                problems.append("recipe-without-contract")
            if decl and decl != side:
                problems.append("side-differs-from-folder")
            found.append(Recipe(rel, side, heading.group(1).strip() if heading else rel,
                                fields["CONTRACT"].group(2).strip().split(" ")[0] if "CONTRACT" in fields else "?",
                                decl, word, status_text, date, acc, problems))
    return found


def summary(recipes: list[Recipe]) -> str:
    if not recipes:
        return "**STATUS: no recipe yet.**"
    n = len(recipes)
    c = {w: sum(1 for r in recipes if r.status_word == w) for w in STATUS_WORDS}
    newest = max((r.date for r in recipes if r.status_word == "verified" and r.date), default="")
    out = f"**STATUS: {n} recipe{'s' if n != 1 else ''} — {c['verified']} verified · {c['draft']} draft · {c['planned']} planned.**"
    if newest:
        out += f" Newest verification: {newest}."
    return out + (" Unless a recipe's own `STATUS` line names a real device, `verified` means it was run against the demo "
                  "organisation with a simulated source (or by hand): read that line for what was NOT verified.")


def table(recipes: list[Recipe], doc_dir: Path, root: Path) -> str:
    if not recipes:
        return "_No recipe on this side yet._"
    rows = ["| Recipe | Contract | Status | Verified on | Acceptance |", "|---|---|---|---|---|"]
    for r in recipes:
        rel = Path(__import__("os").path.relpath(root / r.path, doc_dir)).as_posix()
        rows.append(f"| [{r.title}]({rel}) | `{r.contract}` | {r.status_word or '?'} | {r.date or '-'} | {r.acceptance} |")
    return "\n".join(rows)


def expected_block(doc: str, recipes: list[Recipe], root: Path) -> str:
    doc_dir = (root / doc).parent
    if doc in ("README.md", "AGENTS.md"):
        body = summary(recipes)
    else:
        side = doc.split("/")[0]
        mine = [r for r in recipes if r.side == side]
        body = summary(mine) + "\n\n" + table(mine, doc_dir, root)
    return f"{BEGIN}\n{body}\n{END}"


BLOCK = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)


def check(root: Path, write: bool = False) -> list[tuple[str, str]]:
    """Returns [(file, rule)]. Never returns the text it compared."""
    problems: list[tuple[str, str]] = []
    recipes = discover(root)
    for r in recipes:
        problems += [(r.path, rule) for rule in r.problems]
    for doc in DOCS:
        p = root / doc
        if not p.exists():
            problems.append((doc, "document-missing"))
            continue
        text = p.read_text(encoding="utf-8")
        want = expected_block(doc, recipes, root)
        if not BLOCK.search(text):
            problems.append((doc, "markers-missing"))
            continue
        if write and BLOCK.search(text).group(0) != want:
            text = BLOCK.sub(lambda _m: want, text, count=1)
            p.write_text(text, encoding="utf-8")
        if BLOCK.search(text).group(0) != want:
            problems.append((doc, "generated-block-is-stale"))
        outside = BLOCK.sub("", text)
        for name, rx in CLAIMS.items():
            if rx.search(outside):
                problems.append((doc, name))
        for m in LINK.finditer(text):
            target = m.group(1)
            if re.match(r"^[a-z][a-z0-9+.-]*:", target):             # http:, https:, mailto:
                continue
            if not (p.parent / target).exists():
                problems.append((doc, "broken-link"))
                break
    return problems


def main(argv: list[str]) -> int:
    write = "--write" in argv
    problems = check(ROOT, write=write)
    n = len(discover(ROOT))
    if problems:
        for f, rule in problems:
            print(f"{f}: {rule}")
        print(f"check_recipe_status: {n} recipes, {len(problems)} problem(s)")
        return 1
    if n == 0:
        print("check_recipe_status: read 0 recipes — refusing to report OK")
        return 1
    print(f"check_recipe_status: {n} recipes, 0 problem(s)" + (" (blocks regenerated)" if write else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
