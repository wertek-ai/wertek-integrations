# Scaffold CLI — Create a New Connector

The scaffold CLI generates all the boilerplate for a new connector, following the integration framework patterns.

## Usage

```bash
python -m integrations.scaffold <key> \
  --name "Display Name" \
  --category <historian|cmms|erp|iot|scada> \
  --direction <outbound|inbound|bidirectional>
```

### Example

```bash
python -m integrations.scaffold acme_cmms \
  --name "Acme CMMS" \
  --category cmms \
  --direction bidirectional
```

## Generated Files

The scaffold creates a complete connector package:

```
services/acme_cmms/
  __init__.py           # Package exports
  plugin.py             # IntegrationDefinition + registry registration
  models.py             # AcmeCmmsConfig dataclass
  config.py             # CRUD + Fernet encryption (get/save/delete)
  client.py             # AcmeCmmsClient (BaseIntegrationClient)
  sync_service.py       # AcmeCmmsSyncService (BaseSyncService)
  adapter.py            # AcmeCmmsAdapter (CanonicalAdapter)
  help/
    en.json             # English help content (prerequisites, setup, FAQ)
    es.json             # Spanish help content
```

Plus a migration SQL template printed to stdout.

## What You Fill In

The scaffold generates working stubs. You need to implement:

### 1. `client.py` — API Communication

```python
class AcmeCmmsClient(BaseIntegrationClient):
    async def test_connection(self) -> ConnectionResult:
        # Call the external API health/version endpoint
        ...

    async def create_work_order(self, data: dict) -> dict:
        # POST to external API
        ...
```

### 2. `adapter.py` — IAES Transformations

```python
class AcmeCmmsAdapter(CanonicalAdapter):
    def health_event_to_external(self, event: AssetHealthEvent) -> dict:
        # Transform IAES asset.health -> Acme's native format
        return {
            "acme_health_score": event.health_index * 100,
            "acme_fault_code": event.failure_mode,
            ...
        }
```

### 3. `sync_service.py` — Sync Logic

```python
class AcmeCmmsSyncService(BaseSyncService):
    async def sync_outbound(self, result: SyncResult) -> None:
        # Query Wertek for pending events, transform, send
        ...

    async def sync_inbound(self, result: SyncResult) -> None:
        # Fetch from external, transform to IAES, write to Wertek
        ...
```

### 4. Migration SQL

Run the generated SQL to create the config table:

```sql
CREATE TABLE acme_cmms_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES organizations(id) UNIQUE,
    -- connection fields (your API)
    api_url TEXT NOT NULL,
    api_key_encrypted BYTEA,
    -- sync settings
    sync_enabled BOOLEAN DEFAULT FALSE,
    sync_interval_seconds INTEGER DEFAULT 600,
    -- timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5. Frontend Adapter

Add an entry in `connectors/registry.ts`:

```typescript
{
  key: 'acme_cmms',
  name: 'Acme CMMS',
  category: 'cmms',
  icon: 'Wrench',
  // ... connection fields, sync config, help content
}
```

## Recipe Summary

New connector = 5 steps:

1. `python -m integrations.scaffold <key>` (generates 9 files)
2. Implement `client.py` (API calls) + `adapter.py` (transforms)
3. Run migration SQL
4. Add frontend adapter entry
5. Add encryption key env var to Railway

The framework handles: sync scheduling, metrics, event bus, logging, encryption, retry, conflict detection, help system, and simulation mode.
