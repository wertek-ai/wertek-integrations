# Connector Capability Matrix

The capability matrix is the single source of truth for what each connector can do. It drives:
- **Frontend**: show/hide UI elements per connector
- **Backend**: validate operations before executing
- **API**: `GET /api/v1/integrations/capabilities`
- **Documentation**: generate accurate help content

## Matrix (v1.0)

### Data Push

| Capability | PI System | AVEVA Data Hub | SAP PM | Odoo | MaintainX | Fracttal |
|------------|:---------:|:--------------:|:------:|:----:|:---------:|:--------:|
| Test Connection | Y | Y | Y | Y | Y | Y |
| Push Measurements | Y | Y | - | - | - | Y |
| Push Health Events | Y | Y | - | Y | Y | Y |
| Push Alerts | Y | Y | - | - | Y | Y |

### Work Orders

| Capability | PI System | AVEVA Data Hub | SAP PM | Odoo | MaintainX | Fracttal |
|------------|:---------:|:--------------:|:------:|:----:|:---------:|:--------:|
| Push Work Orders | - | - | Y | Y | - | - |
| Create Work Orders | - | - | Y | Y | Y | Y |
| Read Work Orders | - | - | Y | Y | - | - |
| Bidirectional WO Sync | - | - | Y | Y | - | - |
| Auto-Create on Critical | - | - | Y | Y | Y | Y |

### Assets

| Capability | PI System | AVEVA Data Hub | SAP PM | Odoo | MaintainX | Fracttal |
|------------|:---------:|:--------------:|:------:|:----:|:---------:|:--------:|
| Read Assets | - | - | Y | Y | Y | Y |
| Update Asset Fields | - | - | - | Y | Y | Y |
| Create Assets | - | - | - | - | - | - |
| Read Back Status | - | - | Y | Y | - | - |

### Configuration

| Capability | PI System | AVEVA Data Hub | SAP PM | Odoo | MaintainX | Fracttal |
|------------|:---------:|:--------------:|:------:|:----:|:---------:|:--------:|
| Field Mapping | Y | Y | Y | Y | - | Y |
| Webhook Inbound | - | - | - | - | - | - |

## Connector Profiles

### PI System (Historian)
- **Direction**: Outbound only
- **Pattern**: Tag Writer (PI Web API batch)
- **Auth**: Basic auth over HTTPS
- **Tag naming**: `PREFIX.Plant.Area.Equipment.Category.Metric`
- **Notes**: On-premise, requires VPN or network access

### AVEVA Data Hub (Cloud Historian)
- **Direction**: Outbound only
- **Pattern**: SDS Stream Writer (REST API)
- **Auth**: OAuth2 Client Credentials
- **Notes**: Cloud-to-cloud, no VPN required

### SAP PM (ERP)
- **Direction**: Bidirectional
- **Pattern**: OData (S/4HANA) or RFC (ECC)
- **Auth**: Basic auth or SAP Logon
- **Notes**: Full WO lifecycle sync with conflict resolution

### Odoo (CMMS)
- **Direction**: Bidirectional
- **Pattern**: XML-RPC (stdlib, zero deps)
- **Auth**: API key
- **Notes**: Odoo 14-18, Community + Enterprise, custom `x_wertek_*` fields

### MaintainX (CMMS)
- **Direction**: Outbound only
- **Pattern**: User Variables (REST API)
- **Auth**: API key (Bearer)
- **Notes**: Premium+ plan required ($65/user/mo), pushes intelligence as key-value pairs

### Fracttal (CMMS)
- **Direction**: Outbound only
- **Pattern**: Widget Injection + Auto-OT (REST API)
- **Auth**: Token (no Bearer prefix)
- **Notes**: Custom fields on assets, auto-creates OT on critical severity

## Adding a Capability

To declare a new capability:

1. Add to `Capability` enum in `capabilities.py`
2. Set `True`/`False` for each connector in `CAPABILITY_MATRIX`
3. Optionally add a note explaining the implementation
4. Frontend adapter picks it up automatically via the API
