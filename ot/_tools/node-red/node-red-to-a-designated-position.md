# Send a pump's variables to Wertek from Node-RED

**Who this is for:** you already run **Node-RED** next to a plant (it is the tool most integrators reach for),
and some node in it already knows a pump's values: a Modbus, OPC UA or MQTT node, or a PLC read. You want
Wertek to keep them and to fill the asset's panel.

**What it is not for:** reading the device itself (that is the protocol recipe, for example
[`../../_protocols/modbus-tcp/`](../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md)); this
flow is the **send half** for Node-RED. It does not create assets and it does not designate positions.

## The idea, in one paragraph

Two function nodes and one HTTP request do the whole job. Your source node leaves
`msg.payload = { flow_m3h: 412.5, head_m: 85.2, ... }`. The flow turns each number into an IAES
`asset.measurement`, sends the batch to `POST /iaes/ingest`, and reads one answer per event. The flow file
carries **no secret**: the key and the asset id are read from the **environment of the Node-RED process**
(`env.get(...)`). The flow as shipped has a *simulated* pump as its source; replace that one node.

For a pump, the variable name is what fills the panel: use `flow_m3h`, `head_m`, `kw`, `pf`,
`vibration_mm_s`, `bearing_temp_c`, `winding_temp_c`, `seal_temp_c`, with the units the flow already sets. The
hydraulic efficiency is not sent: the panel derives it. See the table in the Modbus recipe.

## Steps

1. **Designate the position** on the asset (the Modbus recipe's acceptance does it for `pump_process`).
2. **Import** [`pump-process-to-wertek.flow.json`](pump-process-to-wertek.flow.json) into Node-RED.
3. **Give Node-RED its environment**, not the flow. Start Node-RED from a shell where the variables are
   exported (see `docs/API_KEY_HANDLING.md` for how to load the key without typing it on a command line):
   `WERTEK_API_KEY`, `WERTEK_ASSET_ID`, optionally `WERTEK_POSITION_CODE` (default `pump_process`) and
   `WERTEK_BASE_URL`. With Docker, `-e`; with systemd, `EnvironmentFile=` outside the repository.
4. **Replace the simulated source node** with yours; keep its output shape.
5. **Deploy.** The flow fires every 60 s. The panel only shows readings younger than 300 s.

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         msg.payload = { <variable key>: <number> } left by your source node
OUTPUT        one IAES 2.0 `asset.measurement` per number, sent as ONE batch to POST /iaes/ingest; the answer
              per event (msg.payload.answers: key, value, c, d) and the HTTP status of the batch
MAPPING       key -> variable of the position's contract; the unit is set by the flow from a table (the pump
              panel's own units). A key that is not in the table, or a value that is not a finite number, is
              SKIPPED and named in msg.skipped; it is never replaced by zero.
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the event time =
              the time of the tick, to the second, UTC
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry,
              revocable from Settings -> API keys) · env WERTEK_ASSET_ID, read with env.get() from the
              environment of the Node-RED PROCESS. Never typed into a node property, a flow/group/subflow
              environment variable or a context variable: those are saved in the flow file in clear text.
DO NOT INFER  · what your source node is, and that its values are in the units of the table
              · that the position exists and has these variables (404/405 otherwise)
              · the cadence of the position: a tick faster than it is answered 504 (dropped, retry later)
              · one position per instrument (billing); this flow sends all keys to ONE position
              · how Node-RED receives its environment in your deployment (shell, Docker, systemd)
              · Node-RED's "credential"-typed environment variables: not verified here
IDEMPOTENCY   every tick sends new event ids; a tick inside the cadence is answered 504 per event (HTTP 422),
              which the flow reports as an answer, not as a failure
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported, and NODE_RED_BIN pointing to Node-RED)
              python ot/_tools/node-red/acceptance_node_red.py
              must print one OK line per check and end in `RESULT: PASS`: Node-RED starts the flow · five
              variables become five events · all five answered 100 · a second send inside the cadence is
              answered 504 per event and reported as an answer · the key is not in the flow file, in the
              HTTP answers or in Node-RED's log.
              What it does NOT see: that the values reached the asset's panel (open the Operation tab within
              300 s), and any real source (the shipped source is simulated).
STATUS        verified 2026-10-05 · Node-RED 5.0.7 on Node 24, against api.wertek.ai (demo organisation, asset
              AST_E3CF6A82, position pump_process) · PASS · the asset's Operation tab was then seen by a person showing
              flow 411.7 m³/h, head 84.7 m, power 118.1 kW, seal 62.7 °C, vibration 2.6 mm/s and a derived
              hydraulic efficiency of 80.5 % (the values this run sent; 0.2725 x 411.7 x 84.7 / 118.1 = 80.46).
              Not verified: a real source node; the Node-RED editor UI.
```

## Verification report (2026-10-05)

```
node-red: 127.0.0.1:61027 · flow 9 nodes
run 1: [('flow_m3h', 411.7, 100), ('head_m', 84.7, 100), ('kw', 118.1, 100), ('seal_temp_c', 62.7, 100), ('vibration_mm_s', 2.6, 100)]
  OK  the flow answered HTTP 200 to the probe
  OK  five variables were built into five events
  OK  all five answered 100 (stored)
  OK  nothing was skipped
  OK  a second send inside the cadence is answered 504 per event
  OK  the flow reports that as an answer (http 422), not as a failure
  OK  the key is not in the flow file
  OK  the key is not in the HTTP answers
  OK  the key is not in Node-RED's log
RESULT: PASS
```

If you already use the community nodes `node-red-contrib-iaes` to build events, you can keep them: the part this
recipe adds is the call to Wertek, with the key taken from the environment.
