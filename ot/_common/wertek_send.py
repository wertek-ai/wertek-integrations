"""The shared SEND half of the `ot/` recipes: read the contract, designate a position if it is missing,
build an IAES `asset.measurement` event, send a batch, read one answer per event.

The first recipe (`ot/iaes/asset-measurement-to-a-designated-position.md`) verified this half against
api.wertek.ai on 2026-10-04. This module is its reusable form; each recipe adds only how to READ its source.

Credentials (docs/API_KEY_HANDLING.md): the key is read from WERTEK_API_KEY and is never printed,
logged, put in a URL or included in an error message.

Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

SPEC = "2.0"
DATASCHEMA = "https://iaes.dev/schema/v2/asset.measurement"


def config(need_asset: bool = True) -> dict:
    """Read the configuration from the environment. Exits, without printing any value, when it is missing."""
    cfg = {
        "base": os.environ.get("WERTEK_BASE_URL", "https://api.wertek.ai").rstrip("/"),
        "key": os.environ.get("WERTEK_API_KEY"),
        "asset": os.environ.get("WERTEK_ASSET_ID"),
        "position": os.environ.get("WERTEK_POSITION_CODE", "acceptance_wi"),
    }
    if not cfg["key"] or (need_asset and not cfg["asset"]):
        sys.exit("set WERTEK_API_KEY and WERTEK_ASSET_ID in the environment (the key is never printed)")
    a = cfg["asset"] or ""
    if need_asset and (any(ch.isspace() for ch in a) or "<" in a or ">" in a):
        # a copied placeholder is the usual cause; an asset id has no spaces and no angle brackets
        sys.exit("WERTEK_ASSET_ID does not look like an asset id (spaces or <...> found): set the real id")
    return cfg


def http(cfg: dict, method: str, path: str, body=None, timeout: int = 40):
    """One call. Returns (status, parsed JSON). Cloudflare rejects urllib's default User-Agent: name yourself."""
    headers = {"X-API-Key": cfg["key"], "User-Agent": "wertek-integrations-ot/1.0",
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(cfg["base"] + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def read_contract(cfg: dict) -> dict:
    st, contract = http(cfg, "GET", f"/iaes/assets/{cfg['asset']}/measurement-points")
    if st != 200:
        sys.exit(f"could not read the contract: HTTP {st}")
    return contract


def ensure_position(cfg: dict, spec: dict) -> dict:
    """Return the position `spec['code']` from the contract; designate it only if it is not there yet
    (designating consumes one point of the organisation's pool, so this never designates twice)."""
    contract = read_contract(cfg)
    code = spec["code"]
    have = {p["code"]: {v["key"] for v in p.get("variables", [])} for p in contract.get("positions", [])}
    # The endpoint "designates OR COMPLETES" a position: re-sending a position that already exists adds the
    # variables it lacks and consumes no new point. So a position left with fewer variables than the spec
    # (an earlier, smaller version of the same recipe) is completed instead of answering 405 for the rest.
    if code not in have or not {v["key"] for v in spec["variables"]} <= have[code]:
        st, d = http(cfg, "POST", f"/iaes/assets/{cfg['asset']}/measurement-points", spec)
        if st != 201:
            # the server says WHY (e.g. more variables than one position may hold); it never contains the key
            why = str((d or {}).get("detail") or "")[:300]
            sys.exit(f"could not designate position {code}: HTTP {st} {why}".strip())
        contract = read_contract(cfg)
    return next(p for p in contract["positions"] if p["code"] == code)


def event(cfg: dict, measurement_type: str, value, unit: str, source: str, correlation_id: str,
          event_id: str | None = None, when: float | None = None) -> dict:
    """An IAES 2.0 `asset.measurement`. A boolean travels as 0/1 (the contract's value_conventions);
    pass `event_id` again to RETRY a send: the same id is stored once (answer 101)."""
    return {
        "spec_version": SPEC,
        "event_id": event_id or str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "event_type": "asset.measurement",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(when)),
        "source": source,
        "dataschema": DATASCHEMA,
        "asset": {"asset_id": cfg["asset"]},
        "data": {"measurement_type": measurement_type, "value": value, "unit": unit,
                 "location": cfg["position"]},
    }


def send(cfg: dict, events: list[dict]) -> dict:
    """POST the batch (a top-level LIST). Returns {event_id: result}; result["c"] is the catalogue code."""
    st, r = http(cfg, "POST", "/iaes/ingest", events)
    # A batch in which NOTHING was accepted answers HTTP 422 but still carries one answer per event
    # (for example 504, faster than the contracted cadence). That is an answer, not a failure.
    if "results" not in r:
        # the server's own answer is safe to show (it never contains the key); the request is not shown
        why = str(r.get("detail") or r.get("error") or r.get("message") or "")[:300]
        sys.exit(f"ingest answered HTTP {st} without per-event results: {why}")
    return {x.get("event_id"): x for x in r.get("results", [])}
