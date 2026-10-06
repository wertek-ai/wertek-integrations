# Read an Eastron SDM630 energy meter and send it to a designated position

**Who this is for:** you have an **Eastron SDM630** (three-phase energy meter, RS485 Modbus RTU) behind an RS485-to-Ethernet
converter, or the SDM630 with a Modbus TCP port, and you want Wertek to keep its readings as part of an asset's history.

**What it is not for:**
- Replacing the **Energy Gateway** that already feeds Wertek's energy module. That is a different door, with its own meter
  registry, license limits and cadence gate. This recipe uses the **position contract** of an ordinary asset (see "Two doors"
  below) and does not touch the energy module.
- Writing to the meter, reading its configuration registers, harmonics, demand or tariffs.

## The idea, in one paragraph

An SDM630 publishes its measurements as **IEEE 754 floats in input registers (Modbus function 04)**, two registers per value.
It carries no names and no units on the wire: **you** write a map that says which register is which Wertek variable and in
which unit, and this recipe never guesses. It reuses the Modbus connector of
[`../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md`](../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md)
(function per register, `float32`/`float64`, a **declared** word order) and the send half verified in
[`../../iaes/asset-measurement-to-a-designated-position.md`](../../iaes/asset-measurement-to-a-designated-position.md).

## Three things about this meter that a map must declare

1. **Function 04, not 03.** The measurements are *input* registers. Asking for the same addresses by function 03 reads
   another table: the acceptance proves it returns something else. The map carries `"function": "input"` per register.
2. **Word order is a setting, not a fact of the model.** The manual's default is *most significant register first*, and the
   meter lets you reverse it. A reversed read is **not** an error: it is a plausible-looking wrong number (a voltage of
   231.4 V read the wrong way is `2.7e+23`, which at least looks wrong; a power factor or a frequency may not). The connector
   therefore **refuses** any multi-register value without `device.word_order`.
3. **Power is in watts.** The register holds W; the map applies `scale: 0.001` and declares the variable in **kW**. Wertek compares
   units and never converts: declaring `W` against a `kW` contract is answered `406`.

## Three doors, and a name that changes the road

Energy can reach Wertek through three doors, and they are not interchangeable:

| Door | For | What it does |
|---|---|---|
| **Energy Gateway** (`/energy/gateway/push`) | a customer's registered energy meter fed by a Wertek gateway, the energy module's screens | meter registry, cadence per meter by the server's clock |
| **IAES energy-meter door** (`/iaes/ingest`, energy names) | a registered energy meter fed by your own device or script, the energy module's screens | the asset id is the meter id; accepted by the **event's own time**, history up to 35 days, one reading per meter and time: [`docs/ENERGY_METER_DOOR.md`](../../../docs/ENERGY_METER_DOOR.md) |
| **IAES position** (`/iaes/ingest`, this recipe) | any asset: a position with variables you designate | the position contract: variable, unit, cadence, one answer per event |

**Trap:** the IAES endpoint routes by the variable's **exact name**. A `measurement_type` equal to `power`, `energy`,
`frequency`, `power_factor`, `voltage`, `current`, `reactive_power`, `thd_voltage` or `thd_current` is sent to the **energy
meter door** (with the asset id used as a meter id), *not* to your position. This map therefore uses `pf_total` and
`frequency_hz` instead of `power_factor` and `frequency`. Pick variable names that are not on that list, unless you mean the
energy door.

## One position holds at most eight variables

The billing policy admits **8 variables per position**: more is answered `422` when you designate. This map has exactly eight
(`voltage_l1`, `voltage_l2`, `voltage_l3`, `current_avg`, `power_kw`, `pf_total`, `frequency_hz`, `energy_import_kwh`). An
SDM630 has about seventy registers; covering more means more positions, and **what a second position for the same physical
meter costs is a commercial question this recipe does not answer**.

## Steps

1. **Edit the map** (`sdm630_map.json`): `device.host`, `unit_id` and, if your meter or converter was configured with the
   registers reversed, `device.word_order`. Addresses are **0-based** (`address_base: 0`), as in the manual; if your converter
   or tool counts from 1, set `address_base` accordingly.
