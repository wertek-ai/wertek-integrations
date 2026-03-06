"""
Example: MaintainX-style adapter (outbound only, User Variables pattern).

This demonstrates how a connector transforms IAES events into
the external system's native format. MaintainX stores intelligence
as key-value "User Variables" on assets.

This is a simplified reference — the production adapter has additional
error handling, rate limiting, and batch support.
"""

from sdk.adapter_contract import (
    CanonicalAdapter,
    AssetHealthEvent,
    MeasurementEvent,
    WorkOrderEvent,
    Severity,
)


class ExampleMaintainXAdapter(CanonicalAdapter):
    """
    Transform IAES events -> MaintainX User Variables.

    Pattern: Push intelligence as key-value pairs on assets.
    Direction: Outbound only.
    """

    def health_event_to_external(self, event: AssetHealthEvent) -> dict:
        """
        IAES asset.health -> MaintainX userVariables

        The health event becomes a set of User Variables that
        technicians see on the asset detail page in MaintainX.
        """
        variables = {
            "wertek_health_index": str(round(event.health_index * 100)),
            "wertek_severity": event.severity.value,
            "wertek_last_updated": event.timestamp.isoformat(),
        }

        if event.rul_days is not None:
            variables["wertek_rul_days"] = str(event.rul_days)

        if event.failure_mode:
            variables["wertek_fault_type"] = event.failure_mode

        if event.recommended_action:
            variables["wertek_action"] = event.recommended_action

        result = {"userVariables": variables}

        # Auto-create work order on critical severity
        if event.severity == Severity.CRITICAL:
            result["create_work_order"] = {
                "title": f"Critical alert: {event.failure_mode or 'anomaly detected'}",
                "description": (
                    f"Health index: {event.health_index:.0%}\n"
                    f"RUL: {event.rul_days} days\n"
                    f"Action: {event.recommended_action or 'Investigate immediately'}"
                ),
                "priority": "HIGH",
            }

        return result

    def measurement_to_external(self, event: MeasurementEvent) -> dict:
        """
        MaintainX doesn't support direct measurement push.
        Measurements flow through health events instead.
        """
        raise NotImplementedError("MaintainX: use health_event_to_external()")

    def work_order_to_external(self, event: WorkOrderEvent) -> dict:
        """
        IAES maintenance.work_order_intent -> MaintainX work order.
        Only used for auto-create on critical.
        """
        priority_map = {
            "low": "LOW",
            "medium": "MEDIUM",
            "high": "HIGH",
            "emergency": "HIGH",  # MaintainX doesn't have "emergency"
        }

        return {
            "title": event.title,
            "description": event.description,
            "priority": priority_map.get(event.priority, "MEDIUM"),
        }


# ─── Usage Example ───────────────────────────────────────────

if __name__ == "__main__":
    adapter = ExampleMaintainXAdapter()

    # Simulate an IAES health event
    event = AssetHealthEvent(
        asset_id="MOTOR-001",
        health_index=0.16,
        anomaly_score=0.92,
        rul_days=5,
        failure_mode="bearing_inner_race",
        severity=Severity.CRITICAL,
        recommended_action="Replace bearing immediately",
        source="wertek.ai.vibration",
    )

    # Transform to MaintainX format
    result = adapter.health_event_to_external(event)

    import json
    print(json.dumps(result, indent=2))

    # Output:
    # {
    #   "userVariables": {
    #     "wertek_health_index": "16",
    #     "wertek_severity": "critical",
    #     "wertek_last_updated": "2026-03-06T...",
    #     "wertek_rul_days": "5",
    #     "wertek_fault_type": "bearing_inner_race",
    #     "wertek_action": "Replace bearing immediately"
    #   },
    #   "create_work_order": {
    #     "title": "Critical alert: bearing_inner_race",
    #     "description": "Health index: 16%\nRUL: 5 days\nAction: Replace bearing immediately",
    #     "priority": "HIGH"
    #   }
    # }
