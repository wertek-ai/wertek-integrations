"""ACCEPTANCE for `ot/_protocols/mqtt/mqtt-to-a-designated-position.md`.

Starts a real MQTT broker (amqtt) on this machine, publishes what an edge gateway would publish about a PUMP, runs the
connector against it, sends to a real Wertek organisation and prints what came back, event by event. It never prints
the API key, and the broker has no credentials worth keeping.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test pump asset>
    python acceptance_mqtt.py

It feeds the pump's `pump_process` position (the same five variables as the Modbus recipe), so the position must be
designated already (the Modbus recipe's acceptance does it). MQTT carries neither names nor units: the map declares them.

Needs: paho-mqtt (the connector) and amqtt (the test broker only). Exit code 0 only when every expected answer was observed.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "_common"))
import mqtt_to_wertek as c  # noqa: E402
import wertek_send as w  # noqa: E402

import paho.mqtt.client as mqtt  # noqa: E402
from amqtt.broker import Broker  # noqa: E402

cfg = w.config()
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "pump_process")
SPEC = {
    "code": cfg["position"], "name": "pump process variables (wertek-integrations acceptance)", "component": "pump",
    "variables": [{"key": k, "unit": u, "unit_symbol": u, "kind": "gauge"} for k, u in
                  [("flow_m3h", "m³/h"), ("head_m", "m"), ("kw", "kW"), ("seal_temp_c", "°C"), ("vibration_mm_s", "mm/s")]],
    "cadence_seconds": 60, "report_mode": "sampled",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT, PORT_SILENT, PORT_CLOSED = free_port(), free_port(), free_port()
loop = asyncio.new_event_loop()
brokers: list = []


async def _brokers():
    anon = {"amqtt.plugins.authentication.AnonymousAuthPlugin": {"allow_anonymous": True}}
    b = Broker({"listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT}"}}, "sys_interval": 0, "plugins": anon})
    await b.start()
    brokers.append(b)
    await asyncio.Event().wait()


def silent_server():
    """Accepts a TCP connection and never answers: the case of a broker (or a firewall) that does not let us in
    without saying so. The connector must NAME that, not read it as 'the plant published nothing'."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", PORT_SILENT))
    srv.listen(5)
    held = []
    while True:
        conn, _ = srv.accept()
        held.append(conn)          # keep it open, say nothing


threading.Thread(target=silent_server, daemon=True).start()


def serve():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_brokers())
    except Exception:                                   # shutdown cancels the wait: expected
        pass


threading.Thread(target=serve, daemon=True).start()
for p in (PORT, PORT_SILENT):
    for _ in range(80):
        try:
            socket.create_connection(("127.0.0.1", p), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        sys.exit("the local MQTT broker did not start")
print(f"broker: 127.0.0.1:{PORT} · a silent TCP server on :{PORT_SILENT} · nothing listening on :{PORT_CLOSED}")


def publish(items, retain=False, delay=0.0):
    """Publish like an edge gateway would. `delay` lets the connector subscribe first (QoS 0 is not queued)."""
    def go():
        time.sleep(delay)
        pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="acceptance-publisher")
        pub.connect("127.0.0.1", PORT)
        pub.loop_start()
        for topic, payload in items:
            pub.publish(topic, payload, qos=1, retain=retain).wait_for_publish(timeout=5)
        pub.loop_stop()
        pub.disconnect()
    t = threading.Thread(target=go)
    t.start()
    return t


ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'OK ' if cond else 'BAD'} {label} {detail}")


def codes_of(events, results):
    return [results.get(e["event_id"], {}).get("c") for e in events]


pos = w.ensure_position(cfg, SPEC)
cadence = int(pos["assignment"].get("cadence_seconds") or 60)
print("position:", cfg["position"], "· adapter", pos["assignment"]["adapter"], "· covered", pos["covered"])

base_map = {
    "broker": {"host": "127.0.0.1", "port": PORT},
    "position": cfg["position"], "listen_s": 4,
    "topics": [
        {"topic": "plant/pump1/flow",    "variable": "flow_m3h",       "unit": "m³/h"},                    # a bare number
        {"topic": "plant/pump1/process", "json_path": "head.m", "variable": "head_m", "unit": "m"},        # a JSON field
        {"topic": "plant/pump1/power",   "scale": 0.1, "variable": "kw", "unit": "kW"},                    # raw x 0.1
        {"topic": "plant/pump1/seal",    "json_path": "t", "ts_path": "at", "variable": "seal_temp_c", "unit": "°C"},
        {"topic": "plant/pump1/vib",     "variable": "vibration_mm_s", "unit": "mm/s"},
    ],
}
def feed():
    """What the gateway publishes NOW. The seal temperature carries its own time, taken at each publication: sending
    the same time twice is sending the same reading twice, and Wertek answers that 504."""
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [("plant/pump1/flow", "412.5"), ("plant/pump1/process", json.dumps({"head": {"m": 85.2}})),
            ("plant/pump1/power", "1184"), ("plant/pump1/seal", json.dumps({"t": 62.3, "at": at})),
            ("plant/pump1/vib", "2.8")]


