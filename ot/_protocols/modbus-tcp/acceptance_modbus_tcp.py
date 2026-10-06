"""ACCEPTANCE for `ot/_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md`.

Starts a Modbus TCP simulator on this machine that plays the instruments of a PUMP, runs the connector
against it, sends to a real Wertek organisation and prints what came back, event by event.
It never prints the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test pump asset>
    python acceptance_modbus_tcp.py

The five variables are the ones the pump panel reads (flow_m3h, head_m, kw, seal_temp_c, vibration_mm_s):
a variable's `key` is what ties it to the panel, and the panel labels it with the CHANNEL's unit and does not
convert, so the unit declared here must be exactly the channel's. The hydraulic efficiency is not sent: the
panel derives it from flow, head and power.

Needs: pymodbus. Exit code 0 only when every expected answer was observed.
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
import modbus_to_wertek as c  # noqa: E402
import wertek_send as w  # noqa: E402

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext  # noqa: E402
from pymodbus.server import ModbusTcpServer  # noqa: E402

cfg = w.config()
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "pump_process")

# the pump panel's channels (core/asset_intelligence/channels.py): key == channel name; unit == channel unit.
# These are the variables of the `pump` template the system offers when a position is designated
# (core/canonical_dictionary/pump.py); a backend test keeps the template and the panel in step.
VARS = [  # key, contract unit (the panel's own), symbol shown, simulated raw register (x0.1)
    ("flow_m3h",       "m³/h", "m³/h", 4125),   # 412.5 m³/h
    ("head_m",         "m",    "m",     852),   # 85.2 m
    ("kw",             "kW",   "kW",   1184),   # 118.4 kW
    ("seal_temp_c",    "°C",   "°C",    623),   # 62.3 °C
    ("vibration_mm_s", "mm/s", "mm/s",   28),   # 2.8 mm/s
]
SPEC = {
    "code": cfg["position"], "name": "pump process variables (wertek-integrations acceptance)",
    "component": "pump",
    "variables": [{"key": k, "unit": u, "unit_symbol": s, "kind": "gauge"} for k, u, s, _ in VARS],
    "cadence_seconds": 60, "report_mode": "sampled",
}


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
loop = asyncio.new_event_loop()
server_box: dict = {}


async def _run_server():
    # pymodbus builds the server on the running loop, so it must be created INSIDE one.
    block = ModbusSequentialDataBlock(0, [0] * 200)
    # pymodbus' datastore adds 1 to the address a client asks for (the classic "1-based" quirk of the
    # simulator): to serve registers 100..104 to a client that asks for 100..104, store them at 101..105.
    block.setValues(101, [raw for *_, raw in VARS])
    ctx = ModbusServerContext(devices=ModbusDeviceContext(hr=block), single=True)
    srv = ModbusTcpServer(ctx, address=("127.0.0.1", PORT))
    server_box["srv"] = srv
    await srv.serve_forever()


def serve():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_server())
    except Exception as e:                              # shutdown cancels serve_forever: expected
        server_box["ended"] = type(e).__name__


t = threading.Thread(target=serve, daemon=True)
t.start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
        break
    except OSError:
        time.sleep(0.1)
else:
    sys.exit("the local Modbus simulator did not start")

print(f"simulator: 127.0.0.1:{PORT} · registers 100..104 = {[raw for *_, raw in VARS]}")
pos = w.ensure_position(cfg, SPEC)
print("position:", cfg["position"], "· adapter", pos["assignment"]["adapter"], "· covered", pos["covered"],
      "· variables", [v["key"] + "[" + str(v.get("unit")) + "]" for v in pos["variables"]])

base_map = {
    "device": {"host": "127.0.0.1", "port": PORT, "unit_id": 1, "address_base": 0, "word_order": "big"},
    "position": cfg["position"],
    "registers": [{"address": 100 + i, "type": "int16", "scale": 0.1, "variable": k, "unit": u}
                  for i, (k, u, _s, _r) in enumerate(VARS)],
}

ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'OK ' if cond else 'BAD'} {label} {detail}")


def codes_of(events, results):
    return [results.get(e["event_id"], {}).get("c") for e in events]


# 1 · the happy path: five registers -> five events, each answered 100 (stored)
events, results, skipped = c.run_once(cfg, base_map)
codes = codes_of(events, results)
if 504 in codes:   # a run happened less than a cadence ago: wait it out and prove the STORE once
    wait = int(pos["assignment"].get("cadence_seconds") or 60) + 2
    print(f"run 1 answered 504 (inside the cadence): waiting {wait} s, then sending again")
    time.sleep(wait)
    events, results, skipped = c.run_once(cfg, base_map)
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", {k: got.get(k) for k, *_ in VARS}, codes)
check("five registers become five events", len(events) == 5)
check("values decoded with their scale (x0.1)",
      all(abs(got.get(k, -1) - raw / 10) < 1e-9 for k, _u, _s, raw in VARS))
check("all five answered 100 (stored)", codes == [100] * 5, str(codes))

# 2 · a register that cannot be read is skipped and NAMED; nothing is sent in its place
m2 = {**base_map, "registers": base_map["registers"] + [
    {"address": 500, "type": "int16", "variable": "kw", "unit": "kW"}]}   # address not served
time.sleep(int(pos["assignment"].get("cadence_seconds") or 60) + 2)        # let the gate open again
events2, results2, skipped2 = c.run_once(cfg, m2)
check("an unreadable register is skipped, not sent as zero", len(events2) == 5 and len(skipped2) == 1, str(skipped2))

# 3 · a wrong unit declared in the map is Wertek's to refuse: 406, and no conversion
m3 = {**base_map, "registers": [{"address": 100, "type": "int16", "scale": 0.1, "variable": "flow_m3h", "unit": "L/s"}]}
events3, results3, _ = c.run_once(cfg, m3)
code3 = codes_of(events3, results3)[0] if events3 else None
check("a wrong unit is answered 406 (no conversion)", code3 == 406, f"c={code3}")

# 4 · the derived channel is computed by the panel, never sent: not in the contract -> 405
m4 = {**base_map, "registers": [{"address": 100, "type": "int16", "variable": "hydraulic_efficiency_pct", "unit": "%"}]}
events4, results4, _ = c.run_once(cfg, m4)
code4 = codes_of(events4, results4)[0] if events4 else None
check("the derived hydraulic efficiency is not a contract variable: 405", code4 == 405, f"c={code4}")

# 5 · decoding of 32-bit values and word order, without any network
check("float32 big word order", abs(c.decode([0x41BC, 0x0000], "float32", "big") - 23.5) < 1e-6)
check("float32 little word order", abs(c.decode([0x0000, 0x41BC], "float32", "little") - 23.5) < 1e-6)
check("int16 negative", c.decode([0xFFFF], "int16") == -1)

srv = server_box.get("srv")
if srv:
    asyncio.run_coroutine_threadsafe(srv.shutdown(), loop)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
