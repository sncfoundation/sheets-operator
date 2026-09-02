#!/usr/bin/env python3
"""
SheetsOperator — a canonical operator for Google Sheets.

Control plane (a spreadsheet holding a `ManagedSheets` registry) -> a controller loop
-> managed target spreadsheets. The controller continuously reconciles each target back
to its template's desired state, so any edit by anyone drifts and is repaired. This is
the operator pattern applied to spreadsheets: desired state lives in the control plane,
a controller drives the external resource. It is NOT an in-sheet script.

  sheetsctl.py apply <name> --template sep3      # create a target sheet from a template,
                                                 # register it in the control plane, reconcile
  sheetsctl.py run [--interval 8]                # the controller loop: reconcile every managed sheet
  sheetsctl.py reconcile <name>                  # one reconcile pass for one managed sheet
  sheetsctl.py ls                                # list managed sheets

Auth: a Google OAuth "authorized user" JSON (spreadsheets + drive scopes) via
--creds or $SHEETSOP_CREDS. The control-plane spreadsheet id via --control or
$SHEETSOP_CONTROL (created on first `apply` if unset).
"""
import argparse, json, os, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL_TAB = "ManagedSheets"
CONTROL_COLS = ["name", "template", "target_id", "url", "created"]

def _svc():
    path = os.environ.get("SHEETSOP_CREDS") or os.path.expanduser("~/.sheetsop/creds.json")
    creds = Credentials.from_authorized_user_info(json.load(open(path)))
    if not creds.valid:
        creds.refresh(Request())
    return (build("sheets", "v4", credentials=creds, cache_discovery=False),
            build("drive", "v3", credentials=creds, cache_discovery=False))

def _hex(h):
    h = h.lstrip("#"); return {"red": int(h[0:2],16)/255, "green": int(h[2:4],16)/255, "blue": int(h[4:6],16)/255}

def load_template(name):
    dirs = [os.environ["SHEETSOP_TEMPLATES"]] if os.environ.get("SHEETSOP_TEMPLATES") else []
    dirs.append(os.path.join(HERE, "templates"))
    for d in dirs:
        p = os.path.join(d, f"{name}.json")
        if os.path.exists(p):
            return json.load(open(p))
    raise FileNotFoundError(f"template '{name}' not found in {dirs}")

# ---------------------------------------------------------------- control plane

def _ensure_control(sheets):
    cid = os.environ.get("SHEETSOP_CONTROL")
    if cid:
        return cid
    ss = sheets.spreadsheets().create(body={
        "properties": {"title": "SheetsOperator — control plane"},
        "sheets": [{"properties": {"title": CONTROL_TAB}}]}).execute()
    cid = ss["spreadsheetId"]
    sheets.spreadsheets().values().update(spreadsheetId=cid, range=f"{CONTROL_TAB}!A1",
        valueInputOption="RAW", body={"values": [CONTROL_COLS]}).execute()
    print(f"[control-plane] created: {ss['spreadsheetUrl']}\n  export SHEETSOP_CONTROL={cid}")
    return cid

def _managed(sheets, cid):
    r = sheets.spreadsheets().values().get(spreadsheetId=cid, range=f"{CONTROL_TAB}!A1:E1000").execute()
    rows = r.get("values", [])
    return [dict(zip(rows[0], row)) for row in rows[1:] if row]

# ------------------------------------------------------------------- reconcile