2. **Give the program its credentials from the environment**, never from the map or the command line
   (`../../../docs/API_KEY_HANDLING.md`): `WERTEK_API_KEY`, `WERTEK_ASSET_ID`.
3. **Run it** (the position is designated, or completed, the first time):

   ```
   pip install pymodbus
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/eastron/sdm630/sdm630_map.json --once
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/eastron/sdm630/sdm630_map.json --interval 60     # loop
   ```

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         an Eastron SDM630 reachable by Modbus TCP, and the JSON map sdm630_map.json written by a person: per
              register the function (input), address, type (float32), scale, the Wertek variable key and its unit
OUTPUT        one IAES 2.0 `asset.measurement` per readable register, sent to POST /iaes/ingest to the position
              `meter_sdm630` of the asset; one answer per event (GET /iaes/schema/codes)
MAPPING       register -> variable of the position's contract. Voltage V · current A · power W*0.001 -> kW ·
              power factor 1 (unitless) · frequency Hz · imported active energy kWh (kind counter)
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the value as the meter
              published it, after the declared scale · that an unreadable register is skipped, never sent as zero
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable from
              Settings -> API keys) · env WERTEK_ASSET_ID. Never in the map, on a command line, in a URL or in a log.
DO NOT INFER  · the word order (declared per device; reversing it gives a plausible wrong number)
              · function 03 vs 04 (declared per register)
              · the address base of YOUR converter (0 or 1)
              · the unit and scale of each register (declare them from the manual)
              · whether the energy counters are in kWh: this model's manual publishes kWh; a related model (the X835)
                lets the user choose a k or M prefix on the meter. Check the meter's own setting.
              · the CT/VT ratio configured in the meter: not verified here whether the registers report primary or
                secondary-side values; read it from the meter's setup before trusting current and power
              · the variable NAMES that are routed to the energy door (see "a name that changes the road")
              · what a second position for the same physical meter costs
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
IDEMPOTENCY   re-sending the SAME event id is stored once (101). A second read inside the cadence is answered 504 and
              dropped: an unchanged read is not a new reading.
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/eastron/sdm630/acceptance_sdm630.py must
              print one OK line per check and end in `RESULT: PASS`: eight input registers -> eight events decoded as the
              meter published them (W -> kW) -> all answered 100 · function 03 does NOT return the measurement · a
              multi-register value without word_order is refused · the wrong word order is shown to give a plausible
              wrong number · float64 over four registers decodes · an unserved register is skipped and named · power in
              W against a kW contract -> 406.
              What it does NOT see: a real SDM630, a real RS485 converter, the CT/VT ratio of a real installation, and
              how the values look in the app.
STATUS        verified 2026-10-06 · against api.wertek.ai (demo organisation, a demo asset) with a pymodbus simulator of
              the SDM630 register map · PASS. The addresses, types and function come from the manufacturer's SDM630
              Modbus protocol V1.8 (71 of 71 registers checked against it; this map uses 8). NOT verified on a real SDM630.
```

## Credentials

The meter has no credentials in this recipe (Modbus TCP is unauthenticated: put it on a network you control). The Wertek key
is the only secret, and it is environment-only.

## Verification report (2026-10-06)

```
simulator: SDM630 input registers [0, 2, 4, 46, 52, 62, 70, 72] (float32, most significant word first)
position: meter_sdm630 · adapter iaes · covered True · 8 variables
run 1: voltage_l1 231.4 V · voltage_l2 229.8 V · voltage_l3 232.1 V · current_avg 12.27 A · power_kw 8.25 kW
       pf_total 0.93 · frequency_hz 60.01 Hz · energy_import_kwh 15234.5 kWh -> [100 x 8]
  OK  eight input registers become eight events
  OK  values decoded as the meter published them (power W -> kW by scale)
  OK  all eight answered 100 (stored)
  OK  function 03 on an input-register meter does NOT return the measurement
  OK  a multi-register value without word_order is refused
  OK  the wrong word order gives a plausible-looking WRONG number (so it must be declared)
  OK  float64 over four registers decodes (big word order)
  OK  an unserved register is skipped and named, the other eight are still read
  OK  power declared in W against a kW contract is answered 406 (no conversion)
RESULT: PASS
```

The values above are **simulated**: they were written to a demo asset and mean nothing physical.
