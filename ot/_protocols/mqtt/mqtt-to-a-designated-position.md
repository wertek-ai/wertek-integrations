# Read an MQTT broker and send it to a designated position

**Who this is for:** your plant already publishes to an **MQTT broker** (an edge gateway, a PLC with an MQTT client, a
Raspberry Pi, a sensor hub), and you want Wertek to keep what it publishes as part of an asset's history.

**What it is not for:** Sparkplug B (its payloads are protobuf, not text or JSON: a separate recipe), publishing *to* the
broker, and arrays or waveforms (answered `409`: they go through the capture door).

## The idea, in one paragraph

MQTT carries a topic and bytes. It carries **no unit and no name**, and a broker does not know whether a value is fresh.
So the recipe has one job: **a map you write**, saying which topic is which Wertek variable, how to read the payload (a bare
number, or a field of a JSON object) and in what unit. The program connects, listens for a short window, keeps the **latest
message of each topic** and sends it as an IAES `asset.measurement`. It uses the send half verified in
[`../../iaes/asset-measurement-to-a-designated-position.md`](../../iaes/asset-measurement-to-a-designated-position.md).

## Two traps this program refuses on purpose

1. **A retained message is not a fresh reading.** The broker keeps the last message of a topic and hands it to every new
   subscriber *the moment it subscribes*, possibly days after the device published it. Stamping it with "now" would present an
   old value as current, and a pump that stopped reporting last Tuesday would look alive. A retained message is therefore
   **skipped and named** unless its payload carries its own time (`ts_path`), in which case the event is stamped with *that* time.
2. **A payload that is not a number is skipped, never sent as zero.** `ERR`, an empty payload, or a JSON object without the
   field you asked for is named in the output and nothing is sent in its place.

A third, quieter one: if the program **never gets into the broker** (refused, unreachable, wrong credentials, or a server that
accepts the TCP connection and never answers) it says so. Without that it would report "nothing published", which reads as
"the plant is idle" when the truth is "we were never in the room".

## Steps

1. **Write the map** (`example_pump_map.json`): `broker` (host, port, optional `tls`), `listen_s` (how long to listen) and, per
   topic, `topic`, `variable`, `unit`, optionally `json_path` (`a.b.c`), `ts_path`, `scale`, `offset`, `qos`.
2. **Designate the position** if it is not in the contract yet (first recipe, step 2).
3. **Give the program its credentials from the environment**, never from the map or the command line
   (`../../../docs/API_KEY_HANDLING.md`): `WERTEK_API_KEY`, `WERTEK_ASSET_ID`, and, if the broker wants a user,
   `MQTT_USERNAME` and `MQTT_PASSWORD`.
4. **Run it:**

   ```
   pip install paho-mqtt
   python ot/_protocols/mqtt/mqtt_to_wertek.py --map my_map.json --once
   python ot/_protocols/mqtt/mqtt_to_wertek.py --map my_map.json --interval 60     # loop
   ```

   `listen_s` must be long enough for your device to publish at least once: a device that publishes every 30 s needs a window
   of at least 30 s, or the topic is reported as "nothing published in the window".

## Contract

