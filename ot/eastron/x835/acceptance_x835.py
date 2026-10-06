"""ACCEPTANCE for `ot/eastron/x835/eastron-x835-to-a-designated-position.md`.

Starts a Modbus TCP simulator that plays an Eastron X835 (input registers, float32, the manual's addresses, and a HOLDING
register that says which energy prefix the meter is set to), runs the Modbus connector with `x835_map.json` against it,
sends to a real Wertek organisation and prints what came back, event by event. It never prints the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test asset>
    python acceptance_x835.py

Variable names avoid the ones the backend routes to the energy-meter path (`power`, `energy`, `frequency`, `power_factor`...).

Needs: pymodbus. Exit code 0 only when every expected answer was observed.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_protocols" / "modbus-tcp"))
sys.path.insert(0, str(HERE.parents[1] / "_common"))
import modbus_to_wertek as c  # noqa: E402
import wertek_send as w  # noqa: E402

from pymodbus.client import ModbusTcpClient  # noqa: E402
from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext  # noqa: E402
from pymodbus.server import ModbusTcpServer  # noqa: E402

cfg = w.config()
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "meter_x835")
MAP = json.loads((HERE / "x835_map.json").read_text(encoding="utf-8"))

RAW = {0: 126.4, 2: 127.1, 4: 125.9, 46: 11.4, 52: 3360.0, 62: 0.91, 70: 60.01, 72: 15234.5}     # W for power
EXPECT = {"voltage_l1": 126.4, "voltage_l2": 127.1, "voltage_l3": 125.9, "current_avg": 11.4, "power_kw": 3.36,
          "pf_total": 0.91, "frequency_hz": 60.01, "energy_import_kwh": 15234.5}
SPEC = {
    "code": cfg["position"], "name": "Eastron X835 (wertek-integrations acceptance)", "component": "energy_meter",
    "variables": [{"key": r["variable"], "unit": r["unit"], "unit_symbol": r["unit"],
                   "kind": "counter" if r["variable"] == "energy_import_kwh" else "gauge"} for r in MAP["registers"]],
    "cadence_seconds": 60, "report_mode": "sampled",
}
PREFIX_ADDR = MAP["guards"][0]["address"]


def f32_words(x: float) -> list[int]:
    b = struct.pack(">f", x)
    return [int.from_bytes(b[:2], "big"), int.from_bytes(b[2:], "big")]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
loop = asyncio.new_event_loop()
box: dict = {}


async def _run_server():
    ir = ModbusSequentialDataBlock(0, [0] * 200)
    hr = ModbusSequentialDataBlock(0, [0] * 200)
    # pymodbus' datastore adds 1 to the address a client asks for: to serve register N, store it at N+1.
    for addr, val in RAW.items():
        ir.setValues(addr + 1, f32_words(val))
    hr.setValues(PREFIX_ADDR + 1, f32_words(0.0))             # the meter is set to prefix k (kWh)
    box["hr"] = hr
    ctx = ModbusServerContext(devices=ModbusDeviceContext(ir=ir, hr=hr), single=True)
    srv = ModbusTcpServer(ctx, address=("127.0.0.1", PORT))
    box["srv"] = srv
    await srv.serve_forever()


def serve():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_server())
    except Exception:                                   # shutdown cancels serve_forever: expected
        pass


threading.Thread(target=serve, daemon=True).start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
        break
    except OSError:
        time.sleep(0.1)
else:
    sys.exit("the local Modbus simulator did not start")
time.sleep(0.3)

print(f"simulator: 127.0.0.1:{PORT} · X835 input registers {sorted(RAW)} · holding register {PREFIX_ADDR} = energy prefix")
pos = w.ensure_position(cfg, SPEC)
print("position:", cfg["position"], "· adapter", pos["assignment"]["adapter"], "· covered", pos["covered"],
      "· variables", [v["key"] + "[" + str(v.get("unit")) + "]" for v in pos["variables"]])

base_map = {**MAP, "device": {**MAP["device"], "host": "127.0.0.1", "port": PORT}, "position": cfg["position"]}
ok = True


def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  {'OK ' if cond else 'BAD'} {label} {detail}")


def codes_of(events, results):
    return [results.get(e["event_id"], {}).get("c") for e in events]


cadence = int(pos["assignment"].get("cadence_seconds") or 60)

# 1 · prefix k (the guard holds): eight input registers -> eight events, all stored
events, results, skipped = c.run_once(cfg, base_map)
codes = codes_of(events, results)
if 504 in codes:
    print(f"run 1 answered 504 (inside the cadence): waiting {cadence + 2} s, then sending again")
    time.sleep(cadence + 2)
    events, results, skipped = c.run_once(cfg, base_map)
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", got, codes)
check("with the prefix at k, eight registers become eight events", len(events) == 8 and skipped == [], str(skipped))
check("values decoded as the meter published them (power W -> kW by scale)",
      all(abs(got.get(k, -1) - v) < 1e-3 for k, v in EXPECT.items()), str(got))
check("all eight answered 100 (stored)", codes == [100] * 8, str(codes))

# 2 · READ ONLY from here (nothing is sent): the guard is the whole point of this recipe
probe = ModbusTcpClient("127.0.0.1", port=PORT, timeout=3)
probe.connect()
box["hr"].setValues(PREFIX_ADDR + 1, f32_words(1.0))                # someone sets the meter to prefix M (MWh)
rd, sk = c.read_values(probe, base_map)
names = {x["variable"] for x in rd}
check("with the prefix at M, the energy value is NOT read (it would be 1000 times off)",
      "energy_import_kwh" not in names and any("energy_import_kwh" in s and "guard" in s for s in sk), str(sk))
check("...and the other seven registers are still read", len(rd) == 7, str(sorted(names)))
check("the skip message says what the meter reads and what the map expects",
      any("reads 1" in s and "expects 0" in s for s in sk), str(sk))

box["hr"].setValues(PREFIX_ADDR + 1, f32_words(0.0))                # back to k
rd2, sk2 = c.read_values(probe, base_map)
check("with the prefix back at k the energy value is read again", len(rd2) == 8 and sk2 == [], str(sk2))

broken = {**base_map, "guards": [{**base_map["guards"][0], "address": 500}]}      # a guard the meter cannot answer
rd3, sk3 = c.read_values(probe, broken)
check("a guard that cannot be read FAILS CLOSED: the energy value is not sent",
      "energy_import_kwh" not in {x["variable"] for x in rd3} and any("could not be read" in s for s in sk3), str(sk3))
probe.close()

# 3 · a wrong unit declared in the map is Wertek's to refuse: 406, and no conversion
time.sleep(1)
m4 = {**base_map, "registers": [{**base_map["registers"][4], "unit": "W"}]}
ev4, r4, _ = c.run_once(cfg, m4)
code4 = codes_of(ev4, r4)[0] if ev4 else None
check("power declared in W against a kW contract is answered 406 (no conversion)", code4 == 406, f"c={code4}")

srv = box.get("srv")
if srv:
    asyncio.run_coroutine_threadsafe(srv.shutdown(), loop)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
