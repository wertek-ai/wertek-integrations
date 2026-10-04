# Send a measurement to a designated position on an asset

**Who this is for:** you have a PLC, meter, drive, gateway or a Node-RED/n8n flow that already
knows a value (a temperature, a pressure, a run state), and you want Wertek to keep it as part
of the asset's history, under the asset's own rules.

**What it is not for:** energy meters that Wertek already reads through a kit or gateway
(those positions are fed by another rail and answer `410` if you try), and waveforms,
spectra or video (arrays do not travel in an event — they go through the capture door and
the event carries the reference, `409`).

## The idea, in one paragraph

Wertek does not accept "a measurement". It accepts a measurement **for a position that
someone designated on an asset**, with the variables, units and cadence that were contracted
there. So the recipe has three moves: **read the contract** of the asset (what positions
exist, what each one expects), **designate** a position if yours is not there yet (this
consumes one point of the organisation's pool), and **send events** that match it. Every
event gets its own answer, by code, from a catalogue you can download once.

## Step 1 — read the contract

```
GET https://api.wertek.ai/iaes/assets/{asset_id}/measurement-points
X-API-Key: $WERTEK_API_KEY            (scope iaes.ingest; the key names the organisation)
```

You get `positions[]` — each with its `code`, the current `assignment` (adapter, cadence,
`stale_after_seconds`, `report_mode`), `covered` (the pool covers it), `billing_policy`, and
`variables[]` (`key`, `unit`, `dtype`, `kind`, …) — plus `ingest` (where and how to send) and
**`value_conventions`**, which says how each `dtype` travels. The response carries an `ETag`;
send it back as `If-None-Match` and you get `304` while nothing changed.

## Step 2 — designate a position (only when yours is not in the contract)

```
POST https://api.wertek.ai/iaes/assets/{asset_id}/measurement-points
{
  "code": "zona_1",                       // what you will send as data.location
  "name": "Zone 1", "component": "ambient",
  "variables": [
    {"key": "temperature", "unit": "Cel", "unit_symbol": "degC", "kind": "gauge", "eu_low": -40, "eu_high": 60},
    {"key": "door_open",   "unit": "1",   "kind": "state", "dtype": "boolean"}
  ],
  "cadence_seconds": 60, "report_mode": "sampled"
}
```

`201` returns the position, how many variables it has, the `assignment` (`adapter: iaes`),
the `pool` after the act and a `warning` when the organisation has no pool contracted yet
(the position is created and flagged; nothing is silently refused). `402` = the pool is
exhausted; `422` names the field that is wrong. Designating is an **act that consumes a
point** — do it once per position, not once per run.

## Step 3 — send events

One `asset.measurement` per reading, single object or a **top-level JSON list** of up to 100:

```json
{
  "spec_version": "2.0", "event_id": "<uuid4>", "correlation_id": "<uuid4 per batch>",
  "event_type": "asset.measurement",
  "timestamp": "2026-10-04T18:12:05Z",            // the time of the MEASUREMENT, RFC 3339 UTC
  "source": "plant_x.plc_12",                      // ^[a-z][a-z0-9_.]+$
  "dataschema": "https://iaes.dev/schema/v2/asset.measurement",
  "asset": {"asset_id": "<the asset, as the contract shows it>"},
  "data": {"measurement_type": "temperature", "value": 23.5, "unit": "Cel", "location": "zona_1"}
}
```

`data.location` is the position `code`; `data.measurement_type` is the variable `key`;
`unit` must be the contract's UCUM unit (**compared, never converted**).

## Step 4 — read the answer, per event

```
{"accepted": 2, "rejected": 3, "results": [{"event_id": "…", "c": 100, "d": null, "status": "stored", …}, …]}
```

`c` is a code from `GET /iaes/schema/codes` (download once, cache by `ETag`):

| class | meaning | examples |
|---|---|---|
| `1xx` | stored | `100` stored · `101` duplicate `event_id`, not stored again · `102` historical accepted |
| `2xx` | stored with a warning | `200` position not covered by the pool · `204` outside `eu_low/eu_high` |
| `4xx` | your message is wrong — do not retry as is | `400` envelope invalid (the IAES validator's own text) · `404` position not designated · `405` variable not in the contract · `406` unit mismatch · `407` dtype mismatch · `409` arrays · `410` position fed by another rail |
| `5xx` | our side — retry | `500` storing failed · `503` rate limited (`retry_after_s`) · `504` faster than the contracted cadence, dropped |

## How booleans and states travel

The IAES 2.0 `asset.measurement` schema requires `data.value` to be a **number**. `true` and
`"on"` are rejected with `400` before Wertek sees them. So:

- a `boolean` variable travels as **`0` or `1`**; Wertek stores it as the declared boolean;
- an `enum` variable travels as its **numeric member code**; text members are not reachable
  through `/iaes/ingest`;
- a digital-input **word** travels as the integer it is (one bit per state) — declare it
  `integer`; which load or state each bit means is a rule on the asset, not a value in the event;
- `text` is not reachable through `/iaes/ingest`.

This is what the contract's `value_conventions` says, in the response itself.

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         a value you already have, with its unit (UCUM) and the UTC time it was measured
OUTPUT        one IAES 2.0 `asset.measurement` event per reading, POSTed to /iaes/ingest;
              stored in the asset's history under the designated position
MAPPING       data.location  = position.code        (GET /iaes/assets/{id}/measurement-points)
              data.measurement_type = variable.key  (same response)
              data.unit      = variable.unit        (compared, not converted)
              data.value     = number; boolean as 0/1, enum as numeric code
                               (response field `value_conventions`)
              timestamp      = time of measurement, RFC 3339 UTC (IAES MUST)
PRESERVE      event_id (idempotency key) · correlation_id per batch · the measurement time,
              never the send time · the contract unit · the ETag of the contract you read
DO NOT INFER  the position code or the variable keys (read them; do not derive them from tag
              names) · unit conversions · which bit of a digital-input word means which
              state · what to do on 4xx other than fix the message · whether a position fed
              by a kit/gateway (410) may be re-pointed to your integration (ask the owner)
IDEMPOTENCY   same event_id twice → 101, stored once · designating an existing code: not
              defined by this recipe — read the contract first and designate only if absent
ACCEPTANCE    WERTEK_API_KEY=wk_… WERTEK_ASSET_ID=<asset> python ot/iaes/acceptance_asset_measurement.py
              must print one line per event with OK and end in `RESULT: PASS`:
              temperature/Cel → 100 (or 504 if re-run inside 60 s) · door_open=1 → 100 ·
              door_open=true → 400 · humidity → 405 · temperature/degF → 406.
              What the validator cannot see: that your `value` is in the contract's unit
              (406 is Wertek's check, not IAES's) and that the stored row reached the asset's
              panel — open the asset in app.wertek.ai, tab Sensors, after the run.
STATUS        verified 2026-10-04 against api.wertek.ai (demo organisation, position
              p4_e2e_1240 on asset 2026-02-000002), two runs 70 s apart: see the report at
              the end of this file. `value_conventions` in the contract response ships with
              wertek-backend PR «every energy door declares its adapter, and the contract says
              how booleans travel» — until it is deployed the contract reads version 1.0 and
              the field is absent; the acks above do not depend on it.
```

## Credentials

The API key goes in `WERTEK_API_KEY`, scoped to one organisation and revocable from
*Settings → API keys* in app.wertek.ai. Nothing in this recipe prints it.

## Verification report (2026-10-04, api.wertek.ai, demo organisation)

Two runs of the acceptance, 70 s apart, against the existing position `p4_e2e_1240`
(`temperature[Cel]`, `door_open[1]` boolean, cadence 60 s). The second run, clean:

```
contract: 4 position(s) · version 1.0
position: p4_e2e_1240 · adapter iaes · variables ['door_open[1]', 'temperature[Cel]'] · covered True
ingest: HTTP 201 · accepted 2 · rejected 3
  OK  c=100 expected [100, 504] · temperature in the contract unit
  OK  c=100 expected [100, 504] · boolean as 0/1 (the convention)
  OK  c=400 expected [400] · boolean as true (the schema says no) · envelope
  OK  c=405 expected [405] · variable not in the contract · humidity
  OK  c=406 expected [406] · wrong unit, no conversion · degF≠Cel
RESULT: PASS
```

The first run, 70 s earlier, answered `504 · 12s<60s` for the two stored events because a
run had happened 12 s before it — the cadence gate doing what the contract says. Not seen by
the acceptance and not claimed: that the two `100` rows reached the asset's panel (open the
asset in app.wertek.ai to check), and `value_conventions` (contract 1.1, pending deploy).