```
CONTRACT      iaes
SIDE          ot
INPUT         an MQTT broker (MQTT 3.1.1, the client's default; v5 and TLS are not verified) and a JSON map written by a person: broker host and port,
              the listening window, and per topic the Wertek variable key, its unit, optionally a JSON path, a path to
              the payload's own time, scale, offset and QoS
OUTPUT        one IAES 2.0 `asset.measurement` per topic that delivered a number, sent to POST /iaes/ingest; event time =
              the payload's own time when `ts_path` gives one, else the moment the message arrived; one answer per event
              (GET /iaes/schema/codes)
MAPPING       topic (+ JSON path) -> variable of the position's contract; the unit is declared in the map, NOT read from
              the broker. A boolean payload (`true`/`false`) travels as 0/1 (`value_conventions`).
PRESERVE      the unit declared in the contract (compared, not converted: 406 on mismatch) · the payload's own time when
              it has one · that nothing is invented: a topic with no message, a non-numeric payload or a retained
              message without its own time is skipped and NAMED, never sent as a number
CREDENTIALS   env WERTEK_API_KEY (scope iaes.ingest, one organisation, ideally one asset, with an expiry, revocable from
              Settings -> API keys) · env WERTEK_ASSET_ID · and, only if the broker needs one, env MQTT_USERNAME /
              MQTT_PASSWORD. Never in the map, on a command line, in a URL or in a log.
DO NOT INFER  · the unit, the scale and the offset of every topic: declare them from the device's documentation
              · whether a topic's value is raw or engineering units
              · the payload's time zone or epoch unit when `ts_path` is used: ISO 8601 (with `Z` or an offset) and epoch
                seconds or milliseconds are read; anything else is skipped, not guessed
              · the TLS trust: `tls: true` uses the system CA store; which CA your broker needs, client certificates and
                the broker's own authorisation (ACLs) are NOT decided here
              · what to do when the broker is unreachable: this recipe sends nothing and says so
              · the cadence: it must be >= the position's contracted cadence (else 504, dropped)
              · Sparkplug B or any binary payload: not read
IDEMPOTENCY   a payload that repeats the SAME own time carries the same event time as the previous one and is answered
              504 (the cadence gate): an unchanged source is not a new reading. Re-sending the SAME event id is stored
              once (101).
ACCEPTANCE    (with WERTEK_API_KEY and WERTEK_ASSET_ID exported) python ot/_protocols/mqtt/acceptance_mqtt.py must print
              one OK line per check and end in `RESULT: PASS`: five topics (a bare number, a JSON field, a scaled raw
              value, a payload with its own time, a plain number) -> five events -> all answered 100 · a retained message
              without its own time is skipped and named · a non-numeric payload is skipped and named · a JSON without the
              field is skipped and named · a topic nobody published is named · a payload's own ISO time and an epoch in
              milliseconds are read as such · a server that accepts the connection and never answers is named
              "never connected" · a closed port is named · neither a password nor the Wertek key appears in what is shown
              · a wrong unit -> 406.
              What it does NOT see: a real broker (Mosquitto, EMQX, HiveMQ, a cloud broker), TLS, client certificates, QoS
              1/2 delivery guarantees across reconnects, and any real device.
STATUS        verified 2026-10-06 · against api.wertek.ai (demo organisation, a demo pump, position pump_process) with an
              amqtt 0.12.1 broker on localhost and paho-mqtt 2.1.0 · PASS. Not verified: any real broker, TLS, and how
              the values look in the app.
```

## Credentials

The broker's user and password are credentials like the Wertek key: environment only. The map holds addresses, topics and
units, never secrets. The acceptance checks that a test password does not appear in anything the program prints.

## Verification report (2026-10-06)

```
broker: amqtt on localhost · a silent TCP server · a closed port
position: pump_process · adapter iaes · covered True
run 1: {'flow_m3h': 412.5, 'head_m': 85.2, 'kw': 118.4, 'seal_temp_c': 62.3, 'vibration_mm_s': 2.8} [100 x 5]
  OK  five topics become five events
  OK  a bare number, a JSON field and a scaled raw value are decoded
  OK  all five answered 100 (stored)
  OK  a retained message without its own time is skipped and named (it could be old)
  OK  a payload that is not a number is skipped and named, never sent as zero
  OK  a JSON payload without the field is skipped and named
  OK  a topic nobody published is named, not invented
  OK  none of the four produced an event
  OK  a payload's own ISO time is kept as the event time
  OK  an epoch in milliseconds is read as milliseconds
  OK  a boolean payload travels as 0/1
  OK  a server that accepts the connection and never answers is named 'never connected'
  OK  a port with nothing listening is named
  OK  ...and neither the password nor the Wertek key is in anything shown
  OK  a wrong unit is answered 406 (no conversion)
RESULT: PASS
```

One thing to know about the test broker: amqtt writes "No data to decode MQTT packet fixed header" to its own log when the
acceptance probes its port. It is about the test broker, not about this recipe.
