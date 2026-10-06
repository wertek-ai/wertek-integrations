"""ACCEPTANCE for `ot/carlo-gavazzi/em340/carlo-gavazzi-em340-to-a-designated-position.md`.

Starts a Modbus TCP simulator that plays a Carlo Gavazzi EM340 (INTEGER registers with scale factors, 32-bit values with
the LEAST significant word first), runs the Modbus connector with `em340_map.json` against it, sends to a real Wertek
organisation and prints what came back, event by event. It never prints the API key.

    # load the key into the session WITHOUT typing it on a command line (docs/API_KEY_HANDLING.md)
    export WERTEK_ASSET_ID=<your test asset>
    python acceptance_em340.py

It uses ENERGY-NAMED variables of a position (`power_kw`, `voltage_l1`, ...) on an ordinary asset, through the position
contract. It never sends a variable named exactly `power`, `energy`, `frequency` or `power_factor`: the backend routes
those names to the energy-meter path (see the SDM630 recipe, "A name that changes the road").

Needs: pymodbus. Exit code 0 only when every expected answer was observed.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
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
cfg["position"] = os.environ.get("WERTEK_POSITION_CODE", "meter_em340")
MAP = json.loads((HERE / "em340_map.json").read_text(encoding="utf-8"))

# what the simulated meter stores: the RAW integer, by address (V*10, A*1000, W*10, PF*1000, Hz*10, kWh*10)
RAW = {0: (2314, 2), 2: (2298, 2), 4: (2321, 2), 12: (12300, 2), 40: (82500, 2), 49: (930, 1), 51: (600, 1), 52: (152345, 2)}
EXPECT = {"voltage_l1": 231.4, "voltage_l2": 229.8, "voltage_l3": 232.1, "current_l1": 12.3, "power_kw": 8.25,
          "pf_total": 0.93, "frequency_hz": 60.0, "energy_import_kwh": 15234.5}
KIND = {"energy_import_kwh": "counter"}
SPEC = {
    "code": cfg["position"], "name": "Carlo Gavazzi EM340 (wertek-integrations acceptance)", "component": "energy_meter",
    "variables": [{"key": r["variable"], "unit": r["unit"], "unit_symbol": r["unit"],
                   "kind": KIND.get(r["variable"], "gauge")} for r in MAP["registers"]],
    "cadence_seconds": 60, "report_mode": "sampled",
}


def words(value: int, n: int, order: str) -> list[int]:
    """An integer as n 16-bit registers (two's complement). order 'little' = LEAST significant word first."""
    v = value & ((1 << (16 * n)) - 1)
    ws = [(v >> (16 * (n - 1 - i))) & 0xFFFF for i in range(n)]          # most significant first
    return ws if order == "big" else list(reversed(ws))


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
    for addr, (raw, n) in RAW.items():
        block.setValues(addr + 1, words(raw, n, "little"))
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

print(f"simulator: 127.0.0.1:{PORT} · EM340 integer registers {sorted(RAW)} (32-bit values: least significant word first)")
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

# 1 · the happy path: eight integer registers -> eight events, decoded with the manual's scale factors and word order
events, results, skipped = c.run_once(cfg, base_map)
codes = codes_of(events, results)
if 504 in codes:   # a run happened less than a cadence ago: wait it out and prove the STORE once
    print(f"run 1 answered 504 (inside the cadence): waiting {cadence + 2} s, then sending again")
    time.sleep(cadence + 2)
    events, results, skipped = c.run_once(cfg, base_map)
    codes = codes_of(events, results)
got = {e["data"]["measurement_type"]: e["data"]["value"] for e in events}
print("run 1:", got, codes)
check("eight integer registers become eight events", len(events) == 8 and skipped == [], str(skipped))
check("values decoded with the manual's scale factors (V*10, A*1000, W*10 -> kW, PF*1000, Hz*10, kWh*10)",
      all(abs(got.get(k, -1) - v) < 1e-6 for k, v in EXPECT.items()), str(got))
check("all eight answered 100 (stored)", codes == [100] * 8, str(codes))

# 2 · read only (nothing is sent): the word order is declared, and the wrong one is a plausible-looking WRONG number
probe = ModbusTcpClient("127.0.0.1", port=PORT, timeout=3)
probe.connect()
wrong = {**base_map, "device": {**base_map["device"], "word_order": "big"}, "registers": base_map["registers"][:1]}
rd, _s = c.read_values(probe, wrong)
check("a 32-bit value read with the word order reversed is NOT an error and NOT the right number",
      bool(rd) and abs(rd[0]["value"] - 231.4) > 1, str(rd))
missing = {**base_map, "device": {k: v for k, v in base_map["device"].items() if k != "word_order"},
           "registers": base_map["registers"][:1]}
try:
    c.read_values(probe, missing)
    refused = False
except ValueError:
    refused = True
check("a 32-bit value without device.word_order is refused", refused)
# an INT16 spans ONE register: no word order applies, and none is required
one, _s = c.read_values(probe, {**base_map, "device": {k: v for k, v in base_map["device"].items() if k != "word_order"},
                                "registers": [r for r in base_map["registers"] if r["variable"] == "pf_total"]})
check("a one-register INT16 needs no word order", bool(one) and abs(one[0]["value"] - 0.93) < 1e-9, str(one))
m5 = {**base_map, "registers": base_map["registers"] + [
    {"function": "input", "address": 500, "type": "int32", "scale": 0.1, "variable": "voltage_l1", "unit": "V"}]}
rd5, s5 = c.read_values(probe, m5)
probe.close()
check("an unserved register is skipped and named, the other eight are still read",
      len(rd5) == 8 and len(s5) == 1 and "500" in s5[0], str(s5))

# 3 · no network: signs. Export power is NEGATIVE in this meter's integers (two's complement, 32 and 16 bit)
check("a negative INT32 with the least significant word first (exported power)",
      c.decode(words(-82500, 2, "little"), "int32", "little") == -82500)
check("a negative INT16 (an exported power factor)", c.decode(words(-930, 1, "little"), "int16") == -930)

# 4 · a wrong unit declared in the map is Wertek's to refuse: 406, and no conversion
m6 = {**base_map, "registers": [{**base_map["registers"][4], "unit": "W"}]}
ev6, r6, _ = c.run_once(cfg, m6)
code6 = codes_of(ev6, r6)[0] if ev6 else None
check("power declared in W against a kW contract is answered 406 (no conversion)", code6 == 406, f"c={code6}")

srv = server_box.get("srv")
if srv:
    asyncio.run_coroutine_threadsafe(srv.shutdown(), loop)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
