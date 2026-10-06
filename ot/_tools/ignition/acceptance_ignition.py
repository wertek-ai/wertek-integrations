"""Acceptance for the Ignition recipe: import the tag file into a running Gateway and see it send to Wertek.

    (with IGNITION_URL, IGNITION_API_TOKEN and optionally WERTEK_API_KEY EXPORTED in the shell, loaded as
    docs/API_KEY_HANDLING.md shows — never typed on the command line)
    python ot/_tools/ignition/acceptance_ignition.py

What it needs:
  * a running Ignition 8.3 Gateway whose ENVIRONMENT has WERTEK_API_KEY and WERTEK_ASSET_ID (the tag script
    reads them there; see the recipe), a tag provider named `default`, and the trial or a license running;
  * an Ignition API key (IGNITION_API_TOKEN) whose security level the Gateway accepts for read AND write
    (Platform -> Security -> General Settings);
  * optionally WERTEK_API_KEY in THIS shell too, only to prove the key is not in the tag file or the log.

It prints one OK/FAIL line per check and ends in `RESULT: PASS` or `RESULT: FAIL`. Standard library only.
No key is ever printed.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TAGS = Path(__file__).with_name("pump-process-to-wertek.tags.json")
LOGGER = "wertek.ingest"
WAIT_S = 150          # one tick is 65 s; a fresh import waits for its first change
EXPECTED_VARIABLES = 5

base = os.environ.get("IGNITION_URL", "http://localhost:8088").rstrip("/")
token = os.environ.get("IGNITION_API_TOKEN")
wertek_key = os.environ.get("WERTEK_API_KEY")
if not token:
    sys.exit("set IGNITION_API_TOKEN (an Ignition API key; it is never printed)")

results: list[bool] = []


def check(ok: bool, what: str) -> None:
    results.append(bool(ok))
    print(("  OK  " if ok else "  FAIL ") + what)


def call(method: str, path: str, query: dict | None = None, body: bytes | None = None,
         content_type: str = "application/json"):
    url = base + path + ("?" + urllib.parse.urlencode(query) if query else "")
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"X-Ignition-API-Token": token, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {}


# 1 · the Gateway answers with this key
st, info = call("GET", "/data/api/v1/gateway-info")
print(f"gateway: {info.get('name')} · Ignition {info.get('ignitionVersion')} · edition {info.get('edition')}")
check(st == 200, f"the Gateway API accepts the key (HTTP {st}; 401 = wrong key or secure channel, 403 = security level)")
if st != 200:
    print("RESULT: FAIL")
    sys.exit(1)
st, trial = call("GET", "/data/api/v1/trial")
running = st == 200 and not trial.get("expired", True)
check(running, f"the trial/license is running (expired={trial.get('expired')}, seconds left={trial.get('trialSecondsLeft')})")

# 2 · the tag file carries no secret, and imports cleanly
text = TAGS.read_text(encoding="utf-8")
check("WERTEK_API_KEY" in text and not re.search(r"\bwk_[A-Za-z0-9]", text),
      "the tag file reads the key from the environment and carries no key")
if wertek_key:
    check(wertek_key not in text, "the key in this shell is not in the tag file")
started_ms = int(time.time() * 1000)
st, imp = call("POST", "/data/api/v1/tags/import",
               {"provider": "default", "type": "json", "collisionPolicy": "Overwrite"},
               TAGS.read_bytes(), "application/octet-stream")
check(st == 200 and imp.get("failureCount") == 0 and imp.get("successCount", 0) >= 7,
      f"the tag file imports into [default] (HTTP {st}, success {imp.get('successCount')}, "
      f"failures {imp.get('failureCount')})")

# 3 · a NEW send appears in the Gateway log, with one answer per variable
line = None
deadline = time.time() + WAIT_S
while time.time() < deadline and line is None:
    st, logs = call("GET", "/data/api/v1/logs", {"logger": LOGGER, "startTime": started_ms, "limit": 20})
    for item in (logs.get("items") or []):
        msg = str(item.get("message") or "")
        if msg.startswith("sent ") or "failed" in msg or "not set" in msg or "no good-quality" in msg:
            line = msg
            break
    if line is None:
        time.sleep(5)
print(f"log: {line}")
check(line is not None, f"the tag script ran and logged under `{LOGGER}` within {WAIT_S} s")
codes = [int(c) for c in re.findall(r"(\d{3})L?\b", (line or "").split("codes", 1)[-1])][:EXPECTED_VARIABLES]
http = re.search(r"HTTP (\d{3})", line or "")
check(bool(http) and http.group(1) in ("200", "201"), f"the batch was accepted (HTTP {http.group(1) if http else '?'})")
check(len(codes) == EXPECTED_VARIABLES and all(c == 100 for c in codes),
      f"all {EXPECTED_VARIABLES} variables answered 100 (stored): {codes}")
check("skipped []" in (line or ""), "no variable was skipped for bad quality")

# 4 · the key never reaches the log
if wertek_key:
    st, logs = call("GET", "/data/api/v1/logs", {"startTime": started_ms, "limit": 500})
    blob = json.dumps(logs)
    check(wertek_key not in blob, "the key is not in the Gateway log")

print("RESULT: " + ("PASS" if all(results) else "FAIL"))
sys.exit(0 if all(results) else 1)
