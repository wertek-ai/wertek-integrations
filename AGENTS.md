# Working with this repository — for a person, or an agent working for one

> **Status of this repository: one recipe verified** (`ot/iaes/asset-measurement-to-a-designated-position.md`,
> 2026-10-04, with an executable acceptance). Every other recipe is `planned` and promises nothing.

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
3. **Credentials never go into files.** Environment variables or a secret store only.
4. **A passing validator is not conformance.** Run the recipe's `ACCEPTANCE`.
5. **A person reviews the result.** Report: what you read, what you ran and what it
   printed, where the recipe was silent, and what you could not verify.

## IAES

IAES is an open specification maintained separately at
[`wertek-ai/iaes`](https://github.com/wertek-ai/iaes). For connecting a system to IAES
(not to Wertek), start with its `INTEGRATING_WITH_AGENTS.md`.
