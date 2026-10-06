"""Writes `pump-process-to-wertek.tags.json`, the Ignition tag export this recipe imports.

The send script lives inside the tag export (a `valueChanged` event script on the `tick` tag), so the whole
recipe is ONE file that Ignition imports: no project, no Designer. It is generated here, not hand-edited, so the
script stays readable as Python and is indented exactly as Ignition expects (one tab: the body of
`valueChanged(tag, tagPath, previousValue, currentValue, initialChange, missedEvents)`).

    python ot/_tools/ignition/build_tags.py

Credentials (docs/API_KEY_HANDLING.md): the script reads WERTEK_API_KEY from the Gateway's ENVIRONMENT
(java.lang.System.getenv); the key is never in the tag file, a tag value, a URL or a log line.
"""
import json
from pathlib import Path

FOLDER = "WertekPumpProcess"

#: The five variables of the position `pump_process` (the same contract as the Modbus, Node-RED and n8n recipes).
#: The values are SIMULATED by expression tags: replace each `expression` with your OPC/Modbus tag (see the recipe).
VARIABLES = [
    ("flow_m3h",       u"m³/h", "120 + 5 * sin(toMillis(now(5000)) / 60000.0)"),
    ("head_m",         "m",          "32 + 1 * sin(toMillis(now(5000)) / 90000.0)"),
    ("kw",             "kW",         "15 + 0.5 * sin(toMillis(now(5000)) / 75000.0)"),
    ("seal_temp_c",    u"°C",   "55 + 2 * sin(toMillis(now(5000)) / 120000.0)"),
    ("vibration_mm_s", "mm/s",       "2.5 + 0.3 * sin(toMillis(now(5000)) / 45000.0)"),
]

#: Faster than the position's cadence (60 s) would be answered 504; a little slower leaves room for jitter.
TICK_MS = 65000

SCRIPT = r'''
# Wertek: send the pump's variables to the position `pump_process` (wertek-integrations ot/_tools/ignition).
# Runs on the Gateway when `tick` changes. The HTTP call runs off the tag thread (invokeAsynchronous).
if initialChange:
	return
import java.lang.System as JSystem
import java.time.Instant as Instant
import java.time.temporal.ChronoUnit as ChronoUnit
import java.util.UUID as UUID
log = system.util.getLogger("wertek.ingest")
key = JSystem.getenv("WERTEK_API_KEY")
asset = JSystem.getenv("WERTEK_ASSET_ID")
position = JSystem.getenv("WERTEK_POSITION_CODE") or "pump_process"
base = (JSystem.getenv("WERTEK_BASE_URL") or "https://api.wertek.ai").rstrip("/")
if not key or not asset:
	log.warn("WERTEK_API_KEY or WERTEK_ASSET_ID not set in the Gateway environment: nothing sent")
	return
units = __UNITS__
folder = "[default]__FOLDER__/"
names = sorted(units.keys())
values = system.tag.readBlocking([folder + n for n in names])
stamp = str(Instant.now().truncatedTo(ChronoUnit.SECONDS))
correlation = str(UUID.randomUUID())
events = []
skipped = []
for name, qv in zip(names, values):
	if not qv.quality.isGood() or qv.value is None:
		skipped.append(name)  # a bad-quality value is not sent as a number
		continue
	events.append({
		"spec_version": "2.0",
		"event_id": str(UUID.randomUUID()),
		"correlation_id": correlation,
		"event_type": "asset.measurement",
		"timestamp": stamp,
		"source": "wertek_integrations.ignition",
		"dataschema": "https://iaes.dev/schema/v2/asset.measurement",
		"asset": {"asset_id": asset},
		"data": {"measurement_type": name, "value": float(qv.value), "unit": units[name], "location": position},
	})
if not events:
	log.warn("no good-quality values to send; skipped: %s" % skipped)
	return
body = system.util.jsonEncode(events)
def send():
	try:
		client = system.net.httpClient(timeout=20000)
		r = client.post(base + "/iaes/ingest", data=body, headers={
			"X-API-Key": key, "Content-Type": "application/json", "User-Agent": "wertek-integrations-ignition/1.0"})
		codes = [x.get("c") for x in (r.json or {}).get("results", [])] if r.json else []
		log.info("sent %d events at %s -> HTTP %s codes %s skipped %s" % (len(events), stamp, r.statusCode, codes, skipped))
	except Exception as e:
		log.error("send failed: %s" % e)  # the key is never part of the message
system.util.invokeAsynchronous(send)
'''


def _script() -> str:
    units = "{" + ", ".join(f'"{k}": u"{u}"' for k, u, _ in VARIABLES) + "}"
    body = SCRIPT.strip("\n").replace("__UNITS__", units).replace("__FOLDER__", FOLDER)
    return "\n".join("\t" + line if line else "" for line in body.split("\n"))


def build() -> dict:
    tags = [{"name": k, "tagType": "AtomicTag", "valueSource": "expr", "dataType": "Float8",
             "expression": expr, "documentation": f"Simulated. Unit {u}. Replace with your OPC/Modbus tag."}
            for k, u, expr in VARIABLES]
    tags.append({"name": "tick", "tagType": "AtomicTag", "valueSource": "expr", "dataType": "DateTime",
                 "expression": f"now({TICK_MS})",
                 "documentation": "Changes every 65 s; its valueChanged script sends the variables to Wertek.",
                 "eventScripts": [{"eventid": "valueChanged", "script": _script()}]})
    return {"name": FOLDER, "tagType": "Folder", "tags": tags}


if __name__ == "__main__":
    out = Path(__file__).with_name("pump-process-to-wertek.tags.json")
    out.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", out)