def reconcile_target(sheets, target_id, tpl):
    """Repaint the desired state onto the target sheet in one batchUpdate: the title
    banner + the pixel image as cell backgrounds. Overwriting the region reverts drift."""
    meta = sheets.spreadsheets().get(spreadsheetId=target_id).execute()
    sid = meta["sheets"][0]["properties"]["sheetId"]
    grid = tpl.get("grid")                   # optional pixel image (cell backgrounds)
    W, H = (tpl.get("w", 0), tpl.get("h", 0)) if grid else (0, 0)
    banner = tpl.get("banner", tpl.get("title", ""))
    caption = tpl.get("caption", "")
    top = 2                                  # row0 = banner, row1 = caption, image from row2
    need_rows, need_cols = top + H + 1, max(W, 8)

    def _band(row, h): return {"updateDimensionProperties": {"range": {"sheetId": sid,
        "dimension": "ROWS", "startIndex": row, "endIndex": row + 1},
        "properties": {"pixelSize": h}, "fields": "pixelSize"}}
    def _merge(row): return {"mergeCells": {"range": {"sheetId": sid, "startRowIndex": row,
        "endRowIndex": row + 1, "startColumnIndex": 0, "endColumnIndex": need_cols}, "mergeType": "MERGE_ALL"}}

    reqs = [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties":
            {"rowCount": need_rows, "columnCount": need_cols}}, "fields": "gridProperties"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS",
            "startIndex": 0, "endIndex": need_cols}, "properties": {"pixelSize": 16}, "fields": "pixelSize"}},
        _band(0, 46), _band(1, 24), _merge(0), _merge(1),
        # banner: centered, gold, bold
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1,
            "startColumnIndex": 0, "endColumnIndex": need_cols},
            "cell": {"userEnteredValue": {"stringValue": banner},
                     "userEnteredFormat": {"backgroundColor": _hex("#d29922"),
                        "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                        "textFormat": {"bold": True, "fontSize": 18, "foregroundColor": _hex("#1a1a1a")}}},
            "fields": "userEnteredValue,userEnteredFormat"}},
        # caption: below the banner, no fill, smaller, not bold
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "endRowIndex": 2,
            "startColumnIndex": 0, "endColumnIndex": need_cols},
            "cell": {"userEnteredValue": {"stringValue": caption},
                     "userEnteredFormat": {"backgroundColor": _hex("#ffffff"),
                        "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                        "textFormat": {"bold": False, "fontSize": 9, "foregroundColor": _hex("#666666")}}},
            "fields": "userEnteredValue,userEnteredFormat"}},
    ]
    if grid:
        # size the image rows square, then paint the pixels as one updateCells
        reqs.append({"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "ROWS",
            "startIndex": top, "endIndex": top + H}, "properties": {"pixelSize": 16}, "fields": "pixelSize"}})
        rows_data = [{"values": [
            {"userEnteredFormat": {"backgroundColor": _hex(grid[y][x])}} for x in range(W)]} for y in range(H)]
        reqs.append({"updateCells": {"start": {"sheetId": sid, "rowIndex": top, "columnIndex": 0},
            "rows": rows_data, "fields": "userEnteredFormat.backgroundColor"}})

    sheets.spreadsheets().batchUpdate(spreadsheetId=target_id, body={"requests": reqs}).execute()

# --------------------------------------------------------------------- actions

def apply(name, template, public=True):
    sheets, drive = _svc()
    cid = _ensure_control(sheets)
    tpl = load_template(template)
    ss = sheets.spreadsheets().create(body={"properties": {"title": f"{tpl.get('banner','sheet')} — {name}"}}).execute()
    tid, url = ss["spreadsheetId"], ss["spreadsheetUrl"]
    reconcile_target(sheets, tid, tpl)
    if public:
        drive.permissions().create(fileId=tid, body={"role": "writer", "type": "anyone"}).execute()
    sheets.spreadsheets().values().append(spreadsheetId=cid, range=f"{CONTROL_TAB}!A1",
        valueInputOption="RAW", insertDataOption="INSERT_ROWS",
        body={"values": [[name, template, tid, url, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())]]}).execute()
    print(f"[apply] {name} ({template}) -> {url}\n  public: anyone can edit; the operator will reconcile it.")
    return url

def run(interval):
    sheets, _ = _svc()
    cid = os.environ["SHEETSOP_CONTROL"]
    print(f"[operator] reconcile loop every {interval}s over control plane {cid}")
    while True:
        for m in _managed(sheets, cid):
            try:
                reconcile_target(sheets, m["target_id"], load_template(m["template"]))
                print(f"  reconciled {m['name']} ({m['template']})")
            except Exception as e:
                print(f"  FAILED {m.get('name')}: {e}")
        time.sleep(interval)

def reconcile_one(name):
    sheets, _ = _svc()
    cid = os.environ["SHEETSOP_CONTROL"]
    m = next((m for m in _managed(sheets, cid) if m["name"] == name), None)
    if not m: sys.exit(f"no managed sheet named {name}")
    reconcile_target(sheets, m["target_id"], load_template(m["template"]))
    print(f"[reconcile] {name} restored to desired state")

def ls():
    sheets, _ = _svc()
    cid = os.environ.get("SHEETSOP_CONTROL")
    if not cid: sys.exit("set SHEETSOP_CONTROL")
    for m in _managed(sheets, cid):
        print(f"{m['name']:20} {m['template']:10} {m['url']}")

def main():
    ap = argparse.ArgumentParser(description="SheetsOperator — a canonical operator for Google Sheets")
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("apply"); a.add_argument("name"); a.add_argument("--template", required=True)
    a.add_argument("--private", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--interval", type=int, default=8)
    rc = sub.add_parser("reconcile"); rc.add_argument("name")
    sub.add_parser("ls")
    args = ap.parse_args()
    if args.cmd == "apply": apply(args.name, args.template, public=not args.private)
    elif args.cmd == "run": run(args.interval)
    elif args.cmd == "reconcile": reconcile_one(args.name)
    elif args.cmd == "ls": ls()
    else: ap.print_help()

if __name__ == "__main__":
    main()
