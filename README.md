# Wertek Integrations

> Connect systems **to** Wertek (from OT) or **from** Wertek (into IT). Public, MIT-licensed,
> and written for people and for coding agents.

<!-- recipes:begin -->
**STATUS: 10 recipes — 10 verified · 0 draft · 0 planned.** Newest verification: 2026-10-06. Unless a recipe's own `STATUS` line names a real device, `verified` means it was run against the demo organisation with a simulated source (or by hand): read that line for what was NOT verified.
<!-- recipes:end -->

| You want to | Go to |
|---|---|
| Send data to Wertek from a PLC, meter, drive or SCADA | [`ot/`](ot/) |
| Move data from Wertek into a CMMS, ERP, email or chat | [`it/`](it/) |

Not everything Wertek does is [IAES](https://github.com/wertek-ai/iaes): each recipe declares
`CONTRACT: iaes` or `CONTRACT: wertek-native`. Coding agents: read [`AGENTS.md`](AGENTS.md).
Recipe format: [`docs/RECIPE_TEMPLATE.md`](docs/RECIPE_TEMPLATE.md).

> **Everything below this line is the earlier Wertek Integration SDK (IAES 1.1, March 2026).**
> It has not been reviewed against IAES 2.0 and is being reorganised under [`it/`](it/).

---

## Wertek Integration SDK (earlier version)

> Build connectors that bridge industrial asset intelligence with enterprise systems — using the [IAES standard](https://github.com/wertek-ai/iaes).

The Wertek Integration SDK provides the architecture, contracts, and tooling to build connectors between the Wertek AI platform and external systems (CMMS, historians, SCADA, ERP).

## Architecture

```
Sensors / AI / Experts
        |
        v
  IAES Events (vendor-neutral)
        |
        v
  ┌─────────────────────────────┐
  │  Wertek Integration Layer   │
  │                             │
  │  Registry ── Scheduler      │
  │  BaseSyncService            │
  │  CanonicalAdapter           │
  │  MetricsCollector           │
  │  EventBus (Redis Streams)   │
  │  Encryption                 │
  └─────────────────────────────┘
        |
        v
  Enterprise Systems
  SAP PM | PI System | Odoo | MaintainX | Fracttal | AVEVA Data Hub
```

Every connector follows the same pattern:
1. **Plugin** — registers in the IntegrationRegistry
2. **Client** — handles authentication and API calls to the external system
3. **Adapter** — transforms IAES canonical events to/from the native format
4. **SyncService** — orchestrates inbound/outbound sync with metrics and events
5. **Config** — encrypted credential storage (Fernet, per-tenant)

## What's in this repo

| Directory | Contents |
|-----------|----------|
| `docs/` | Architecture overview, capability matrix, connector patterns, API key handling, and [the energy-meter door of `/iaes/ingest`](docs/ENERGY_METER_DOOR.md) (which variable names reach the energy module, and how it answers) |
| `sdk/` | Adapter contracts and base classes (reference for the connector shape) |
| `examples/` | Example connector implementation |

## Building a connector inside Wertek

> **The scaffold CLI is not in this repository.** It is part of Wertek's own platform, so the
> command cannot be run from here. This section and `sdk/SCAFFOLD.md` describe the shape of a
> connector for reference. To connect something today, use the recipes under [`ot/`](ot/) and
> [`it/`](it/).

## Connector Lifecycle

```
1. Scaffold      (Wertek-internal tool, not in this repository)
2. Implement     Fill in client.py (API calls) + adapter.py (transforms)
3. Register      plugin.py auto-registers on import
4. Configure     Admin UI: credentials + sync settings (encrypted)
5. Test          Simulation mode: mock connection + data injection
6. Deploy        Push to Railway, scheduler picks it up
7. Monitor       /api/v1/integrations/metrics + EventBus
```

## Capability Matrix

Each connector declares what it can do. The matrix drives UI rendering, operation validation, and documentation.

| Capability | PI System | Data Hub | SAP PM | Odoo | MaintainX | Fracttal |
|------------|:---------:|:--------:|:------:|:----:|:---------:|:--------:|
| Test Connection | Y | Y | Y | Y | Y | Y |
| Push Measurements | Y | Y | - | - | - | Y |
| Push Health Events | Y | Y | - | Y | Y | Y |
| Push Alerts | Y | Y | - | - | Y | Y |
| Create Work Orders | - | - | Y | Y | Y | Y |
| Read Work Orders | - | - | Y | Y | - | - |
| Bidirectional WO Sync | - | - | Y | Y | - | - |
| Auto-Create on Critical | - | - | Y | Y | Y | Y |
| Read Assets | - | - | Y | Y | Y | Y |
| Update Asset Fields | - | - | - | Y | Y | Y |
| Read Back Status | - | - | Y | Y | - | - |
| Field Mapping | Y | Y | Y | Y | - | Y |

## Adapter Contract

Every connector implements a `CanonicalAdapter` that transforms between IAES events and native format:

```python
class MyAdapter(CanonicalAdapter):
    """Transform IAES events <-> MySystem native format."""

    # ── v1.0 Core ──
    def health_event_to_external(self, event: AssetHealthEvent) -> Any:
        """IAES asset.health -> native format"""
        ...

    def measurement_to_external(self, event: MeasurementEvent) -> Any:
        """IAES asset.measurement -> native format"""
        ...

    def work_order_to_external(self, event: WorkOrderEvent) -> Any:
        """IAES maintenance.work_order_intent -> native format"""
        ...

    def external_to_work_order(self, data: Any) -> WorkOrderEvent:
        """Native WO -> IAES WorkOrderEvent (for inbound sync)"""
        ...

    def external_to_asset(self, data: Any) -> AssetEvent:
        """Native asset -> IAES AssetEvent (for inbound sync)"""
        ...

    # ── v1.1 Additions ──
    def completion_event_to_external(self, event: CompletionEvent) -> Any:
        """IAES maintenance.completion -> native format"""
        ...

    def hierarchy_event_to_external(self, event: HierarchyEvent) -> Any:
        """IAES asset.hierarchy -> native format"""
        ...

    def spare_part_usage_to_external(self, event: SparePartUsageEvent) -> Any:
        """IAES maintenance.spare_part_usage -> native format"""
        ...

    def external_to_completion(self, data: Any) -> CompletionEvent:
        """Native completion -> IAES CompletionEvent (for inbound sync)"""
        ...
```

Not all methods are required. Outbound-only connectors (PI System, MaintainX) skip `external_to_*`. Inbound-only skip `*_to_external`. v1.1 methods default to `NotImplementedError` — implement them as your connector supports the new event types.

## Connector Patterns

| Pattern | Used by | Description |
|---------|---------|-------------|
| **Tag Writer** | PI System, AVEVA Data Hub | Write IAES events as time-series tag values |
| **User Variables** | MaintainX | Push intelligence as key-value pairs on assets |
| **Widget Injection** | Fracttal | Write to custom fields + auto-create OT on critical |
| **Bidirectional Sync** | SAP PM, Odoo | Full WO lifecycle sync with conflict resolution |
| **XML-RPC** | Odoo | Zero-dependency stdlib client (Python xmlrpc.client) |
| **OAuth2 Client Credentials** | AVEVA Data Hub | Cloud-to-cloud, no VPN required |
| **OData** | SAP PM (S/4HANA) | RESTful SAP API |

## Observability

Every sync operation automatically emits:
- **Metrics** — sync count, latency (p50/p95/p99), error rate, records throughput
- **Events** — 9 event types via Redis Streams (with in-process fallback)
- **Structured logs** — JSON picked up by BetterStack
- **Health status** — healthy / degraded / unhealthy / idle per connector

## Related

- **[IAES](https://github.com/wertek-ai/iaes)** — The event specification this SDK implements
- **[iaes.dev](https://iaes.dev)** — Browse the IAES specification online
- **[Wertek AI](https://wertek.ai)** — The platform

## License

MIT

---

*Wertek Integration SDK v1.1 — March 2026*
