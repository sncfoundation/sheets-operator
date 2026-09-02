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

## Deploy (run it 24/7)

Run the controller on an **always-on host** (a small VM). A laptop works for a demo, but while it
sleeps the controller is paused and edits are not repaired until it wakes.

### 1. Prerequisites

- **Docker** and **git** on the host.
- A **Google OAuth "authorized-user" JSON** for an account that can edit the sheets, with the
  `spreadsheets` and `drive` scopes. It contains a `refresh_token` (the controller refreshes
  itself, so it keeps working). Keep this file private — never commit it.
- The **control-plane spreadsheet id** (`SHEETSOP_CONTROL`) — the registry of managed sheets.

### 2. Get the code and add your credentials

```bash
git clone https://github.com/sncfoundation/sheets-operator
git clone https://github.com/sncfoundation/demos          # templates (e.g. sep3) live here
cd sheets-operator
cp /path/to/your/authorized-user.json creds.json          # your Google creds; never commit
```

### 3. Start it

With docker compose (edit `SHEETSOP_CONTROL`, put templates in `./templates` or mount the demos repo):

```bash
export SHEETSOP_CONTROL=<your-control-plane-spreadsheet-id>
docker compose up -d --build
docker compose logs -f
```

Or with plain `docker run` (mounts creds + the demos templates so it knows the `sep3` desired state):

```bash
docker build -t sheets-operator:1 .
docker run -d --name sheets-operator --restart unless-stopped \
  -e SHEETSOP_CONTROL=<your-control-plane-spreadsheet-id> \
  -e SHEETSOP_TEMPLATES=/templates -e PYTHONUNBUFFERED=1 \
  -v "$PWD/creds.json:/creds/creds.json:ro" \
  -v "$PWD/../demos/sep3:/templates:ro" \
  sheets-operator:1 run --interval 10
```

### 4. Verify

```bash
docker ps                       # sheets-operator should be "Up"
docker logs sheets-operator     # expect: "reconciled <name> (<template>)"
```

Now edit a managed sheet (recolor a cell, delete something) and within a few seconds it snaps back.

### Important

- **Use `run`, not `apply`.** `run` heals *existing* sheets. `apply` creates *new* ones.
- **Moving to another host does not change any spreadsheet links.** The controller reconciles
  existing sheets by their ids in the control plane. Point a new host at the **same**
  `SHEETSOP_CONTROL` with the **same** creds and it drives the same sheets — identical URLs.
- Run only **one** controller per control plane (harmless if two — reconciles are idempotent — but pointless).

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
