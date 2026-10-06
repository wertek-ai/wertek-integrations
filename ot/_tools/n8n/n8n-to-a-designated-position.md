# Send a pump's variables to Wertek from n8n

> **STATUS: verified 2026-10-05** by a person running it in their own n8n against the demo organisation (see the
> report at the end, including the three wrong turns on the way). The version of n8n was **not recorded**.

**Who this is for:** you already run **n8n** and some node in it knows a pump's values (an OPC UA, Modbus, MQTT or
HTTP node, or a database read). You want Wertek to keep them and fill the asset's panel.

**What it is not for:** reading the device (that is the protocol recipe); creating assets; designating positions.
It is the same send half as the Node-RED recipe, shaped for n8n.

## The idea, in one paragraph

A schedule fires every minute. A `config` node holds the asset id and the position code (neither is a secret). Your
source leaves one item `{ flow_m3h: 412.5, head_m: 85.2, ... }`. One Code node builds an IAES `asset.measurement`
per number; one **HTTP Request** node sends the batch with the key taken from an **n8n credential (Header Auth)**;
one Code node reads the answer per event. **The key is never in the workflow file**: n8n stores credentials
encrypted and the workflow only names the credential.

> n8n workflows have leaked keys before: a workflow exported with a key typed into a node carries it. Use the
> credential, never a node field, and never an expression that reads the key into the workflow.

## Steps

1. **Create the credential** in n8n: *Credentials → New → Header Auth*. Name the header `X-API-Key`, paste the key as
   the value (it is encrypted at rest), and name the credential `Wertek API key (X-API-Key)`.
2. **Designate the position** on the asset (the Modbus recipe's acceptance does it for `pump_process`).
3. **Import** [`pump-process-to-wertek.workflow.json`](pump-process-to-wertek.workflow.json), set `asset_id` in the
   `config` node, and select the credential in the HTTP Request node.
4. **Replace the simulated source node** with yours; keep its output shape.
5. **Activate.** The panel only shows readings younger than 300 s.

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         one item {"<variable key>": <number>} left by your source node
OUTPUT        one IAES 2.0 `asset.measurement` per number, sent as ONE batch to POST /iaes/ingest; the answer
              per event (c) and the HTTP status of the batch
MAPPING       key -> variable of the position's contract; the unit comes from a table (the pump panel's own
              units). A key not in the table, or a value that is not a finite number, is SKIPPED and named.
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · event time to the
              second, UTC
CREDENTIALS   an n8n credential of type Header Auth (header X-API-Key) holding a Wertek key: scope iaes.ingest,
              one organisation, ideally one asset, with an expiry, revocable from Settings -> API keys. The
              asset id is configuration, not a secret. NEVER a node field or an expression that carries the key.
DO NOT INFER  · the version of n8n: it was not recorded; node versions are those in the JSON
              · what your source node is, and that its values are in the units of the table
              · that the position exists with these variables (404/405 otherwise)
              · the cadence of the position: a run faster than it is answered 504 (HTTP 422) and the workflow
                reports it as an answer
              · the exact parameter names of the nodes in YOUR n8n version: the file imported and ran UNCHANGED on
                2026-10-05 (Schedule 1.2, Set 3.4, Code 2, HTTP Request 4.2) in an n8n whose version was not
                recorded; another version may differ
              · whether your n8n lets the HTTP Request node ignore non-2xx answers ("never error"): the
                workflow needs that for HTTP 422 to be read, not thrown
IDEMPOTENCY   each run sends new event ids; a run inside the cadence is answered 504 per event
ACCEPTANCE    by hand (n8n has no command line here): import, create the credential, set `asset_id`, run once and
              expect, in the last node, `http: 201`, `ok: true` and `c: 100` for five keys; run again inside 60 s
              and expect `c: 504` and `http: 422`. Then open the asset's Operation tab and see the values.
              What it does NOT see: that the key never appears in n8n's execution data or logs (the credential
              is applied by n8n, and the request headers were not inspected), and any real source.
STATUS        verified 2026-10-05 · a person ran it in n8n against api.wertek.ai (demo organisation, asset
              AST_E3CF6A82, position pump_process); the Operation tab then showed flow 411.4 m³/h, head 85.6 m,
              power 118 kW, seal 62.7 °C, vibration 2.6 mm/s and a derived hydraulic efficiency of 81.3 %
              (0.2725 x 411.4 x 85.6 / 118 = 81.33). Not verified: the n8n version; a real source node.
```

## What to do when the last node says it did not go through

The last node's `http` and `why` fields say what Wertek answered. Three wrong turns were hit the first time, in
this order; each one is a different answer and a different fix:

| Wertek answered | It means | Fix |
|---|---|---|
| `401` `Missing X-API-Key header` | n8n sent no key | select the credential in the HTTP Request node (a workflow file never carries credentials, so after importing that field is empty) |
| `401` `Invalid API key` | a key arrived, but not a valid one | the credential's *Value* is not the whole key: it must be only the key (`wk_` + 48 hex characters), with no spaces, newline, quotes or prefix such as `Bearer`. A key prefix copied from a list is not the key. |
| `422` with `c: 403` on every event | the key is valid but is limited to other assets | the `asset_id` in the `config` node must be **exactly** the asset the key was limited to (here `AST_E3CF6A82`); the placeholder in the file, a trailing space or another spelling of the same asset is refused |
| `422` with `c: 504` | faster than the contracted cadence | not an error: wait the cadence (60 s) |

## Verification report (2026-10-05)

Run by a person in their own n8n. First attempt: `http: 401`, `Invalid API key` (the credential held a wrong value).
Second: `http: 422`, `c: 403` on all five (the `config` node still had an asset id the key does not cover). Third,
after fixing both: the five values were stored and the asset's Operation tab showed them with the derived
hydraulic efficiency. Cloudflare did not block n8n's HTTP client.

## If you export your own copy

An n8n export is not a secret, but it carries two things that are yours: `meta.instanceId` (it identifies your
n8n instance) and the `id` of each credential. The key is never in it (it lives encrypted in n8n), but remove those two
before you share or publish a copy, and put the asset id back to a placeholder.
