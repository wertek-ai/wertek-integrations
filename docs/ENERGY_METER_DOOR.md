# The energy-meter door of `/iaes/ingest`

`POST /iaes/ingest` has two roads. Which one an `asset.measurement` takes depends **only on the
exact name** of `data.measurement_type`:

| `measurement_type` | Road | Where it lands | Who decides it is accepted |
|---|---|---|---|
| `power` · `energy` · `reactive_power` · `power_factor` · `frequency` · `thd_voltage` · `thd_current` · `voltage` · `current` | **energy-meter door** (this page) | the energy module (`/equipment/energy` screens) of a **registered energy meter** | the meter: its id, its interval |
| anything else | **position contract** — [`../ot/iaes/asset-measurement-to-a-designated-position.md`](../ot/iaes/asset-measurement-to-a-designated-position.md) | the history of a position someone designated on an asset | the position: variable, unit, cadence |

The two are not interchangeable. If you want a position, pick variable names that are **not** on the
list above (the energy recipes use `pf_total`, `frequency_hz`, `power_kw`…). If you want the energy
module, use those names and a registered meter.

## How the door works (from the code deployed 2026-10-06)

1. **The meter is the asset id.** `asset.asset_id` is used as the meter id (`MTR_001`, …). The meter
   must already exist **in the organisation of your API key**; there is no asset resolution and no
   auto-creation. Unknown meter → `404 meter not provisioned` (not retryable).
2. **One value per event, or the flat fields.** With the standard single `data.value`, only these
   types map without guessing, and only with these units (case-insensitive):

   | type | unit | column |
   |---|---|---|
   | `power` | `kW` | active power |
   | `energy` | `kWh` | active energy counter |
   | `reactive_power` | `kvar` | reactive power |
   | `power_factor` | `1`, `pf`, `ratio`, `-` or empty | power factor |
   | `frequency` | `Hz` | frequency |
   | `thd_voltage` · `thd_current` | `%` | THD |

   `voltage` and `current` are per phase: send the flat fields `data.voltage_l1/l2/l3`,
   `data.current_l1/l2/l3` (also accepted: `power_kw`, `power_kva`, `power_kvar`, `power_l1_kw`…,
   `energy_kwh`). A type whose value cannot be mapped without guessing (e.g. `power` in `W`) does not
   land in the energy module: it continues to the position contract, which answers `404/405/406` by name.
3. **The event's own time decides, not the time it arrives.** A reading at time `t` is stored when no
   other reading of the same meter lies within **0.9 × the meter's interval** of `t`, looking backwards
   **and** forwards. So a 30-day load survey, or a burst re-sent after a lost 4G link, is accepted —
   but forging timestamps cannot add more than one point per interval.
4. **One reading per meter and time.** The database holds a unique index on
   (organisation, meter, time) since 2026-10-06. Re-sending the exact same time is answered `101`.

## Answers you will get on this door

| code | meaning here | retry? |
|---|---|---|
| `100` | stored, and it is the newest reading of the meter | — |
| `102` | stored as **history** (older than the newest one); the meter's "last reading" does not move back | — |
| `101` | a reading of this meter **at this exact time** is already stored; not stored again | no |
| `401` | timestamp more than **5 minutes in the future**, or older than the **35-day** backfill window | no — fix the clock / the data |
| `404` | `meter not provisioned`: no meter with that id in your organisation | no — register the meter |
| `504` | another reading of this meter lies within one interval of this one; dropped | no — it is a cadence decision, not an outage |
| `5xx` other | our side | yes |

Download the full catalogue once from `GET /iaes/schema/codes` and cache it by `ETag`.

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         readings of an energy meter that is ALREADY registered in Wertek, with its meter id
OUTPUT        one IAES 2.0 `asset.measurement` per reading to POST /iaes/ingest, asset.asset_id = the meter id,
              data.measurement_type one of: power, energy, reactive_power, power_factor, frequency, thd_voltage,
              thd_current, voltage, current; one answer per event (GET /iaes/schema/codes)
MAPPING       single data.value only for: power kW · energy kWh · reactive_power kvar · power_factor (unitless) ·
              frequency Hz · thd_* % ; voltage and current per phase in flat fields (voltage_l1..3, current_l1..3)
PRESERVE      the event's own timestamp (it decides acceptance) · the unit (power in W is NOT converted: it leaves
              this door and goes to the position contract)
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, the meter's organisation, with an expiry). Never in a URL or log.
DO NOT INFER  · that the meter exists: register it first (404 otherwise, never auto-created)
              · that a name like `power_kw` or `pf_total` reaches the energy module: it does not, only the exact
                names above do
              · the meter's interval: it is configured on the meter in Wertek, not sent by you
IDEMPOTENCY   same meter + same timestamp → 101, stored once. Another reading within 0.9 × interval → 504, dropped.
              History up to 35 days back → 102 (stored). More than 5 min ahead or older than 35 days → 401.
ACCEPTANCE    not yet an executable acceptance script in this repository. Verified against production on 2026-10-06
              only for: a timestamp one hour in the future answered 401 (on a meter id that does not exist, so
              nothing was written). The other rows are read from the deployed code, not from a run.
```
