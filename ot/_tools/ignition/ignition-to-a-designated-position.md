# Send a pump's variables to Wertek from Ignition

**Who this is for:** you run an **Ignition 8.3** Gateway (Inductive Automation) next to a plant, and its tags
already know a pump's values — from OPC UA, a Modbus device, a PLC driver or MQTT. You want Wertek to keep
them and to fill the asset's panel.

**What it is not for:** reading the device itself (Ignition's drivers already do that, and the protocol
recipes cover it outside Ignition, e.g.
[`../../_protocols/modbus-tcp/`](../../_protocols/modbus-tcp/modbus-tcp-to-a-designated-position.md)). This is
the **send half** for Ignition. It does not create assets and it does not designate positions. It does not
need a project, a Perspective view or the Designer.

## The idea, in one paragraph

Everything is **one tag file** that the Gateway imports:
[`pump-process-to-wertek.tags.json`](pump-process-to-wertek.tags.json). It holds a folder `WertekPumpProcess`
with one tag per variable and a `tick` tag that changes every 65 s. The `valueChanged` event script of `tick`
reads the variables, turns each good-quality value into an IAES `asset.measurement`, sends the batch to
`POST /iaes/ingest` off the tag thread (`system.util.invokeAsynchronous`) and logs one line with the answer
per event under the logger `wertek.ingest`. The key is read from the **Gateway's environment**
(`java.lang.System.getenv`), never from a tag or the file. As shipped, the five variables are **simulated**
expression tags; you replace each `expression` with a reference to your real tag. The script is generated
by [`build_tags.py`](build_tags.py) so it stays readable as Python.

The variable names are the pump panel's own (`flow_m3h`, `head_m`, `kw`, `seal_temp_c`, `vibration_mm_s`),
with the units the file sets. See the table in the Modbus recipe.

## Steps

1. **Designate the position** on the asset (the Modbus recipe's acceptance does it for `pump_process`).
2. **Give the Gateway its environment.** With Docker Compose, under the Ignition service:
   ```yaml
   environment:
     - WERTEK_API_KEY=${WERTEK_API_KEY}        # value in the .env next to the compose file, never in the YAML
     - WERTEK_ASSET_ID=<your asset id>
     - WERTEK_POSITION_CODE=pump_process
     - WERTEK_BASE_URL=https://api.wertek.ai
   ```
   then recreate only that service (`docker compose up -d --no-deps <service>`). On a Windows or Linux
   install without Docker, set them as environment variables of the Gateway service. See
   [`../../../docs/API_KEY_HANDLING.md`](../../../docs/API_KEY_HANDLING.md).
3. **Import the tag file** into the `default` provider: in the Gateway, *Tags → Import*, or with the Gateway
   API (`POST /data/api/v1/tags/import?provider=default&type=json&collisionPolicy=Overwrite`).
4. **Replace the simulated expressions** with your tags, e.g. `{[default]PLC1/Pump/Flow}`; keep the units of
   the table or change them in `build_tags.py` and rebuild.
5. **Watch the log:** *Status → Diagnostics → Logs*, logger `wertek.ingest`, one line per tick:
   `sent 5 events at … -> HTTP 201 codes [100, 100, 100, 100, 100] skipped []`.

**Trial mode:** without a license the Gateway's modules stop every **2 hours** until the trial is reset from
the Gateway page; while stopped, nothing is sent. In the verification below, recreating the container
started a fresh 2-hour trial (observed once, not a documented behaviour).

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         five Ignition tags in [default]WertekPumpProcess (simulated as shipped; your tags in production)
              and a `tick` tag that changes every 65 s
OUTPUT        one IAES 2.0 `asset.measurement` per good-quality tag, sent as ONE batch to POST /iaes/ingest from
              the `tick` valueChanged script; one log line per tick under `wertek.ingest` with the HTTP status of
              the batch and the answer code per event
MAPPING       tag name -> variable of the position's contract; the unit comes from the table in build_tags.py
              (flow_m3h m³/h · head_m m · kw kW · seal_temp_c °C · vibration_mm_s mm/s). A tag whose quality is
              not Good, or whose value is null, is SKIPPED and named in the log line; it is never sent as zero.
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the event time =
              the time of the tick, to the second, UTC (java.time.Instant)
CREDENTIALS   WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable
              from Settings -> API keys) and WERTEK_ASSET_ID in the ENVIRONMENT of the Gateway process. Never in a
              tag, a tag property, a project script, the tag file, a URL or a log line. The acceptance also needs
              an Ignition API key (IGNITION_API_TOKEN) — that one is Ignition's, not Wertek's.
DO NOT INFER  · that your tags are in the units of the table
              · that the position exists and has these variables (404/405 otherwise)
              · the cadence of the position: a tick faster than it is answered 504 per event (dropped); the file
                ticks every 65 s for a 60 s position
              · one position per instrument (billing); this file sends all five variables to ONE position
              · how your Gateway receives environment variables (Docker, Windows service, systemd)
              · that the tag provider is called `default` in your Gateway
              · Ignition versions other than 8.3.9; the Gateway API's security levels in your Gateway: an API key
                cannot carry a role, so the Gateway's read/write permissions must accept the key's level
