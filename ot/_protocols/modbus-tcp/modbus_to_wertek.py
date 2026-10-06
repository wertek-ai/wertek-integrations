"""Read holding or input registers from a Modbus TCP device and send them to Wertek as IAES measurements.

Recipe: ot/_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md

    # the key comes from the environment, never from this command line (docs/API_KEY_HANDLING.md)
    python modbus_to_wertek.py --map my_map.json --once

A register map says WHICH registers, how to decode them, and the UNIT of each value. Modbus carries no
units and no names: the person who writes the map declares them, and this program never guesses.

Needs: pymodbus (BSD-3-Clause). The send half is ot/_common/wertek_send.py (standard library).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_common"))
import wertek_send as w  # noqa: E402

# type -> (struct format of the value, registers it spans)
TYPES = {"int16": (">h", 1), "uint16": (">H", 1), "int32": (">i", 2), "uint32": (">I", 2), "float32": (">f", 2),
         "uint64": (">Q", 4), "float64": (">d", 4)}


def decode(regs: list[int], typ: str, word_order: str | None = None):
    """Registers -> number. For values that span several registers `word_order` is the order of the 16-bit
    words ("big": most significant word first; "little": reversed). The byte order inside a word is always
    big-endian (Modbus). The word order is a property of the DEVICE (some let you change it), so it is never
    defaulted: a multi-register value without it is refused, because the wrong order is a plausible number."""
    fmt, n = TYPES[typ]
    if len(regs) != n:
        raise ValueError(f"{typ} spans {n} register(s), got {len(regs)}")
    if n > 1 and word_order not in ("big", "little"):
        raise ValueError(f"{typ} spans {n} registers: declare device.word_order as \"big\" or \"little\"")
    words = regs if word_order in (None, "big") else list(reversed(regs))
    raw = b"".join(struct.pack(">H", x) for x in words)
    return struct.unpack(fmt, raw)[0]


def _fetch(client, dev: dict, base: int, fn: str, address: int, n: int):
    """One read. Returns (registers, None) or (None, problem). The problem names the register, never the request."""
    if fn not in ("holding", "input"):   # Modbus function 03 vs 04: a register lives in ONE of the two tables
        return None, "function must be \"holding\" or \"input\""
    read = client.read_input_registers if fn == "input" else client.read_holding_registers
    try:
        rr = read(int(address) - base, count=n, device_id=int(dev.get("unit_id", 1)))
    except Exception as e:  # transport failure: name the exception type, not the secret-bearing request
        return None, type(e).__name__
    if rr.isError():
        return None, "modbus error"
    return list(rr.registers), None


def _blocked_by_guards(client, m: dict, dev: dict, base: int) -> dict[str, str]:
    """PRECONDITIONS: a register that must hold a known value for other registers to mean what the map says
    (an energy unit prefix, a CT ratio, a scaling mode). {variable: why it is not sent}. FAILS CLOSED: a guard that
    cannot be read blocks its variables, because an unchecked prefix is how a value ends up 1000 times off."""
    blocked: dict[str, str] = {}
    for g in m.get("guards", []):
        name = g.get("name", f"{g.get('function', 'holding')}@{g['address']}")
        regs, problem = _fetch(client, dev, base, g.get("function", "holding"), g["address"], TYPES[g["type"]][1])
        if problem:
            why = f"guard '{name}' could not be read ({problem}): nothing that depends on it is sent"
        else:
            got = decode(regs, g["type"], dev.get("word_order"))
            if abs(got - float(g["equals"])) < 1e-6:
                continue
            why = f"guard '{name}' reads {got:g}, the map expects {g['equals']:g}" + (f" ({g['why']})" if g.get("why") else "")
        for variable in g["applies_to"]:
            blocked[variable] = why
    return blocked


def read_values(client, m: dict) -> tuple[list[dict], list[str]]:
    """Read every register of the map. Returns (readings, skipped). A register that cannot be read is
    SKIPPED and named; a zero or a previous value is never sent in its place. A variable whose `guards`
    precondition does not hold is skipped and named too."""
    dev = m["device"]
    base = int(dev.get("address_base", 0))
    readings, skipped = [], []
    blocked = _blocked_by_guards(client, m, dev, base)
    for r in m["registers"]:
        n = TYPES[r["type"]][1]
        if r["variable"] in blocked:
            skipped.append(f"{r['variable']}@{r['address']}: {blocked[r['variable']]}")
            continue
        regs, problem = _fetch(client, dev, base, r.get("function", "holding"), r["address"], n)
        if problem:
            skipped.append(f"{r['variable']}@{r['address']}: {problem}")
            continue
        v = decode(regs, r["type"], dev.get("word_order"))
        v = v * float(r.get("scale", 1)) + float(r.get("offset", 0))
        v = round(v, 6)                 # 62.3, not 62.300000000000004: scaling a float leaves noise
        if r.get("kind") == "boolean":
            v = 1 if v != 0 else 0          # the contract's convention: a boolean travels as 0/1
        readings.append({"variable": r["variable"], "unit": r["unit"], "value": v})
    return readings, skipped


def run_once(cfg: dict, m: dict, client=None) -> tuple[list[dict], dict, list[str]]:
    """One cycle: read, build events, send. Returns (events, results by event_id, skipped)."""
    from pymodbus.client import ModbusTcpClient
    own = client is None
    dev = m["device"]
    client = client or ModbusTcpClient(dev["host"], port=int(dev.get("port", 502)), timeout=float(dev.get("timeout_s", 3)))
    try:
        if own and not client.connect():
            return [], {}, [f"could not connect to {dev['host']}:{dev.get('port', 502)}"]
        readings, skipped = read_values(client, m)
    finally:
        if own:
            client.close()
    corr = str(uuid.uuid4())
    events = [w.event(cfg, x["variable"], x["value"], x["unit"], "wertek_integrations.modbus_tcp", corr) for x in readings]
    results = w.send(cfg, events) if events else {}
    return events, results, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--map", required=True, help="JSON register map")
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
