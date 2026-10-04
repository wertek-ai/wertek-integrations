# IT — moving data out of Wertek

> **STATUS: planned.** Content from an earlier version of this repository (IAES 1.1,
> March 2026) still sits at the repository root and has not been reviewed against
> IAES 2.0. It is not covered by this page.

For someone connecting **Wertek to a CMMS, ERP, email, chat or other business system**:
typically Wertek → n8n or API → SAP PM, MaintainX, Fracttal, Odoo, email, Teams.

## What goes here

| Folder | Holds | Created when |
|---|---|---|
| `iaes/` | recipes that consume IAES events (`CONTRACT: iaes`) | the first recipe exists |
| `native/` | recipes that use Wertek's own API (`CONTRACT: wertek-native`) | the first recipe exists |

Folders are created with their first recipe, not before. Every recipe follows
[`docs/RECIPE_TEMPLATE.md`](../docs/RECIPE_TEMPLATE.md).

## If you do both halves

If you also need to bring data in from the plant, see [`ot/`](../ot/). When both sides use
IAES, the event is the seam: one half can be built apart from the other and joined later.
A join is only as good as what both halves agree a condition looks like, so check that
before you rely on it.