LIMITS        this is a REFERENCE recipe, not a production connector:
              · ONE asset and ONE position per Gateway: both come from the Gateway environment
                (WERTEK_ASSET_ID, WERTEK_POSITION_CODE), so copying the tag folder for a second drive sends it
                to the same asset and position. Several assets need a tag -> asset/position/variable mapping.
              · no store-and-forward: when the send fails (no Internet), the error is logged and that sample is
                LOST; nothing is queued for a later retry.
              · the event time is the time of the tick (Instant.now()), not the timestamp Ignition holds for the
                value. A connector that queues must send the value's own time, or late data arrives with the
                wrong time.
              · the 65 s tick is this example's (a 60 s position), not a recommended cadence: the position's
                cadence decides.
IDEMPOTENCY   every tick sends new event ids; a tick inside the cadence is answered 504 per event and logged as
              an answer, not as a failure. Re-importing the file with Overwrite replaces the tags, it does not
              duplicate them.
ACCEPTANCE    (with IGNITION_URL and IGNITION_API_TOKEN exported, the Gateway environment set as in step 2, and
              optionally WERTEK_API_KEY to prove it does not leak)
              python ot/_tools/ignition/acceptance_ignition.py
              must print one OK line per check and end in `RESULT: PASS`: the Gateway API accepts the key · the
              trial or license is running · the tag file carries no key · it imports into [default] with 0
              failures · within 150 s the script logs a send · the batch is accepted · all five variables are
              answered 100 · none skipped · the key is not in the Gateway log.
              What it does NOT see: that the values reached the asset's panel (open the Operation tab within
              300 s), and any real source (the shipped tags are simulated).
STATUS        verified 2026-10-06 · Ignition 8.3.9 (b2026082511), standard edition in trial mode, Docker on Ubuntu
              22.04, against api.wertek.ai (demo organisation, asset AST_E3CF6A82, position pump_process) · PASS
              (11 checks; re-run PASS after the Java-exception fix) · a decoy run with a wrong Ignition API key ends in
              RESULT: FAIL at the first check · the asset's Operation tab was then seen by a person showing flow
              115.73 m³/h, head 32.36 m, power 15.37 kW, seal 56.74 °C, vibration 2.3 mm/s and a derived hydraulic
              efficiency of 66.4 % (0.2725 x 115.73 x 32.36 / 15.37 = 66.40).
              Not verified: a real source tag; the Designer; Ignition on Windows; a licensed Gateway; this script's
              error path on a Gateway (the same catch was exercised on the same Gateway in wertek-ai/iaes#54).
```

## Verification report (2026-10-06)

```
gateway: wertek-pruebas · Ignition 8.3.9 (b2026082511) · edition standard
  OK  the Gateway API accepts the key (HTTP 200; 401 = wrong key or secure channel, 403 = security level)
  OK  the trial/license is running (expired=False, seconds left=6760)
  OK  the tag file reads the key from the environment and carries no key
  OK  the key in this shell is not in the tag file
  OK  the tag file imports into [default] (HTTP 200, success 7, failures 0)
log: sent 5 events at 2026-10-06T22:59:01Z -> HTTP 201 codes [100L, 100L, 100L, 100L, 100L] skipped []
  OK  the tag script ran and logged under `wertek.ingest` within 150 s
  OK  the batch was accepted (HTTP 201)
  OK  all 5 variables answered 100 (stored): [100, 100, 100, 100, 100]
  OK  no variable was skipped for bad quality
  OK  the key is not in the Gateway log
RESULT: PASS
```

Before the acceptance, the same Gateway had already sent two ticks 65 s apart (22:56:51Z and 22:57:56Z), both
`HTTP 201` with five `100`. The key was counted, never printed: 0 times in the container log, 0 Gateway log files,
0 Gateway configuration files.

## A Java exception is not a Python exception

In Ignition's Jython, an error raised by Java (for example `java.io.IOException` when the Gateway cannot reach
`api.wertek.ai`) is **not** a Python `Exception`. The first version of this script caught only `Exception`, so a failed
send escaped, Ignition logged a generic `Error running function from system.util.invokeAsynchronous`, and the recipe's own
`send failed: …` line never appeared. It now catches `(Exception, java.lang.Throwable)`. Found on a real Gateway by the
IAES reference scenario (`wertek-ai/iaes#54`), which has the same structure.

## Gateway API access, the two things that blocked us

1. **An API key cannot carry a role.** The key had the level `Authenticated`, the Gateway's read/write
   permissions required `Authenticated / Roles / Administrator`, and the role is greyed out on an API key. Fix:
   *Platform → Security → General Settings*, Gateway Read and Write Permissions, accept `Authenticated`
   ("at least one of"). On a Gateway with more users than `admin`, create a dedicated security level instead.
2. **"Require secure connections for API Keys"** answers 401 over `http://`. Either serve the Gateway over
   HTTPS or, on a private network, uncheck it.
