"""
IAES Adapter Contract — Interface for connector adapters.

Every connector implements this contract to transform between IAES canonical
events and the external system's native format.

See: https://github.com/wertek-ai/iaes
"""

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, Dict
import uuid


# ─── IAES Severity (matches IAES spec v1.0) ─────────────────

class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─── IAES Canonical Events (simplified for SDK) ─────────────

@dataclass
class AssetHealthEvent:
    """IAES event_type: asset.health"""
    asset_id: str
    health_index: float = 1.0
    anomaly_score: float = 0.0
    rul_days: Optional[int] = None
    failure_mode: Optional[str] = None
    fault_confidence: float = 0.0
    severity: Severity = Severity.INFO
    recommended_action: Optional[str] = None
    estimated_downtime_hours: Optional[float] = None
    # Context
    asset_name: Optional[str] = None
    plant_name: Optional[str] = None
    area_name: Optional[str] = None
    # IAES envelope
    source: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MeasurementEvent:
    """IAES event_type: asset.measurement"""
    asset_id: str
    measurement_type: str
    value: float
    unit: str
    sensor_id: Optional[str] = None
    location: Optional[str] = None
    # Context
    asset_name: Optional[str] = None
    # IAES envelope
    source: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkOrderEvent:
    """IAES event_type: maintenance.work_order_intent"""
    title: str = ""
    description: str = ""
    priority: str = "medium"  # low, medium, high, emergency
    asset_id: Optional[str] = None
    asset_name: Optional[str] = None
    recommended_due_days: Optional[int] = None
    triggered_by: Optional[str] = None
    # IAES envelope
    source: str = ""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssetEvent:
    """Asset metadata (IAES v1.1 planned: asset.hierarchy)"""
    external_id: str
    name: str
    asset_type: Optional[str] = None
    serial_number: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    location: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Adapter Contract ───────────────────────────────────────

class CanonicalAdapter(ABC):
    """
    Base class for connector adapters.

    Each connector implements these methods to transform between
    IAES canonical events and the external system's native format.

    Not all methods are required:
    - Outbound-only connectors (PI System, MaintainX): implement *_to_external()
    - Inbound-only: implement external_to_*()
    - Bidirectional (SAP PM, Odoo): implement both
    """

    # ── Outbound: IAES → External ──

    def health_event_to_external(self, event: AssetHealthEvent) -> Any:
        """Transform IAES asset.health to the external system's format."""
        raise NotImplementedError

    def measurement_to_external(self, event: MeasurementEvent) -> Any:
        """Transform IAES asset.measurement to the external system's format."""
        raise NotImplementedError

    def work_order_to_external(self, event: WorkOrderEvent) -> Any:
        """Transform IAES maintenance.work_order_intent to native format."""
        raise NotImplementedError

    # ── Inbound: External → IAES ──

    def external_to_work_order(self, data: Any) -> WorkOrderEvent:
        """Transform native work order data to IAES WorkOrderEvent."""
        raise NotImplementedError

    def external_to_asset(self, data: Any) -> AssetEvent:
        """Transform native asset data to IAES AssetEvent."""
        raise NotImplementedError
