# OT — sending data to Wertek

> **STATUS: one recipe verified** (2026-10-04): sending an `asset.measurement` to a designated
> position. Everything else on this side is still `planned`.

For someone connecting **PLCs, meters, drives or SCADA** to Wertek: typically
PLC / meter / drive → OPC UA, MQTT or Modbus → Node-RED → Wertek.

## What goes here

| Folder | Holds | Created when |
|---|---|---|
| `iaes/` | recipes that send IAES events (`CONTRACT: iaes`) — first: [`asset-measurement-to-a-designated-position.md`](iaes/asset-measurement-to-a-designated-position.md) with its executable [`acceptance`](iaes/acceptance_asset_measurement.py) | ✅ exists |
| `native/` | recipes that use Wertek's own API (`CONTRACT: wertek-native`) | the first recipe exists |

Folders are created with their first recipe, not before. Every recipe follows
[`docs/RECIPE_TEMPLATE.md`](../docs/RECIPE_TEMPLATE.md).

## If you do both halves

Many people understand both worlds. If you also need to act on the data (work orders,
notifications), see [`it/`](../it/). When both sides use IAES, the event is the seam: one
half can be built apart from the other and joined later. A join is only as good as what
both halves agree a condition looks like, so check that before you rely on it.
