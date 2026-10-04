"""ACCEPTANCE for `ot/iaes/asset-measurement-to-a-designated-position.md`.

Runs the whole recipe against a real Wertek organisation and prints what came back,
event by event. It never prints the API key.

    WERTEK_API_KEY=wk_...  WERTEK_ASSET_ID=<your asset>  python acceptance_asset_measurement.py

Optional:
    WERTEK_BASE_URL       default https://api.wertek.ai
    WERTEK_POSITION_CODE  default acceptance_wi — if the contract already has it, the script
                          does not designate again (so the pool is consumed once, not per run)

Exit code 0 only when every expected ack class was observed (see EXPECTED below).
Standard library only; no third-party packages.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get("WERTEK_BASE_URL", "https://api.wertek.ai").rstrip("/")
KEY = os.environ.get("WERTEK_API_KEY")
ASSET = os.environ.get("WERTEK_ASSET_ID")
CODE = os.environ.get("WERTEK_POSITION_CODE", "acceptance_wi")
if not KEY or not ASSET:
    sys.exit("set WERTEK_API_KEY and WERTEK_ASSET_ID (the key is never printed)")

# Cloudflare rejects urllib's default User-Agent (error 1010); name yourself.
HEADERS = {"X-API-Key": KEY, "User-Agent": "wertek-integrations-acceptance/1.0", "Content-Type": "application/json"}


def http(method, path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 method=method, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


# 1 · read the contract; designate the position only if it is not there yet
st, contract = http("GET", f"/iaes/assets/{ASSET}/measurement-points")
assert st == 200, (st, contract)
have = {p["code"] for p in contract.get("positions", [])}
print(f"contract: {len(have)} position(s) · version {contract.get('contract_version')}")
if CODE not in have:
    st, d = http("POST", f"/iaes/assets/{ASSET}/measurement-points", {
        "code": CODE, "name": "wertek-integrations acceptance", "component": "ambient",
        "variables": [
            {"key": "temperature", "unit": "Cel", "unit_symbol": "degC", "kind": "gauge", "eu_low": -40, "eu_high": 60},
            {"key": "door_open", "unit": "1", "kind": "state", "dtype": "boolean"},
        ],
        "cadence_seconds": 60, "report_mode": "sampled",
    })
    print(f"designate: {st} · pool {d.get('pool')} · warning {d.get('warning')}")
    assert st == 201, (st, d)
    st, contract = http("GET", f"/iaes/assets/{ASSET}/measurement-points")
pos = next(p for p in contract["positions"] if p["code"] == CODE)
print("position:", CODE, "· adapter", pos["assignment"]["adapter"], "· variables",
      [v["key"] + "[" + str(v.get("unit")) + "]" for v in pos["variables"]], "· covered", pos["covered"])
print("value_conventions.boolean:", (contract.get("value_conventions") or {}).get("boolean"))

# 2 · one batch, five events, each chosen to show one answer
CORR = str(uuid.uuid4())


def ev(mtype, value, unit):
    return {"spec_version": "2.0", "event_id": str(uuid.uuid4()), "correlation_id": CORR,
            "event_type": "asset.measurement",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "wertek_integrations.acceptance",
            "dataschema": "https://iaes.dev/schema/v2/asset.measurement",
            "asset": {"asset_id": ASSET},
            "data": {"measurement_type": mtype, "value": value, "unit": unit, "location": CODE}}


batch = [
    ("temperature in the contract unit", ev("temperature", 23.5, "Cel"), {100, 504}),  # 504 if a run < 60 s ago
    ("boolean as 0/1 (the convention)", ev("door_open", 1, "1"), {100, 504}),
    ("boolean as true (the schema says no)", ev("door_open", True, "1"), {400}),
    ("variable not in the contract", ev("humidity", 50, "%"), {405}),
    ("wrong unit, no conversion", ev("temperature", 74.3, "degF"), {406}),
]
st, r = http("POST", "/iaes/ingest", [e for _, e, _ in batch])   # the batch is a top-level LIST
print(f"ingest: HTTP {st} · accepted {r.get('accepted')} · rejected {r.get('rejected')}")
by_id = {x.get("event_id"): x for x in r.get("results", [])}

ok = True
for label, e, expected in batch:
    x = by_id.get(e["event_id"], {})
    code = x.get("c")          # the catalogue code; 400 = E_SCHEMA (the standard's validator spoke)
    hit = code in expected
    ok &= hit
    print(f"  {'OK ' if hit else 'BAD'} c={code} expected {sorted(expected)} · {label} · {(x.get('d') or x.get('error') or '')[:80]}")

print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
