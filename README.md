<div align="center">

# 📗 SheetsOperator

**A canonical operator for Google Sheets.**

Control plane (a spreadsheet registry) → an external controller loop → managed target sheets.
The controller continuously reconciles each target back to its template's desired state, so any
edit by anyone drifts and is repaired. A [Sheet-Native Computing Foundation](https://sncfoundation.github.io) project.

</div>

---

This is the operator pattern applied to spreadsheets. Desired state lives in the **control plane**;
a **controller** drives the external resource (a Google Sheet) toward it. It is **not** an in-sheet
Apps Script — control comes from outside the managed resource, exactly like a Kubernetes controller.

```
control plane (ManagedSheets registry)  →  controller loop (this)  →  managed Google Sheets
        desired state                          reconcile()                self-heals on edit
```

## What it does

- `apply <name> --template <t>` — creates a new Google Sheet from a template, makes it
  (optionally) public, registers it in the control plane, and reconciles it once.
- `run` — the controller loop: every N seconds, read the registry and reconcile every managed
  sheet back to its template. Vandalize a managed sheet and it snaps back.
- `reconcile <name>` / `ls`.

A template describes desired state: a `banner`, a `caption`, and an optional pixel `grid`
(cell-background image). See [`templates/hello.json`](templates/hello.json).

## Run it (always-on)

The controller needs Docker, a Google OAuth **authorized-user** JSON (spreadsheets + drive
scopes), and the control-plane spreadsheet id. To keep managed sheets healed 24/7, run it on an
always-on host (a small VM) — not a laptop that sleeps.

```bash
git clone https://github.com/sncfoundation/sheets-operator && cd sheets-operator
cp /path/to/your/google-oauth-authorized-user.json creds.json     # never commit this
export SHEETSOP_CONTROL=<your-control-plane-spreadsheet-id>
# optional: extra templates (e.g. the demos repo) go in ./templates
docker compose up -d --build
docker compose logs -f
```

Or without compose:

```bash
docker build -t sheets-operator:1 .
docker run -d --name sheets-operator --restart unless-stopped \
  -e SHEETSOP_CONTROL=<control-plane-id> -e PYTHONUNBUFFERED=1 \
  -v $PWD/creds.json:/creds/creds.json:ro \
  -v $PWD/templates:/templates:ro -e SHEETSOP_TEMPLATES=/templates \
  sheets-operator:1 run --interval 10
```

**Moving to another host does not change any spreadsheet links.** The controller reconciles
*existing* sheets by the ids in the control plane. Point a new host at the **same**
`SHEETSOP_CONTROL` with the **same** creds and it drives the same sheets — same URLs. Run `run`,
not `apply` (apply creates *new* sheets).

## As a Sheeternetes workload

The controller is just a container, so the canonical home is a **Sheeternetes Deployment**: its
image can be stored in a spreadsheet ([SICF](https://github.com/sncfoundation/sci)), scheduled by
a spreadsheet cluster, and run by a kubelet on a node — a spreadsheet-scheduled operator that
manages spreadsheets. Execution stays on the node; the sheet is the control plane, never the executor.

## Ideas / roadmap

- A **`cluster`** template — provision & self-heal actual Sheeternetes cluster spreadsheets
  (Deployments/Nodes/Pods/Events + a Sheetfana dashboard), so the operator manages real clusters.
- `kind: ManagedSheet` as a first-class Sheeternetes resource (`skctl apply` a ManagedSheet).
- Drift **audit log** (an Events tab: who changed what, when it was reverted).
- Diff-based reconcile (only repair changed cells) for efficiency at scale.
- `SheetTemplate` versioning + templated rollout across a fleet (a StatefulSet of sheets).
- Permissions/sharing reconciliation; `onDelete` finalizers.

See the foundation proposal in [sheeternetes#57](https://github.com/sncfoundation/sheeternetes/issues/57).
Demos (including the self-healing "3 сентября / Shufutinsky" sheet) live in
[sncfoundation/demos](https://github.com/sncfoundation/demos).

---

<sub>Apache-2.0. The spreadsheet is the control plane, never the executor. It reconciles.</sub>
