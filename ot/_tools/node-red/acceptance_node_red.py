"""ACCEPTANCE for `ot/_tools/node-red/node-red-to-a-designated-position.md`.

Starts a real Node-RED with the flow `pump-process-to-wertek.flow.json`, fires it over HTTP, and prints what
Wertek answered for each variable. Then checks that the key appears nowhere it should not. It never prints
the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test pump asset>
    export NODE_RED_BIN=/path/to/node_modules/node-red/red.js      # or have `node-red` on the PATH
    python acceptance_node_red.py

The position `pump_process` must already be designated on the asset (the Modbus recipe's acceptance does it).
Standard library only. Exit code 0 only when every expected answer was observed.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = os.environ.get("WERTEK_API_KEY")
ASSET = os.environ.get("WERTEK_ASSET_ID")
if not KEY or not ASSET:
    sys.exit("set WERTEK_API_KEY and WERTEK_ASSET_ID in the environment (the key is never printed)")
if any(ch.isspace() for ch in ASSET) or "<" in ASSET:
    sys.exit("WERTEK_ASSET_ID does not look like an asset id: set the real id")

bin_ = os.environ.get("NODE_RED_BIN") or shutil.which("node-red")
if not bin_:
    sys.exit("Node-RED not found: set NODE_RED_BIN (path to node-red or to red.js) or put `node-red` on the PATH")
cmd = ["node", bin_] if bin_.endswith(".js") else [bin_]

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'OK ' if cond else 'BAD'} {label} {detail}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/pump/run", timeout=60) as r:
        return {"status": r.status, "body": r.read().decode("utf-8")}


tmp = Path(tempfile.mkdtemp(prefix="wertek-nr-"))
flow_text = (HERE / "pump-process-to-wertek.flow.json").read_text(encoding="utf-8")
# The shipped flow also fires ITSELF every 60 s (its `inject` node). During an acceptance that second sender would land
# inside the cadence of our own probe and be mistaken for a failure, so the copy under test has that timer switched
# off: it fires only when probed. `flow_text` (the original) is what the key checks below read.
_flow = json.loads(flow_text)
for _n in _flow:
    if _n.get("type") == "inject":
        _n["repeat"] = ""
        _n["once"] = False
(tmp / "flows.json").write_text(json.dumps(_flow), encoding="utf-8")
(tmp / "settings.js").write_text(
    "module.exports = { flowFile: 'flows.json', credentialSecret: false, editorTheme: { projects: { enabled: false } },"
    " logging: { console: { level: 'info', metrics: false, audit: false } } };\n", encoding="utf-8")
log_path = tmp / "node-red.log"
port = free_port()
log = open(log_path, "wb")
proc = subprocess.Popen(cmd + ["-p", str(port), "-u", str(tmp), "-s", str(tmp / "settings.js")],
                        stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy())
try:
    for _ in range(120):
        if "Started flows" in log_path.read_text(encoding="utf-8", errors="replace"):
            break
        if proc.poll() is not None:
            sys.exit("Node-RED exited before starting (see the log in " + str(log_path) + ")")
        time.sleep(0.5)
    else:
        sys.exit("Node-RED did not start the flow in 60 s")
    print(f"node-red: 127.0.0.1:{port} · flow {len(json.loads(flow_text))} nodes")

    # 1 · the flow sends five variables; wait out the cadence once if a run happened a minute ago
    r = call(port)
    d = json.loads(r["body"])
    if any(a["c"] == 504 for a in d["answers"]):
        print("run 1 answered 504 (inside the cadence): waiting 62 s, then firing again")
        time.sleep(62)
        r = call(port)
        d = json.loads(r["body"])
    print("run 1:", [(a["key"], a["value"], a["c"]) for a in d["answers"]])
    check("the flow answered HTTP 200 to the probe", r["status"] == 200)
    check("five variables were built into five events", len(d["answers"]) == 5, str([a["key"] for a in d["answers"]]))
    check("all five answered 100 (stored)", [a["c"] for a in d["answers"]] == [100] * 5,
          str([a["c"] for a in d["answers"]]))
    check("nothing was skipped", d["skipped"] == [])

    # 2 · a second send inside the cadence is the gate doing its job: HTTP 422 with 504 per event, not a crash
    d2 = json.loads(call(port)["body"])
    check("a second send inside the cadence is answered 504 per event",
          [a["c"] for a in d2["answers"]] == [504] * 5, str([a["c"] for a in d2["answers"]]))
    check("the flow reports that as an answer (http 422), not as a failure", d2["http"] == 422, f"http={d2['http']}")

    # 3 · the key is nowhere it should not be
    time.sleep(1)
    log.flush()
    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    check("the key is not in the flow file", KEY not in flow_text)
    check("the key is not in the HTTP answers", KEY not in r["body"] and KEY not in json.dumps(d2))
    check("the key is not in Node-RED's log", KEY not in log_text)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()
    shutil.rmtree(tmp, ignore_errors=True)

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
