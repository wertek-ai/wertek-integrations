# Working with this repository — for a person, or an agent working for one

<!-- recipes:begin -->
**STATUS: 9 recipes — 9 verified · 0 draft · 0 planned.** Newest verification: 2026-10-06. Unless a recipe's own `STATUS` line names a real device, `verified` means it was run against the demo organisation with a simulated source (or by hand): read that line for what was NOT verified.
<!-- recipes:end -->

A recipe that is `planned` or `draft` promises nothing.

## Choose a side

| You want to | Go to |
|---|---|
| Send data **to** Wertek from a PLC, meter, drive or SCADA | [`ot/`](ot/) |
| Move data **from** Wertek into a CMMS, ERP, email or chat | [`it/`](it/) |
| Do both halves | Both, and read "If you do both halves" in each |

Read only the side you need. The other side's instructions do not apply to you.

## Two kinds of recipe

Each recipe declares `CONTRACT: iaes` or `CONTRACT: wertek-native`. Not everything
Wertek does is IAES. See [`docs/RECIPE_TEMPLATE.md`](docs/RECIPE_TEMPLATE.md).

## Rules

1. **Do not infer what the recipe does not state.** Where it says `DO NOT INFER`, stop
   and ask the person. Where it is silent, say so in your report.
2. **Check `STATUS` first.** `planned` and `draft` are not instructions to rely on.
3. **Credentials never go into files, command lines, URLs, logs or the chat.** Read the key from the
   environment (`WERTEK_API_KEY`); if it is not set, stop and say so. Do not generate, guess or reuse one.
   Never echo it to check it. Full rule, safe patterns and the agent checklist:
   [`docs/API_KEY_HANDLING.md`](docs/API_KEY_HANDLING.md). `python tools/check_credentials.py` enforces what a
   machine can check.
4. **A passing validator is not conformance.** Run the recipe's `ACCEPTANCE`.
   4-bis. **A variable's name chooses its road.** On `/iaes/ingest`, the names `power`, `energy`,
   `reactive_power`, `power_factor`, `frequency`, `thd_voltage`, `thd_current`, `voltage` and `current` go to a
   registered **energy meter**, not to a position. Read [`docs/ENERGY_METER_DOOR.md`](docs/ENERGY_METER_DOOR.md)
   before sending energy data.
5. **A person reviews the result.** Report: what you read, what you ran and what it
   printed, where the recipe was silent, and what you could not verify.

## IAES

IAES is an open specification maintained separately at
[`wertek-ai/iaes`](https://github.com/wertek-ai/iaes). For connecting a system to IAES
(not to Wertek), start with its `INTEGRATING_WITH_AGENTS.md`.
