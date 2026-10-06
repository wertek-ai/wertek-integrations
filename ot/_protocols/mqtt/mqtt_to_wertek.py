"""Listen to an MQTT broker for a while and send what it published to Wertek as IAES measurements.

Recipe: ot/_protocols/mqtt/mqtt-to-a-designated-position.md

    # the key comes from the environment, never from this command line (docs/API_KEY_HANDLING.md)
    python mqtt_to_wertek.py --map my_map.json --once

A map says WHICH topics, how to read each payload (a bare number or a JSON field), and the UNIT of each value. MQTT carries
neither units nor names: the person who writes the map declares them, and this program never guesses.

Two traps this program refuses on purpose:
  * a RETAINED message is whatever the broker kept from the last publish, possibly days ago, and it arrives the moment
    you subscribe. Stamping it with "now" would present an old value as fresh, so a retained message is skipped and
    named unless its payload carries its own time (`ts_path`).
  * a payload that is not a number (or a JSON field that is missing) is skipped and named, never sent as zero.

If the broker needs a user, MQTT_USERNAME and MQTT_PASSWORD come from the environment, never from the map.

Needs: paho-mqtt (EPL-2.0 OR BSD-3-Clause). The send half is ot/_common/wertek_send.py (standard library).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
import wertek_send as w  # noqa: E402


def dig(obj, path: str):
    """`a.b.c` into nested dicts. Returns (found, value)."""
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False, None
    return True, cur


def to_epoch(v) -> float | None:
    """A payload time: seconds or milliseconds since the epoch, or an ISO 8601 string. None if it is not one."""
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v / 1000.0 if v > 1e11 else float(v)
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None
    return None


def parse_payload(raw: bytes, t: dict):
    """One message -> (value, event_time_or_None, problem_or_None)."""
    text = raw.decode("utf-8", errors="replace").strip()
    path = t.get("json_path")
    if path:
        try:
            ok, v = dig(json.loads(text), path)
        except ValueError:
            return None, None, "payload is not JSON"
        if not ok:
            return None, None, f"no field {path}"
        when = None
        if t.get("ts_path"):
            found, tv = dig(json.loads(text), t["ts_path"])
            when = to_epoch(tv) if found else None
    else:
        v, when = text, None
    if isinstance(v, bool):
        v = 1 if v else 0                         # the contract's convention: a boolean travels as 0/1
    elif isinstance(v, str):
        low = v.lower()
        v = 1 if low == "true" else 0 if low == "false" else v
        if isinstance(v, str):
            try:
                v = float(v)
            except ValueError:
                return None, None, "not a number"
    if not isinstance(v, (int, float)):
        return None, None, "not a number"
    return round(float(v) * float(t.get("scale", 1)) + float(t.get("offset", 0)), 6), when, None


def listen(m: dict) -> tuple[dict, list[str]]:
    """Subscribe and keep the LATEST message of each topic for `listen_s` seconds. Returns (latest, skipped)."""
    import paho.mqtt.client as mqtt

    b = m["broker"]
    latest: dict[str, dict] = {}
    skipped: list[str] = []
    done = threading.Event()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=b.get("client_id", "wertek-integrations-" + uuid.uuid4().hex[:8]))
    user, password = os.environ.get("MQTT_USERNAME"), os.environ.get("MQTT_PASSWORD")
    if user:
        client.username_pw_set(user, password)
    if b.get("tls"):
        client.tls_set()                          # system CA store; which CA to trust is NOT inferred here

    connected = threading.Event()

    def on_connect(c, _u, _f, rc, _p):
        if rc != 0:                               # `rc` is a ReasonCode: name it, never the credentials
            skipped.append(f"broker refused the connection: {rc}")
            done.set()
            return
        connected.set()
        for t in m["topics"]:
            c.subscribe(t["topic"], qos=int(t.get("qos", 0)))

    def on_message(_c, _u, msg):
        latest[msg.topic] = {"payload": msg.payload, "retained": bool(msg.retain), "at": time.time()}

    client.on_connect, client.on_message = on_connect, on_message
    try:
        client.connect(b["host"], int(b.get("port", 1883)), keepalive=int(b.get("keepalive", 30)))
    except OSError as e:
        return {}, [f"could not reach the broker: {type(e).__name__}"]
    client.loop_start()
    done.wait(timeout=float(m.get("listen_s", 5)))
    client.loop_stop()
    client.disconnect()
    if not connected.is_set() and not skipped:
        # some brokers drop an unwanted client without ever answering: without this, "nothing arrived" would be
        # read as "the plant published nothing" when in fact we never got in
        skipped.append(f"never connected to the broker within {m.get('listen_s', 5)} s (refused, unreachable or wrong credentials)")
    return latest, skipped


def run_once(cfg: dict, m: dict) -> tuple[list[dict], dict, list[str]]:
    """One cycle: listen, decode, build events, send. Returns (events, results by event_id, skipped)."""
    latest, skipped = listen(m)
    corr = str(uuid.uuid4())
    events = []
    for t in m["topics"]:
        got = latest.get(t["topic"])
        name = f"{t['variable']}@{t['topic']}"
        if got is None:
            skipped.append(f"{name}: nothing published in the window")
            continue
        value, when, problem = parse_payload(got["payload"], t)
        if problem:
            skipped.append(f"{name}: {problem}")
            continue
        if got["retained"] and when is None:
            skipped.append(f"{name}: retained message without its own time (it could be old)")
            continue
        events.append(w.event(cfg, t["variable"], value, t["unit"], "wertek_integrations.mqtt", corr,
                              when=when if when is not None else got["at"]))
    results = w.send(cfg, events) if events else {}
    return events, results, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", required=True, help="JSON topic map")
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
