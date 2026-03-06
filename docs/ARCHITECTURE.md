# Integration Framework Architecture

## Overview

The Wertek Integration Framework is the middleware layer that connects the Wertek AI platform with external enterprise systems. It implements the [IAES standard](https://github.com/wertek-ai/iaes) for vendor-neutral event exchange.

## Design Decisions

### Why a middleware, not point-to-point?

Without the framework, each new integration requires ~2,000 lines of duplicated code: authentication, sync scheduling, error handling, logging, encryption, conflict resolution, retry logic. The framework reduces a new connector to ~500 lines of business logic.

### Why IAES canonical events?

Every connector used to transform directly from Wertek internal models to external formats. This meant N connectors x M entity types = N*M transformation functions. With IAES canonical events as the intermediate format, each connector only needs to implement the adapter contract (5 methods max), and the framework handles the rest.

### Why per-connector config tables + shared log/mapping tables?

Config tables (credentials, endpoints, sync settings) are too different between connectors to unify. But sync logs, entity mappings, and field mappings follow the same schema everywhere. So:
- **Per-connector**: `<name>_integrations` (config + credentials)
- **Shared**: `integration_sync_logs`, `integration_entity_mappings`, `integration_field_mappings`

### Why Redis Streams for the event bus?

- Already have Redis on Railway ($0 extra cost)
- Consumer groups for reliable delivery
- Automatic message persistence with XADD
- Simple protocol (no Kafka/NATS overhead)
- Sufficient for <1,000 events/min at current scale
- Fallback: in-process delivery if Redis is unavailable

### Why in-memory metrics instead of Prometheus?

For <50 customers, in-memory counters with rolling windows are sufficient. The MetricsCollector singleton is thread-safe, zero-dependency, and emits structured JSON logs that BetterStack ingests. Prometheus adds operational complexity (scraper, storage, Grafana) that isn't justified yet.

## Component Map

```
integrations/
  __init__.py           # Public exports
  registry.py           # IntegrationRegistry singleton + auto-discovery
  models.py             # SyncResult, SyncDirection, SyncStatus
  base_client.py        # BaseIntegrationClient ABC (test_connection)
  base_sync.py          # BaseSyncService ABC (sync flow + metrics + events)
  canonical.py          # IAES canonical events (AssetHealthEvent, etc.)
  capabilities.py       # Capability matrix (15 caps x 6 connectors)
  encryption.py         # Fernet encryption for credentials
  simulation.py         # SimulationClient + DataInjector (dev/test)
  scheduler.py          # UnifiedIntegrationScheduler (APScheduler)
  metrics.py            # MetricsCollector (in-memory, per-connector)
  events.py             # EventBus (Redis Streams + in-process)
  help_registry.py      # ConnectorHelpRegistry (i18n help content)
  endpoints.py          # 13 API endpoints (/api/v1/integrations/*)
  scaffold.py           # CLI: python -m integrations.scaffold <key>
```

## Sync Flow

```
BaseSyncService.sync(direction)
  |
  ├── 1. Create SyncResult (status=RUNNING)
  ├── 2. Emit event: sync.started
  |
  ├── 3. Execute sync_outbound() and/or sync_inbound()
  │       ├── Adapter transforms IAES events <-> native format
  │       ├── Client sends/receives data via external API
  │       └── SyncResult updated (records_read/written/failed)
  |
  ├── 4. Determine final status (SUCCESS/PARTIAL/ERROR/CONFLICT)
  ├── 5. Log to integration_sync_logs (PostgreSQL)
  ├── 6. Emit metrics to MetricsCollector (in-memory)
  ├── 7. Emit event: sync.completed or sync.failed
  └── 8. Return SyncResult
```

## Entity Mapping (Asset Traceability)

```
Neo4j (Asset Graph)
  Asset.id (UUID)
       |
       | wertek_id
       v
PostgreSQL: integration_entity_mappings
  integration_type | wertek_id | external_id | sync_status | content_hash
       |
       | external_id
       v
External System (SAP equipment_number, Odoo maintenance.equipment.id, etc.)
```

Every asset in Wertek can be traced to its corresponding entity in every connected external system via the `integration_entity_mappings` table. The `content_hash` field enables change detection without re-reading the full record.

## Security Model

- **Credentials**: Encrypted at rest with Fernet (per-integration encryption key)
- **Multi-tenant**: All queries scoped by `organization_id`
- **RLS**: Row-Level Security on all shared tables
- **Plan gating**: Connectors require specific subscription plans
- **Simulation mode**: Blocked in production (`INTEGRATION_SIMULATION_MODE` env var)

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/integrations` | List all connectors |
| GET | `/api/v1/integrations/{key}/help` | Help documentation |
| GET | `/api/v1/integrations/{key}/help/troubleshoot` | Search troubleshooting |
| GET | `/api/v1/integrations/help/search` | Cross-connector search |
| GET | `/api/v1/integrations/help/export` | Export for bot training |
| GET | `/api/v1/integrations/{key}/simulate/test` | Simulation test |
| POST | `/api/v1/integrations/{key}/simulate/data` | Inject test data |
| GET | `/api/v1/integrations/{key}/logs` | Sync logs |
| GET | `/api/v1/integrations/{key}/mappings` | Entity mappings |
| GET | `/api/v1/integrations/capabilities` | Capability matrix |
| GET | `/api/v1/integrations/metrics` | All connector metrics |
| GET | `/api/v1/integrations/metrics/health` | Health summary |
| GET | `/api/v1/integrations/events/status` | Event bus status |
