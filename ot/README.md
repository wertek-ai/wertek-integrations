# OT — sending data to Wertek

<!-- recipes:begin -->
**STATUS: 7 recipes — 7 verified · 0 draft · 0 planned.** Newest verification: 2026-10-06. Unless a recipe's own `STATUS` line names a real device, `verified` means it was run against the demo organisation with a simulated source (or by hand): read that line for what was NOT verified.

| Recipe | Contract | Status | Verified on | Acceptance |
|---|---|---|---|---|
| [Read a Modbus TCP device and send it to a designated position](_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md) | `iaes` | verified | 2026-10-05 | script |
| [Read an MQTT broker and send it to a designated position](_protocols/mqtt/mqtt-to-a-designated-position.md) | `iaes` | verified | 2026-10-06 | script |
| [Read an OPC UA server and send it to a designated position](_protocols/opcua/opcua-to-a-designated-position.md) | `iaes` | verified | 2026-10-05 | script |
| [Send a pump's variables to Wertek from n8n](_tools/n8n/n8n-to-a-designated-position.md) | `iaes` | verified | 2026-10-05 | by hand |
| [Send a pump's variables to Wertek from Node-RED](_tools/node-red/node-red-to-a-designated-position.md) | `iaes` | verified | 2026-10-05 | script |
| [Read an Eastron SDM630 energy meter and send it to a designated position](eastron/sdm630/eastron-sdm630-to-a-designated-position.md) | `iaes` | verified | 2026-10-06 | script |
| [Send a measurement to a designated position on an asset](iaes/asset-measurement-to-a-designated-position.md) | `iaes` | verified | 2026-10-04 | script |
<!-- recipes:end -->

For someone connecting **PLCs, meters, drives or SCADA** to Wertek: typically
PLC / meter / drive → OPC UA, MQTT or Modbus → Node-RED → Wertek.

## What goes here

| Folder | Holds | State |
|---|---|---|
| `iaes/` | recipes that send IAES events (`CONTRACT: iaes`) — first: [`asset-measurement-to-a-designated-position.md`](iaes/asset-measurement-to-a-designated-position.md) with its executable [`acceptance`](iaes/acceptance_asset_measurement.py) | ✅ exists |
| `_protocols/` | recipes by **protocol**, for any brand — [`modbus-tcp/`](_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md) (reads a Modbus TCP device and sends it; for a pump it fills the pump panel) [`opcua/`](_protocols/opcua/opcua-to-a-designated-position.md) (reads an OPC UA server, skips any node whose quality is not Good) and [`mqtt/`](_protocols/mqtt/mqtt-to-a-designated-position.md) (listens to a broker; refuses a retained message as if it were fresh), each with an executable `acceptance` | ✅ exists |
| `eastron/` | recipes by **brand**: [`sdm630/`](eastron/sdm630/eastron-sdm630-to-a-designated-position.md) — an Eastron SDM630 energy meter by Modbus function 04, with a declared word order and the energy-door naming trap; executable `acceptance` against a simulator | ✅ exists (simulator-verified, not on a real meter) |
| `_tools/` | recipes by **integration tool**, for any source — [`node-red/`](_tools/node-red/node-red-to-a-designated-position.md) (a flow with an executable [`acceptance`](_tools/node-red/acceptance_node_red.py)) and [`n8n/`](_tools/n8n/n8n-to-a-designated-position.md) (a workflow; verified by hand, no command line) | ✅ exists |
| `_common/` | the **send half** the protocol recipes share ([`wertek_send.py`](_common/wertek_send.py)): read the contract, designate, send, read one answer per event | ✅ exists |
| `native/` | recipes that use Wertek's own API (`CONTRACT: wertek-native`) | none yet — the folder is created with its first recipe |

Folders are created with their first recipe, not before. Every recipe follows
[`docs/RECIPE_TEMPLATE.md`](../docs/RECIPE_TEMPLATE.md).

## If you do both halves

Many people understand both worlds. If you also need to act on the data (work orders,
notifications), see [`it/`](../it/). When both sides use IAES, the event is the seam: one
half can be built apart from the other and joined later. A join is only as good as what
both halves agree a condition looks like, so check that before you rely on it.