# 1 · the happy path: five topics -> five events, the latest message of each, each answered 100 (stored)
th = publish(feed(), delay=1.5)
events, results, skipped = c.run_once(cfg, base_map)
th.join()
codes = codes_of(events, results)
if 504 in codes:   # a run happened less than a cadence ago: wait it out and prove the STORE once
    print(f"run 1 answered 504 (inside the cadence): waiting {cadence + 2} s, then sending again")
    time.sleep(cadence + 2)
    th = publish(feed(), delay=1.5)
    events, results, skipped = c.run_once(cfg, base_map)
    th.join()
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", got, codes)
check("five topics become five events", len(events) == 5 and skipped == [], str(skipped))
check("a bare number, a JSON field and a scaled raw value are decoded",
      got.get("flow_m3h") == 412.5 and got.get("head_m") == 85.2 and abs(got.get("kw", -1) - 118.4) < 1e-9
      and got.get("seal_temp_c") == 62.3 and got.get("vibration_mm_s") == 2.8, str(got))
check("all five answered 100 (stored)", codes == [100] * 5, str(codes))

# 2 · nothing below sends anything: the checks read the broker only
bad_map = {**base_map, "listen_s": 3, "topics": [
    {"topic": "plant/pump1/old",     "variable": "flow_m3h", "unit": "m³/h"},                 # retained, no own time
    {"topic": "plant/pump1/garbage", "variable": "kw", "unit": "kW"},                          # not a number
    {"topic": "plant/pump1/partial", "json_path": "head.m", "variable": "head_m", "unit": "m"},  # JSON without the field
    {"topic": "plant/pump1/silent",  "variable": "vibration_mm_s", "unit": "mm/s"},           # nobody publishes it
]}
publish([("plant/pump1/old", "99.9")], retain=True).join()            # the broker KEEPS it, from "days ago"
th = publish([("plant/pump1/garbage", "ERR"), ("plant/pump1/partial", json.dumps({"head": {}}))], delay=1.5)
ev2, _res2, sk2 = c.run_once(cfg, bad_map)
th.join()
text = " | ".join(sk2)
check("a retained message without its own time is skipped and named (it could be old)",
      any("old" in s and "retained" in s for s in sk2), text)
check("a payload that is not a number is skipped and named, never sent as zero",
      any("garbage" in s and "not a number" in s for s in sk2), text)
check("a JSON payload without the field is skipped and named", any("partial" in s and "no field" in s for s in sk2), text)
check("a topic nobody published is named, not invented", any("silent" in s for s in sk2), text)
check("none of the four produced an event", ev2 == [], str(ev2))

# 3 · a retained message that CARRIES its own time is read at that time (pure parsing: nothing is sent)
v, when, problem = c.parse_payload(json.dumps({"t": 62.3, "at": "2026-01-02T03:04:05Z"}).encode(),
                                   {"json_path": "t", "ts_path": "at"})
check("a payload's own ISO time is kept as the event time",
      problem is None and v == 62.3 and abs(when - datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).timestamp()) < 1)
v2, when2, _p = c.parse_payload(json.dumps({"t": 1, "at": 1767323045123}).encode(), {"json_path": "t", "ts_path": "at"})
check("an epoch in milliseconds is read as milliseconds", abs(when2 - 1767323045.123) < 1e-3, f"{when2}")
check("a boolean payload travels as 0/1", c.parse_payload(b"true", {})[0] == 1 and c.parse_payload(b"false", {})[0] == 0)

# 4 · a broker we cannot get into is NAMED, and the secret is not in what is shown
secret = "pw-" + "q" * 20 + "-test"     # built at run time: this file holds no credential-shaped string
os.environ["MQTT_USERNAME"], os.environ["MQTT_PASSWORD"] = "nobody", secret
silent = {**base_map, "broker": {"host": "127.0.0.1", "port": PORT_SILENT}, "listen_s": 2}
ev4, _res4, sk4 = c.run_once(cfg, silent)
closed = {**base_map, "broker": {"host": "127.0.0.1", "port": PORT_CLOSED}, "listen_s": 2}
ev4b, _res4b, sk4b = c.run_once(cfg, closed)
for k in ("MQTT_USERNAME", "MQTT_PASSWORD"):
    os.environ.pop(k, None)
check("a server that accepts the connection and never answers is named 'never connected', not 'the plant published nothing'",
      any("never connected" in s for s in sk4), str(sk4[:1]))
check("a port with nothing listening is named", any("could not reach" in s for s in sk4b), str(sk4b[:1]))
check("...and neither the password nor the Wertek key is in anything shown",
      secret not in " ".join(sk4 + sk4b) and cfg["key"] not in " ".join(sk4 + sk4b) and ev4 == [] and ev4b == [])

# 5 · a wrong unit declared in the map is Wertek's to refuse: 406, and no conversion
time.sleep(1)
m5 = {**base_map, "listen_s": 3, "topics": [{"topic": "plant/pump1/flow", "variable": "flow_m3h", "unit": "L/s"}]}
th = publish([("plant/pump1/flow", "412.5")], delay=1.2)
ev5, res5, _ = c.run_once(cfg, m5)
th.join()
code5 = codes_of(ev5, res5)[0] if ev5 else None
check("a wrong unit is answered 406 (no conversion)", code5 == 406, f"c={code5}")

for b in brokers:
    asyncio.run_coroutine_threadsafe(b.shutdown(), loop)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
