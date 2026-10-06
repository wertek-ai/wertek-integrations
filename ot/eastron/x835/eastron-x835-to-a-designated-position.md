# Read an Eastron X835 energy meter and send it to a designated position — without trusting its energy prefix

**Who this is for:** you have an **Eastron SMART X835** (or SMARTRAIL X835) three-phase energy meter, RS485 Modbus RTU, behind an
RS485-to-Ethernet converter, and you want Wertek to keep its readings as part of an asset's history.

**What it is not for:** replacing the **Energy Gateway** that feeds Wertek's energy module (a different door: see the Eastron SDM630
recipe, "Three doors", and [`docs/ENERGY_METER_DOOR.md`](../../../docs/ENERGY_METER_DOOR.md)), writing to the meter, or reading its harmonics, demand or tariffs. **It is not a recipe for the Eastron X96:** that
is a different model, and its register document was not available to check this against.

## The idea, in one paragraph

Like the SDM630, the X835 publishes IEEE 754 floats in **input registers (function 04)**, two registers per value, most significant
register first by default. What is different, and the reason this recipe exists, is the **energy registers**: the manual says the
*user* chooses a **k or M prefix** for them, so the same register can mean kWh or MWh depending on a setting in the meter. A map that
declares `kWh` and reads a meter set to `M` sends a number **1000 times too small**, with no error anywhere. The meter exposes that
setting as a holding register, so this recipe **reads it first** and refuses to send the energy value unless it is what the map
declares.

## The trap, and what stops it

| | |
|---|---|
| The setting | holding register 40031, *Energy Units Prefix* (parameter 16, Modbus address 30): **0 = k** (kWh, the default), **1 = M** (MWh) |
| What the map declares | `energy_import_kwh` in **kWh** |
| The guard | `guards[0]`: read address 30, expect `0`; applies to `energy_import_kwh` |
| If the meter is set to M | the energy variable is **skipped and named** («guard 'energy units prefix' reads 1, the map expects 0»); the other seven are sent |
| If the guard cannot be read | **fails closed**: the energy variable is not sent («could not be read») |

The fix for a meter set to M is yours to choose: set the meter back to k, or declare the variable in **MWh** (a different contract
unit; Wertek compares units and answers `406` on a mismatch). The recipe never converts for you.

## Other things this map must declare

1. **Function 04, not 03.** The measurements are input registers; the prefix is a *holding* register (function 03).
2. **Word order** (`device.word_order`): the manual's default is most significant register first, and the meter lets you reverse it with
   its *Register Order* setting. The connector refuses any multi-register value without it, because a reversed read is a plausible wrong number.
3. **Power is in watts**: the map applies `scale: 0.001` and declares **kW**; declaring `W` against a `kW` contract is answered `406`.
4. **Variable names**: the ingest endpoint routes by the variable's exact name, so this map uses `pf_total` and `frequency_hz`, never
   `power_factor` or `frequency` (those go to the energy-meter path, not to your position). A position holds **at most 8 variables**.

## Steps

1. **Edit the map** (`x835_map.json`): `device.host`, `unit_id` and, if the meter's register order was reversed, `word_order`. Addresses are
   0-based as in the manual (`address_base: 0`).
2. **Give the program its credentials from the environment**, never from the map or the command line
   (`../../../docs/API_KEY_HANDLING.md`): `WERTEK_API_KEY`, `WERTEK_ASSET_ID`.
3. **Run it:**

   ```
   pip install pymodbus
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/eastron/x835/x835_map.json --once
   python ot/_protocols/modbus-tcp/modbus_to_wertek.py --map ot/eastron/x835/x835_map.json --interval 60     # loop
   ```

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         an Eastron X835 reachable by Modbus TCP, and the JSON map x835_map.json written by a person: per register the
              function, address, type (float32), scale, the Wertek variable key and its unit; and a `guards` list: a register
              that must hold a known value for another variable to mean what the map says
OUTPUT        one IAES 2.0 `asset.measurement` per readable register whose guard holds, sent to POST /iaes/ingest to the
              position `meter_x835` of the asset; one answer per event (GET /iaes/schema/codes)
MAPPING       register -> variable of the position's contract. Voltage V · average current A · power W*0.001 -> kW ·
              power factor 1 (unitless) · frequency Hz · imported active energy kWh (kind counter, only when the prefix is k)
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the value as the meter published
              it, after the declared scale · that nothing is sent whose meaning depends on a setting we could not confirm
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable from
              Settings -> API keys) · env WERTEK_ASSET_ID. Never in the map, on a command line, in a URL or in a log.
DO NOT INFER  · the energy prefix: read it from the meter (the guard); a map that declares kWh does not make the meter report kWh
              · the word order (declared per device; reversing it gives a plausible wrong number)
              · the type of the prefix register: the manual says every holding parameter occupies two registers and that
                values are IEEE floats; this map reads it as float32 (sin verificar against a real meter)
              · the CT/VT ratio configured in the meter: not verified here whether the registers report primary or
                secondary-side values; read it from the meter's setup before trusting current and power
              · the address base of YOUR converter (0 or 1)
              · what a second position for the same physical meter costs
              · the variable NAMES that are routed to the energy door (see the SDM630 recipe)
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
IDEMPOTENCY   re-sending the SAME event id is stored once (101). A second read inside the cadence is answered 504 and dropped.
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/eastron/x835/acceptance_x835.py must print one OK line
              per check and end in `RESULT: PASS`: with the prefix at k, eight registers -> eight events -> all answered 100 ·
              with the prefix at M the energy value is NOT read and the message says what the meter reads and what the map
              expects, while the other seven are still read · with the prefix back at k it is read again · a guard that cannot
              be read fails closed · power in W against a kW contract -> 406.
              What it does NOT see: a real X835, a real RS485 converter, the real type of the prefix register, the CT/VT ratio of
              a real installation, and how the values look in the app.
STATUS        verified 2026-10-06 · against api.wertek.ai (demo organisation, a demo asset) with a pymodbus simulator of the
              X835 register map · PASS. The eight addresses and the prefix register come from the manufacturer's SMARTRAIL X835
              Modbus protocol (Nov 2014): every address was found in its table. NOT verified on a real X835.
```

## Credentials

The meter has no credentials in this recipe (Modbus TCP is unauthenticated: put it on a network you control). The Wertek key is the
only secret, and it is environment-only.

## Verification report (2026-10-06)

```
simulator: X835 input registers [0, 2, 4, 46, 52, 62, 70, 72] · holding register 30 = energy prefix
position: meter_x835 · adapter iaes · covered True · 8 variables
run 1 (prefix k): voltage_l1 126.4 V · voltage_l2 127.1 V · voltage_l3 125.9 V · current_avg 11.4 A · power_kw 3.36 kW
                  pf_total 0.91 · frequency_hz 60.01 Hz · energy_import_kwh 15234.5 kWh -> [100 x 8]
  OK  with the prefix at k, eight registers become eight events
  OK  values decoded as the meter published them (power W -> kW by scale)
  OK  all eight answered 100 (stored)
  OK  with the prefix at M, the energy value is NOT read (it would be 1000 times off)
  OK  ...and the other seven registers are still read
  OK  the skip message says what the meter reads and what the map expects
  OK  with the prefix back at k the energy value is read again
  OK  a guard that cannot be read FAILS CLOSED: the energy value is not sent
  OK  power declared in W against a kW contract is answered 406 (no conversion)
RESULT: PASS
```

The values above are **simulated**: they were written to a demo asset and mean nothing physical.
