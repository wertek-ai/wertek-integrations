"""Read variables from an OPC UA server and send them to Wertek as IAES measurements.

Recipe: ot/_protocols/opcua/opcua-to-a-designated-position.md

    # the key comes from the environment, never from this command line (docs/API_KEY_HANDLING.md)
    python opcua_to_wertek.py --map my_map.json --once

A map says WHICH nodes, in which namespace, how to scale them and the UNIT of each value. OPC UA carries engineering
units only if the server publishes them, and many do not: the person who writes the map declares them, and this
program never guesses. A node whose StatusCode is not Good is SKIPPED and named; it is never sent as a number.

If the OPC UA server needs a user, its credentials come from OPCUA_USERNAME and OPCUA_PASSWORD in the environment,
never from the map.

Needs: asyncua (LGPL-3.0-or-later; you install it, this repository does not redistribute it).
The send half is ot/_common/wertek_send.py (standard library).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from datetime import timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
import wertek_send as w  # noqa: E402


async def read_values(m: dict) -> tuple[list[dict], list[str]]:
    """Read every node of the map. Returns (readings, skipped). A node that cannot be read, or whose StatusCode
    is not Good, is SKIPPED and named; a zero or a previous value is never sent in its place."""
    from asyncua import Client

    dev = m["server"]
    client = Client(dev["url"], timeout=float(dev.get("timeout_s", 5)))
    user, password = os.environ.get("OPCUA_USERNAME"), os.environ.get("OPCUA_PASSWORD")
    if user and password:
        client.set_user(user)
        client.set_password(password)
    readings, skipped = [], []
    async with client:
        ns_cache: dict[str, int] = {}
        for r in m["nodes"]:
            label = f"{r['variable']}@{r.get('identifier')}"
            try:
                uri = r["namespace_uri"]            # the index differs between servers: ask the server for it
                if uri not in ns_cache:
                    ns_cache[uri] = await client.get_namespace_index(uri)
                node = client.get_node(f"ns={ns_cache[uri]};s={r['identifier']}")
                dv = await node.read_data_value()
            except Exception as e:                    # name the node, never the connection details
                skipped.append(f"{label}: {type(e).__name__}")
                continue
            if not dv.StatusCode.is_good():
                skipped.append(f"{label}: status {dv.StatusCode.name}")
                continue
            v = dv.Value.Value
            if isinstance(v, bool):
                v = 1 if v else 0                    # the contract's convention: a boolean travels as 0/1
            if not isinstance(v, (int, float)):
                skipped.append(f"{label}: not a number")
                continue
            v = round(float(v) * float(r.get("scale", 1)) + float(r.get("offset", 0)), 6)
            when = dv.SourceTimestamp                # the time the SOURCE says; fall back to now
            readings.append({"variable": r["variable"], "unit": r["unit"], "value": v,
                             "when": when.replace(tzinfo=timezone.utc).timestamp() if when else None})
    return readings, skipped


def run_once(cfg: dict, m: dict) -> tuple[list[dict], dict, list[str]]:
    """One cycle: read, build events, send. Returns (events, results by event_id, skipped)."""
    try:
        readings, skipped = asyncio.run(read_values(m))
    except Exception as e:
        return [], {}, [f"could not read the server: {type(e).__name__}"]
    corr = str(uuid.uuid4())
    events = [w.event(cfg, x["variable"], x["value"], x["unit"], "wertek_integrations.opcua", corr, when=x["when"])
              for x in readings]
    results = w.send(cfg, events) if events else {}
    return events, results, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", required=True, help="JSON node map")
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--interval", type=int, default=0, help="seconds between cycles (>= the position's cadence)")
    a = ap.parse_args()
    m = json.loads(Path(a.map).read_text(encoding="utf-8"))
    cfg = w.config()
    cfg["position"] = m.get("position", cfg["position"])
    while True:
        events, results, skipped = run_once(cfg, m)
        for e in events:
            x = results.get(e["event_id"], {})
            print(f"{e['data']['measurement_type']}={e['data']['value']} {e['data']['unit']} -> c={x.get('c')}")
        for s in skipped:
            print("skipped:", s)
        if a.once or not a.interval:
            return 0
        time.sleep(a.interval)


if __name__ == "__main__":
    sys.exit(main())
