# Read a Modbus TCP device and send it to a designated position

**Who this is for:** you have a pump, drive, meter or sensor that answers **Modbus TCP**, and you want
Wertek to keep what it measures as part of the asset's history, and to fill the asset's panel.

**What it is not for:** Modbus RTU over serial (no TCP gateway), writing to a device (this recipe only
reads), waveforms or spectra (arrays do not travel in an event: answer `409`), and equipment Wertek already
reads through a kit or gateway (`410`).

## The idea, in one paragraph

Wertek does not accept "a reading". It accepts a reading **for a variable of a position someone designated on
an asset**, in the unit the position declared. Modbus gives you neither names nor units: only register
numbers and integers. So the recipe has one job: **a map you write**, saying which register is which
variable, how to decode it and in what unit. The program reads the registers, decodes them with your map,
and sends each as an IAES `asset.measurement` through the send half already verified in
[`../../iaes/asset-measurement-to-a-designated-position.md`](../../iaes/asset-measurement-to-a-designated-position.md).
A register that cannot be read is **skipped and named**, never sent as zero.

## For a pump: the variable `key` is what fills the panel

The pump panel finds a reading by `key == channel name`, and labels it with the **channel's** unit, without
converting. So for a pump use these keys and exactly these units, or the value is stored and never shown (or
shown under the wrong label):

| `key` | unit | what |
|---|---|---|
| `flow_m3h` | `m³/h` | volumetric flow |
| `head_m` | `m` | pump head |
| `kw` | `kW` | active power drawn |
| `pf` | `1` | power factor |
| `vibration_mm_s` | `mm/s` | RMS vibration velocity |
| `bearing_temp_c` | `°C` | bearing temperature |
| `winding_temp_c` | `°C` | motor winding temperature |
| `seal_temp_c` | `°C` | seal temperature |

These eight are the `pump` template the system offers when you designate a position. The panel's resolver reads all eight, but its layout **draws six tiles today** (hydraulic efficiency, flow, head, power, seal temperature, vibration): `pf`, `bearing_temp_c` and `winding_temp_c` are stored and read, and no tile shows them yet (their place is the *Drive Motor* stage, which wants a sub-asset of type `motor`). **The hydraulic
efficiency is not sent**: the panel derives it from `flow_m3h`, `head_m` and `kw` (sending it is answered
`405`). The panel only shows readings younger than **300 s**, so send at least every ~4 minutes if you want it
to stay filled.

One position is one device (the billing unit). A pump has several instruments: designate one position per
instrument and map only what that instrument measures.

## Steps

1. **Write the map** (`example_pump_map.json`): `device` (host, port, unit id, **address base**, **word order**)
   and `registers` (address, type, scale, offset, `variable`, `unit`).
2. **Designate the position** if it is not in the contract yet (see the first recipe, step 2). The map's
   `position` is the code.
3. **Run it**, with the key in the environment (never on the command line, `../../../docs/API_KEY_HANDLING.md`):

   ```
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map my_map.json --once
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map my_map.json --interval 60     # loop
   ```

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         a Modbus TCP device (holding registers by function 03, or input registers by function 04, declared per
              register with `function`) and a JSON register map written by a person: address, type (int16 uint16 int32
              uint32 float32 uint64 float64), scale, offset, variable key, unit. A value that spans several registers
              REQUIRES `device.word_order` ("big"|"little"): it is refused without it, never defaulted.
              Optional `guards`: a register that must hold a known value (an energy prefix, a scaling mode) for the
              variables in `applies_to` to be sent; if it differs, or cannot be read, those variables are skipped and
              named (fails closed)
OUTPUT        one IAES 2.0 `asset.measurement` per readable register, sent to POST /iaes/ingest; one answer
              per event from the ack catalogue (GET /iaes/schema/codes)
MAPPING       register -> variable: written in the map, never inferred. The variable keys and units are those
              of the position's contract (GET /iaes/assets/{asset}/measurement-points). Booleans travel as 0/1
              (`value_conventions` of the contract). For a pump the keys are the panel's channels (table above).
