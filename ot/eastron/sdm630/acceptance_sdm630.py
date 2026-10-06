"""ACCEPTANCE for `ot/eastron/sdm630/eastron-sdm630-to-a-designated-position.md`.

Starts a Modbus TCP simulator that plays an Eastron SDM630 (input registers, float32, the manual's addresses), runs the
Modbus connector with `sdm630_map.json` against it, sends to a real Wertek organisation and prints what came back,
event by event. It never prints the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test asset>
    python acceptance_sdm630.py

It uses the ENERGY-NAMED variables of a position (`power_kw`, `voltage_l1`, ...) on an ordinary asset, through the
position contract. It never sends a variable named exactly `power`, `energy`, `frequency`, `power_factor`, `voltage` or
`current`: the backend routes those names to the energy-meter path (see the recipe, "A name that changes the road").

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

from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext  # noqa: E402
from pymodbus.server import ModbusTcpServer  # noqa: E402

cfg = w.config()
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "meter_sdm630")
MAP = json.loads((HERE / "sdm630_map.json").read_text(encoding="utf-8"))

# what the simulated meter "measures": raw value as the meter stores it (W for power), by address
RAW = {0: 231.4, 2: 229.8, 4: 232.1, 46: 12.27, 52: 8250.0, 62: 0.93, 70: 60.01, 72: 15234.5}
EXPECT = {"voltage_l1": 231.4, "voltage_l2": 229.8, "voltage_l3": 232.1, "current_avg": 12.27,
          "power_kw": 8.25, "pf_total": 0.93, "frequency_hz": 60.01, "energy_import_kwh": 15234.5}
KIND = {"energy_import_kwh": "counter"}
SPEC = {
    "code": cfg["position"], "name": "Eastron SDM630 (wertek-integrations acceptance)", "component": "energy_meter",
    "variables": [{"key": r["variable"], "unit": r["unit"], "unit_symbol": r["unit"],
                   "kind": KIND.get(r["variable"], "gauge")} for r in MAP["registers"]],
    "cadence_seconds": 60, "report_mode": "sampled",
}


def f32_words(x: float, order: str = "big") -> list[int]:
    b = struct.pack(">f", x)
    hi, lo = int.from_bytes(b[:2], "big"), int.from_bytes(b[2:], "big")
    return [hi, lo] if order == "big" else [lo, hi]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


PORT = free_port()
loop = asyncio.new_event_loop()
server_box: dict = {}


async def _run_server():
    block = ModbusSequentialDataBlock(0, [0] * 200)
    # pymodbus' datastore adds 1 to the address a client asks for: to serve register N, store it at N+1.
    for addr, val in RAW.items():
        block.setValues(addr + 1, f32_words(val, "big"))
    # the meter's measurements live in INPUT registers (function 04): the HOLDING table is left empty on purpose,
    ctx = ModbusServerContext(devices=ModbusDeviceContext(ir=block, hr=ModbusSequentialDataBlock(0, [0] * 200)), single=True)
    srv = ModbusTcpServer(ctx, address=("127.0.0.1", PORT))
    server_box["srv"] = srv
    await srv.serve_forever()


def serve():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run_server())
    except Exception as e:                              # shutdown cancels serve_forever: expected
        server_box["ended"] = type(e).__name__


threading.Thread(target=serve, daemon=True).start()
for _ in range(50):
    try:
        socket.create_connection(("127.0.0.1", PORT), timeout=0.2).close()
        break
    except OSError:
        time.sleep(0.1)
else:
    sys.exit("the local Modbus simulator did not start")

print(f"simulator: 127.0.0.1:{PORT} · SDM630 input registers {sorted(RAW)} (float32, most significant word first)")
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

# 1 · the happy path: eight input registers -> eight events, decoded with the manual's addresses, scale and word order
events, results, skipped = c.run_once(cfg, base_map)
codes = codes_of(events, results)
if 504 in codes:   # a run happened less than a cadence ago: wait it out and prove the STORE once
    print(f"run 1 answered 504 (inside the cadence): waiting {cadence + 2} s, then sending again")
    time.sleep(cadence + 2)
    events, results, skipped = c.run_once(cfg, base_map)
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", got, codes)
check("eight input registers become eight events", len(events) == 8 and skipped == [], str(skipped))
check("values decoded as the meter published them (power W -> kW by scale)",
      all(abs(got.get(k, -1) - v) < 1e-3 for k, v in EXPECT.items()))
check("all eight answered 100 (stored)", codes == [100] * 8, str(codes))

# 2 · the HOLDING table of this simulator is empty: asking for the same addresses by function 03 reads zeros, which is
#     exactly why the function is declared per register and never assumed
#     (this probe only READS: nothing is sent to Wertek)
from pymodbus.client import ModbusTcpClient  # noqa: E402

probe = ModbusTcpClient("127.0.0.1", port=PORT, timeout=3)
probe.connect()
m2 = {**base_map, "registers": [{**r, "function": "holding"} for r in base_map["registers"][:1]]}
rd2, _s2 = c.read_values(probe, m2)
check("function 03 on an input-register meter does NOT return the measurement",
      bool(rd2) and rd2[0]["value"] != 231.4, str(rd2))

# 3 · no network: the word order is declared, never defaulted, and the wrong one gives a plausible wrong number
try:
    c.decode(f32_words(231.4), "float32")
    refused = False
except ValueError:
    refused = True
check("a multi-register value without word_order is refused", refused)
swapped = c.decode(f32_words(231.4, "little"), "float32", "big")
check("the wrong word order gives a plausible-looking WRONG number (so it must be declared)",
      abs(swapped - 231.4) > 1 and abs(c.decode(f32_words(231.4, "little"), "float32", "little") - 231.4) < 1e-3,
      f"wrong order reads {swapped:.6g}")

# 4 · float64 over four registers (the PAC3200's energy counters), same declared order
words = [int.from_bytes(struct.pack(">d", 11392716913.556253)[i:i + 2], "big") for i in range(0, 8, 2)]
check("float64 over four registers decodes (big word order)",
      abs(c.decode(words, "float64", "big") - 11392716913.556253) < 1e-3)

# 5 · a register that cannot be read is skipped and NAMED; a wrong unit is Wertek's to refuse (406)
m5 = {**base_map, "registers": base_map["registers"] + [
    {"function": "input", "address": 500, "type": "float32", "variable": "pf_total", "unit": "1"}]}
rd5, s5 = c.read_values(probe, m5)          # read only: an address the meter does not serve
probe.close()
check("an unserved register is skipped and named, the other eight are still read",
      len(rd5) == 8 and len(s5) == 1 and "500" in s5[0], str(s5))
m6 ={**base_map, "registers": [{**base_map["registers"][6], "unit": "W"}]}
ev6, r6, _ = c.run_once(cfg, m6)
code6 = codes_of(ev6, r6)[0] if ev6 else None
check("power declared in W against a kW contract is answered 406 (no conversion)", code6 == 406, f"c={code6}")

srv = server_box.get("srv")
if srv:
    asyncio.run_coroutine_threadsafe(srv.shutdown(), loop)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
