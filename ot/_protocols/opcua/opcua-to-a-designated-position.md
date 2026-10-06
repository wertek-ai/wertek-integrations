# Read an OPC UA server and send it to a designated position

**Who this is for:** you have a PLC, relay, drive or gateway that exposes an **OPC UA server**, and you want Wertek
to keep what it measures as part of the asset's history.

**What it is not for:** subscribing to changes (this recipe **reads** on a schedule), writing to the server,
historical access, or arrays and waveforms (answered `409`: they go through the capture door).

## The idea, in one paragraph

Wertek accepts a reading **for a variable of a position someone designated on an asset**, in the unit the position
declared. An OPC UA server gives you values and, sometimes, units; many servers publish none. So the recipe has one
job: **a map you write**, saying which node is which Wertek variable and in what unit. The program reads each node,
**skips any node whose StatusCode is not Good**, and sends the rest as IAES `asset.measurement`, stamping each event with
the **time the source gives** (`SourceTimestamp`), so a device that stops updating stops looking fresh. It uses the send
half already verified in [`../../iaes/asset-measurement-to-a-designated-position.md`](../../iaes/asset-measurement-to-a-designated-position.md).

## The namespace is looked up by URI, never by index

An OPC UA node is `ns=<index>;s=<identifier>`, and the **index differs between servers** (and between restarts of
the same one). The map therefore holds the namespace **URI** and the identifier; the program asks the server which
index that URI has today. A map with `ns=2` in it is a map that works on one machine.

## An example: the second instrument of a pump

A pump has several instruments, and one position is one device (the billing unit). The Modbus recipe feeds the
hydraulics through `pump_process`; this one feeds a **motor protection relay** through its own position,
`pump_motor`, with `bearing_temp_c`, `winding_temp_c` and `pf`. Same asset, two instruments, two positions.

> **What the pump panel shows today.** Its layout draws **six** tiles: hydraulic efficiency (derived), flow, head,
> power, seal temperature and vibration. The three motor channels above are read by the panel's resolver and stored
> by Wertek, but **no tile draws them yet**: their place is the *Drive Motor* stage, which looks for a sub-asset of
> type `motor`. Until such a sub-asset exists, sending them is correct and invisible on that screen.

## Steps

1. **Write the map** (`example_motor_map.json`): `server.url` and, per node, `namespace_uri`, `identifier`
   (a string identifier), `variable`, `unit`, optionally `scale` and `offset`.
2. **Designate the position** if it is not in the contract yet (first recipe, step 2).
3. **Give the program its credentials from the environment**, never from the map or the command line
   (`../../../docs/API_KEY_HANDLING.md`): `WERTEK_API_KEY`, `WERTEK_ASSET_ID`, and, if the OPC UA server wants a user,
   `OPCUA_USERNAME` and `OPCUA_PASSWORD`.
4. **Run it:**

   ```
   pip install asyncua                      # LGPL-3.0-or-later: you install it; this repository does not ship it
   python ot/_protocols/opcua/opcua_to_wertek.py --map my_map.json --once
   python ot/_protocols/opcua/opcua_to_wertek.py --map my_map.json --interval 60     # loop
   ```

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         an OPC UA server and a JSON map written by a person: server url, and per node the namespace URI, a
              string identifier, the Wertek variable key, its unit, optionally scale and offset
OUTPUT        one IAES 2.0 `asset.measurement` per Good numeric node, sent to POST /iaes/ingest, event time = the
              node's SourceTimestamp (now if the server gives none); one answer per event (GET /iaes/schema/codes)
MAPPING       node -> variable of the position's contract; the unit is declared in the map, NOT read from the
              server. A boolean node travels as 0/1 (`value_conventions`). A node that is not a number is skipped.
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the SOURCE time of
              each reading · the node's quality: a StatusCode that is not Good is never sent as a number
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable
              from Settings -> API keys) · env WERTEK_ASSET_ID · and, only if the OPC UA server needs one, env
              OPCUA_USERNAME / OPCUA_PASSWORD. Never in the map, on a command line, in a URL or in a log.
DO NOT INFER  · the namespace index (look it up by URI) and the identifier type: this connector handles string
                identifiers (`s=`) only; numeric, GUID and opaque identifiers are not read
              · the SECURITY: the acceptance uses an unsecured, anonymous endpoint on localhost. A real server
                has a security policy, a certificate to trust and an authentication; none of that is decided here
              · the unit, the scale and the offset of every node: declare them from the server's documentation
              · reading versus subscribing: this recipe reads on a schedule, it does not subscribe
              · which instrument each node belongs to, hence how many positions to designate (billing)
              · what to do when the server is unreachable: this recipe sends nothing and says so
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
IDEMPOTENCY   a read whose SourceTimestamp has not changed carries the same event time as the previous one, and is
              answered 504 (the cadence gate): an unchanged source is not a new reading. Re-sending the SAME event
              id is stored once (101).
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/_protocols/opcua/acceptance_opcua.py
              must print one OK line per check and end in `RESULT: PASS`: three nodes -> three events read as the
              device published them -> all answered 100 · a node with a BAD StatusCode (BadSensorFailure) is
              skipped and named, not sent · a missing node is skipped and named · a wrong unit -> 406.
              What it does NOT see: that the values are drawn on any screen (the pump panel draws none of these
              three), the security of a real server, and any real device (it runs against a simulated server).
STATUS        verified 2026-10-05 · against api.wertek.ai (demo organisation, asset AST_E3CF6A82, position
              pump_motor) with an asyncua 1.1.5 server on localhost · PASS, twice. Not verified: a real OPC UA
              server, any security policy, and how the values look in the app.
```

## Credentials

The OPC UA server's user and password are credentials like the Wertek key: environment only. The map holds
addresses and units, never secrets.

## Verification report (2026-10-05)

```
opc ua server: 127.0.0.1:62087 · namespace urn:wertek:test:motor-protection-relay · 3 measured nodes + 1 with a BAD status
position: pump_motor · adapter iaes · covered True · variables ['bearing_temp_c[°C]', 'pf[1]', 'winding_temp_c[°C]']
run 1: {'bearing_temp_c': 71.5, 'winding_temp_c': 88.2, 'pf': 0.86} [100, 100, 100]
  OK  three nodes become three events
  OK  values read as the device published them
  OK  all three answered 100 (stored)
  OK  a node with a BAD status is skipped and named, not sent as a number ['pf@Fault: BadSensorFailure']
  OK  a missing node is skipped and named ['pf@NoSuchNode: BadNodeIdUnknown']
  OK  a wrong unit is answered 406 (no conversion)
RESULT: PASS
```

One thing to know about the simulator: asyncua prints "Endpoints other than open requested but private key and
certificate are not set" when it starts. It is about the simulator's own security setup, not about this recipe.