PRESERVE      the unit declared in the contract (it is compared, not converted: 406 on mismatch) · the event
              time = the time of the read · the same event_id when you RETRY a send (answered 101, stored once)
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry,
              revocable from Settings -> API keys) · env WERTEK_ASSET_ID. Never a literal, never printed.
DO NOT INFER  · the ADDRESS BASE: vendor manuals number registers from 0 or from 1 and the protocol does
                not say which; set `address_base` from the manual, do not guess
              · the WORD ORDER of 32-bit values and floats ("big" = high word first) · the scale, the offset
                and the UNIT of every register: the device sends integers only
              · the unit id (slave id) and whether the device wants a gateway in between
              · which instrument each register belongs to, hence how many positions to designate (billing)
              · what to do when a device is unreachable: this recipe sends nothing and says so; whether you
                want a buffer or an alarm is yours to decide
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
IDEMPOTENCY   running twice sends two readings (new event ids) -> the second is answered 504 if it is inside the
              cadence. Re-sending the SAME event id is stored once (101).
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/_protocols/modbus-tcp/acceptance_modbus_tcp.py
              must print one OK line per check and end in `RESULT: PASS`: five registers -> five events decoded
              with their scale -> all answered 100 · an unreadable register is skipped and named (not sent) ·
              a wrong unit -> 406 · the derived efficiency -> 405 · float32 and negative decoding.
              What it does NOT see: that the values reached the asset's panel (open the asset's Operation tab
              within 300 s of the last send), and any real device (it runs against a simulator).
STATUS        verified 2026-10-05 · against api.wertek.ai (demo organisation, asset AST_E3CF6A82, position
              pump_process) with a pymodbus 3.11.4 simulator on localhost · PASS · the five variables were then
              read back from the store with the panel's own conditions (fresh, quality good, not historical,
              data class production), and the asset's Operation tab was seen by a person showing flow 412.5 m³/h,
              head 85.2 m, power 118.4 kW, seal 62.3 °C, vibration 2.8 mm/s and a derived hydraulic efficiency of
              80.9 % (the value predicted from the panel's formula before looking). Not verified: a real Modbus device.
```

## Credentials

Never write the key into the map, a script or a log. Load it into the session as described in
[`docs/API_KEY_HANDLING.md`](../../../docs/API_KEY_HANDLING.md). Use a key scoped to one organisation, to the one
asset you are connecting, with an expiry.

## Verification report (2026-10-05)

Acceptance run against the demo organisation, simulator at `127.0.0.1`, registers 100..104 =
`[4125, 852, 1184, 623, 28]` (scale 0.1):

```
position: pump_process · adapter iaes · covered True · variables ['flow_m3h[m³/h]', 'head_m[m]', 'kw[kW]', 'seal_temp_c[°C]', 'vibration_mm_s[mm/s]']
run 1: {'flow_m3h': 412.5, 'head_m': 85.2, 'kw': 118.4, 'seal_temp_c': 62.3, 'vibration_mm_s': 2.8} [100, 100, 100, 100, 100]
  OK  five registers become five events
  OK  values decoded with their scale (x0.1)
  OK  all five answered 100 (stored)
  OK  an unreadable register is skipped, not sent as zero ['kw@500: modbus error']
  OK  a wrong unit is answered 406 (no conversion)
  OK  the derived hydraulic efficiency is not a contract variable: 405
  OK  float32 big word order
  OK  float32 little word order
  OK  int16 negative
RESULT: PASS
```

Two things the first runs taught, kept here because the next person will meet them:

- A batch in which **no** event is accepted answers **HTTP 422**, but it still carries one answer per event
  (for example `504`, faster than the cadence). It is an answer, not a failure: read `results`.
- The pymodbus **simulator** serves a register one address higher than a client asks for (its datastore is
  1-based). That is the simulator, not Modbus, and it is the same trap as the address base above.
