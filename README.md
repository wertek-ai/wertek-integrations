# Wertek Integration SDK

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
| `docs/` | Architecture overview, capability matrix, connector patterns |
| `sdk/` | Adapter contracts, base classes, scaffold templates |
| `examples/` | Example connector implementation |

## Quick Start: Scaffold a New Connector

```bash
python -m integrations.scaffold acme_cmms \
  --name "Acme CMMS" \
  --category cmms \
  --direction bidirectional
```

This generates 9 files + migration SQL. See [sdk/SCAFFOLD.md](sdk/SCAFFOLD.md) for details.

## Connector Lifecycle

```
1. Scaffold      python -m integrations.scaffold <key>
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
```

Not all methods are required. Outbound-only connectors (PI System, MaintainX) skip `external_to_*`. Inbound-only skip `*_to_external`.

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

*Wertek Integration SDK v1.0 — March 2026*
