# Read a Carlo Gavazzi EM340 energy meter and send it to a designated position

**Who this is for:** you have a **Carlo Gavazzi EM340** (three-phase energy meter, RS485 Modbus RTU) behind an RS485-to-Ethernet
converter, and you want Wertek to keep its readings as part of an asset's history.

**What it is not for:** replacing the **Energy Gateway** that already feeds Wertek's energy module (a different door, with its own
meter registry and license limits: see the Eastron SDM630 recipe, "Three doors", and
[`docs/ENERGY_METER_DOOR.md`](../../../docs/ENERGY_METER_DOOR.md)), writing to the meter, or reading its
harmonics, demand or tariffs.

## The idea, in one paragraph

An EM340 does **not** publish IEEE floats. It publishes **integers with a scale factor** (volts times 10, amperes times 1000,
watts times 10…), and its 32-bit values put the **least significant word first**. A map that treated it like an SDM630 would
read plausible numbers that are wrong by orders of magnitude. This recipe reuses the Modbus connector of
[`../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md`](../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md)
and the send half verified in
[`../../iaes/asset-measurement-to-a-designated-position.md`](../../iaes/asset-measurement-to-a-designated-position.md).
You write a map; this recipe never guesses a unit, a scale or a word order.

## What this meter's map must declare

1. **Integer types and scale factors.** `int32` for most values and `int16` (**one** register) for power factor and frequency.
   The scale turns the raw integer into the declared unit: voltage `0.1`, current `0.001`, energy `0.1`, power factor `0.001`,
   frequency `0.1`.
2. **Word order `little`** (least significant word first) for the 32-bit values, from the manufacturer's protocol (v2 rev17).
   It is declared in `device.word_order` and the connector **refuses** a 32-bit value without it. Read the wrong way, a voltage
   of 231.4 V becomes 15,165,030 V: not an error, a number. A one-register `int16` needs no word order.
3. **Signs.** Exported power is negative in these integers (two's complement, 32 and 16 bit). The acceptance proves the decoding;
   what Wertek does with a negative value for a given variable is the position contract's business, not this recipe's.
4. **Power in kW.** The register holds watts times 10; the map declares kW with `scale: 0.0001` (0.1 for the factor, 0.001 for
   kilo). Declaring `W` against a `kW` contract is answered `406`.

Two traps shared with the other energy recipes: the ingest endpoint routes by the variable's **exact name**, so this map uses
`pf_total` and `frequency_hz` and never `power_factor` or `frequency` (those go to the energy-meter path, not your position); and
a position holds **at most 8 variables**: this map is exactly eight.

## Steps

1. **Edit the map** (`em340_map.json`): `device.host` and `unit_id` for your converter; addresses are **0-based**
   (`address_base: 0`) as in the manual, so set `address_base` if your converter counts from 1.
2. **Give the program its credentials from the environment**, never from the map or the command line
   (`../../../docs/API_KEY_HANDLING.md`): `WERTEK_API_KEY`, `WERTEK_ASSET_ID`.
3. **Run it** (the position is designated, or completed, the first time):

   ```
   pip install pymodbus
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/carlo-gavazzi/em340/em340_map.json --once
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/carlo-gavazzi/em340/em340_map.json --interval 60     # loop
   ```

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         a Carlo Gavazzi EM340 reachable by Modbus TCP, and the JSON map em340_map.json written by a person: per
              register the function (input), address, type (int32 or int16), scale, the Wertek variable key and its unit
OUTPUT        one IAES 2.0 `asset.measurement` per readable register, sent to POST /iaes/ingest to the position
              `meter_em340` of the asset; one answer per event (GET /iaes/schema/codes)
MAPPING       register -> variable of the position's contract. Voltage V (x0.1) · current A (x0.001) · power W*10 ->
              kW (x0.0001) · power factor 1 (x0.001, INT16) · frequency Hz (x0.1, INT16) · imported active energy kWh
              (x0.1, kind counter)
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the value as the meter
              published it, after the declared scale · the sign · that an unreadable register is skipped, never sent as zero
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable from
              Settings -> API keys) · env WERTEK_ASSET_ID. Never in the map, on a command line, in a URL or in a log.
DO NOT INFER  · the word order (declared per device; reversing it gives a plausible wrong number)
              · integer versus float: this meter publishes integers with a scale factor
              · the scale factor of each register: declare it from the manual
              · function 03 vs 04: this map declares 04; whether your converter or firmware also answers 03 is not
                checked here
              · the address base of YOUR converter (0 or 1)
              · the CT/VT ratio configured in the meter: not verified here whether the registers report primary or
                secondary-side values; read it from the meter's setup before trusting current and power
              · the meaning of a negative power or power factor for YOUR contract
              · the models that publish the high-resolution energy registers (not used by this map)
              · the variable NAMES that are routed to the energy door (see the SDM630 recipe)
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
IDEMPOTENCY   re-sending the SAME event id is stored once (101). A second read inside the cadence is answered 504 and
              dropped: an unchanged read is not a new reading.
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/carlo-gavazzi/em340/acceptance_em340.py must
              print one OK line per check and end in `RESULT: PASS`: eight integer registers -> eight events decoded with
              the manual's scale factors -> all answered 100 · a 32-bit value read with the word order reversed is not an
              error and not the right number · a 32-bit value without word_order is refused · a one-register INT16 needs
              none · an unserved register is skipped and named · a negative INT32 (least significant word first) and a
              negative INT16 decode · power in W against a kW contract -> 406.
              What it does NOT see: a real EM340, a real RS485 converter, the CT/VT ratio of a real installation, and
              how the values look in the app.
STATUS        verified 2026-10-06 · against api.wertek.ai (demo organisation, a demo asset) with a pymodbus simulator of
              the EM340 register map · PASS. The addresses, scale factors and word order come from the manufacturer's
              EM340 communication protocol v2 rev17 (50 of 50 registers of the map checked against it; this map uses 8).
              NOT verified on a real EM340.
```

## Credentials

The meter has no credentials in this recipe (Modbus TCP is unauthenticated: put it on a network you control). The Wertek key is
the only secret, and it is environment-only.

## Verification report (2026-10-06)

```
simulator: EM340 integer registers [0, 2, 4, 12, 40, 49, 51, 52] (32-bit values: least significant word first)
position: meter_em340 · adapter iaes · covered True · 8 variables
run 1: voltage_l1 231.4 V · voltage_l2 229.8 V · voltage_l3 232.1 V · current_l1 12.3 A · power_kw 8.25 kW
       pf_total 0.93 · frequency_hz 60.0 Hz · energy_import_kwh 15234.5 kWh -> [100 x 8]
  OK  eight integer registers become eight events
  OK  values decoded with the manual's scale factors
  OK  all eight answered 100 (stored)
  OK  a 32-bit value read with the word order reversed is NOT an error and NOT the right number   (reads 15165030.4)
  OK  a 32-bit value without device.word_order is refused
  OK  a one-register INT16 needs no word order
  OK  an unserved register is skipped and named, the other eight are still read
  OK  a negative INT32 with the least significant word first (exported power)
  OK  a negative INT16 (an exported power factor)
  OK  power declared in W against a kW contract is answered 406 (no conversion)
RESULT: PASS
```

The values above are **simulated**: they were written to a demo asset and mean nothing physical.
