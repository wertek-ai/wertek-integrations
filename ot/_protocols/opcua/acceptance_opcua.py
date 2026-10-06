"""ACCEPTANCE for `ot/_protocols/opcua/opcua-to-a-designated-position.md`.

Starts an OPC UA server on this machine that plays the MOTOR PROTECTION RELAY of a pump (bearing temperature, winding
temperature, power factor), runs the connector against it, sends to a real Wertek organisation and prints what came
back, event by event. It never prints the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test pump asset>
    python acceptance_opcua.py

The three variables are channels the pump panel reads (bearing_temp_c, winding_temp_c, pf): a variable's `key` is what
ties it to the panel, and the panel labels it with the CHANNEL's unit and does not convert. This is the pump's SECOND
instrument: it gets its own position (one position is one device), next to the hydraulics of the Modbus recipe.

Needs: asyncua (LGPL-3.0-or-later). Exit code 0 only when every expected answer was observed.
"""
from __future__ import annotations

import asyncio
import os
import socket
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "_common"))
import opcua_to_wertek as c  # noqa: E402
import wertek_send as w  # noqa: E402

from asyncua import Server, ua  # noqa: E402

cfg = w.config()
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "pump_motor")
NS_URI = "urn:wertek:test:motor-protection-relay"

VARS = [  # key, contract unit (the panel's own), node identifier on the server, simulated value
    ("bearing_temp_c", "°C", "BearingTemp", 71.5),
    ("winding_temp_c", "°C", "WindingTemp", 88.2),
    ("pf",             "1",  "PowerFactor", 0.86),
]
SPEC = {
    "code": cfg["position"], "name": "motor protection relay (wertek-integrations acceptance)", "component": "motor",
    "variables": [{"key": k, "unit": u, "unit_symbol": u, "kind": "gauge"} for k, u, _n, _v in VARS],
    "cadence_seconds": 60, "report_mode": "sampled",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
loop = asyncio.new_event_loop()
box: dict = {}


async def _server():
    srv = Server()
    await srv.init()
    srv.set_endpoint(f"opc.tcp://127.0.0.1:{PORT}/wertek-test/")
    idx = await srv.register_namespace(NS_URI)
    relay = await srv.nodes.objects.add_object(idx, "MotorProtectionRelay")
    nodes = {}
    for _k, _u, ident, val in VARS:
        nodes[ident] = await relay.add_variable(ua.NodeId(ident, idx), ident, float(val))
    nodes["Fault"] = await relay.add_variable(ua.NodeId("Fault", idx), "Fault", 0.0)
    box["nodes"] = nodes
    async with srv:
        box["ready"] = True
        await asyncio.Event().wait()


def serve():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_server())
    except Exception as e:                      # shutdown cancels the wait: expected
        box["ended"] = type(e).__name__


async def _refresh():
    """A real source stamps each reading when the DEVICE updates it. Do the same, so the source time is now."""
    for _k, _u, ident, val in VARS:
        await box["nodes"][ident].write_value(float(val))
    # a node whose quality is BAD: the device says its reading is not to be trusted
    await box["nodes"]["Fault"].write_value(ua.DataValue(
        ua.Variant(0.0, ua.VariantType.Double), ua.StatusCode(ua.StatusCodes.BadSensorFailure), None))


def refresh():
    asyncio.run_coroutine_threadsafe(_refresh(), loop).result(timeout=10)


threading.Thread(target=serve, daemon=True).start()
for _ in range(100):
    if box.get("ready"):
        break
    time.sleep(0.1)
else:
    sys.exit("the local OPC UA server did not start")

print(f"opc ua server: 127.0.0.1:{PORT} · namespace {NS_URI} · {len(VARS)} measured nodes + 1 with a BAD status")
pos = w.ensure_position(cfg, SPEC)
print("position:", cfg["position"], "· adapter", pos["assignment"]["adapter"], "· covered", pos["covered"],
      "· variables", [v["key"] + "[" + str(v.get("unit")) + "]" for v in pos["variables"]])

base_map = {
    "server": {"url": f"opc.tcp://127.0.0.1:{PORT}/wertek-test/", "timeout_s": 5},
    "position": cfg["position"],
    "nodes": [{"namespace_uri": NS_URI, "identifier": ident, "variable": k, "unit": u}
              for k, u, ident, _v in VARS],
}

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'OK ' if cond else 'BAD'} {label} {detail}")


def codes_of(events, results):
    return [results.get(e["event_id"], {}).get("c") for e in events]


# 1 · the happy path: three nodes -> three events, each answered 100 (stored)
refresh()
events, results, skipped = c.run_once(cfg, base_map)
codes = codes_of(events, results)
if 504 in codes:   # a run happened less than a cadence ago: wait it out and prove the STORE once
    wait = int(pos["assignment"].get("cadence_seconds") or 60) + 2
    print(f"run 1 answered 504 (inside the cadence): waiting {wait} s, then sending again")
    time.sleep(wait)
    refresh()
    events, results, skipped = c.run_once(cfg, base_map)
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", got, codes)
check("three nodes become three events", len(events) == 3)
check("values read as the device published them",
      all(abs(got.get(k, -1) - v) < 1e-9 for k, _u, _n, v in VARS))
check("all three answered 100 (stored)", codes == [100] * 3, str(codes))

# 2 · a node whose StatusCode is BAD is skipped and NAMED; nothing is sent in its place
time.sleep(int(pos["assignment"].get("cadence_seconds") or 60) + 2)        # let the gate open again
refresh()
m2 = {**base_map, "nodes": base_map["nodes"] + [
    {"namespace_uri": NS_URI, "identifier": "Fault", "variable": "pf", "unit": "1"}]}
events2, _results2, skipped2 = c.run_once(cfg, m2)
check("a node with a BAD status is skipped and named, not sent as a number",
      len(events2) == 3 and len(skipped2) == 1 and "Bad" in skipped2[0], str(skipped2))

# 3 · a node that does not exist on the server is skipped and named too
m3 = {**base_map, "nodes": base_map["nodes"] + [
    {"namespace_uri": NS_URI, "identifier": "NoSuchNode", "variable": "pf", "unit": "1"}]}
_events3, _results3, skipped3 = c.run_once(cfg, m3)
check("a missing node is skipped and named", any("NoSuchNode" in s for s in skipped3), str(skipped3))

# 4 · a wrong unit declared in the map is Wertek's to refuse: 406, and no conversion
m4 = {**base_map, "nodes": [{"namespace_uri": NS_URI, "identifier": "PowerFactor", "variable": "pf", "unit": "%"}]}
events4, results4, _ = c.run_once(cfg, m4)
code4 = codes_of(events4, results4)[0] if events4 else None
check("a wrong unit is answered 406 (no conversion)", code4 == 406, f"c={code4}")

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
