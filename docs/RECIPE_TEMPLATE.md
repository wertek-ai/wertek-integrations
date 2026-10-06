# Recipe template

Every recipe in `ot/` and `it/` is written for two readers at once: a person who
understands it, and a coding agent that can run it and check itself. The first part
is narrative. The second is the **Contract block**, which is the same for every recipe.

**A recipe without an executable `ACCEPTANCE` may not claim `STATUS: verified`.**

## Narrative

What this recipe connects, why you would, when you would **not**.

## Contract

```
CONTRACT      iaes | wertek-native
SIDE          ot | it
INPUT         what it receives, in what shape
OUTPUT        what it produces
MAPPING       how fields correspond (cite the artifact; do not paraphrase it)
PRESERVE      what must not be lost: provenance, ids, units
DO NOT INFER  what is NOT defined, so the agent must ask instead of guessing
CREDENTIALS   the environment variable NAMES it reads, their scope and how to revoke; never a value
IDEMPOTENCY   what happens if it runs twice
ACCEPTANCE    the command that shows it works, and what it must print
STATUS        verified <date, how> | draft | planned
```

- `CONTRACT: iaes` means the recipe speaks IAES. The event contract lives in
  [`wertek-ai/iaes`](https://github.com/wertek-ai/iaes); this repository cites it and never copies it.
- `CONTRACT: wertek-native` means the recipe uses Wertek's own API or protocol and does not use IAES.
- A passing validator is not conformance. `ACCEPTANCE` also lists what the validator cannot see.

## Credentials

Never write a credential into a recipe, a flow, an example or a log. Show it as an
environment variable or a secret-store reference. Use keys scoped to one organisation
and revocable. Every recipe fills the `CREDENTIALS` line of the Contract block with
variable **names** only. The full rule, with safe patterns and the checklist for agents,
is [`API_KEY_HANDLING.md`](API_KEY_HANDLING.md); `tools/check_credentials.py` runs in CI.
