"""tracking.py — Excel de suivi (data/suivi_diplo_es.xlsx), régénéré à chaque run."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from state import DATA

XLSX_PATH = DATA / "suivi_diplo_es.xlsx"
TYPES = {"appointment": "Appointment", "cese": "End of mission", "resolution": "Posts awarded",
         "vacancy": "Vacancy", "check": "To check"}


def log_rows(movements, detected: str) -> list[dict]:
    rows = []
    for m in movements:
        rows.append({
            "date": m.date, "kind": m.kind, "person": m.person,
            "post": "; ".join(dict.fromkeys(m.posts)) or m.summary,
            "place": "; ".join(dict.fromkeys(m.places)),
            "ministry": m.ministry, "boe_ids": m.boe_ids, "url": m.urls[0] if m.urls else "",
            "detected": detected,
        })
    return rows


def write_xlsx(log: list[dict], path: Path = XLSX_PATH) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", start_color="1F3864")

    def sheet(ws, headers, rows, widths):
        ws.append(headers)
        for c in ws[1]:
            c.font = Font(name="Arial", bold=True, color="FFFFFF", size=10)
            c.fill = head_fill
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for r in rows:
            ws.append(r)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.font = Font(name="Arial", size=10)
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Movements"
    rows = [[e["date"], TYPES.get(e["kind"], e["kind"]), e.get("person", ""), e.get("post", ""), e.get("place", ""),
             e.get("ministry", ""), ", ".join(e.get("boe_ids", [])), e.get("url", ""), e.get("detected", "")]
            for e in sorted(log, key=lambda e: e["date"], reverse=True)]
    sheet(ws, ["BOE date", "Type", "Person", "Post / object", "Place", "Ministry", "BOE id", "Link", "Detected on"],
          rows, [12, 16, 30, 50, 28, 34, 24, 44, 12])
    for row in ws.iter_rows(min_row=2, min_col=8, max_col=8):
        for c in row:
            if c.value:
                c.hyperlink = c.value
                c.font = Font(name="Arial", size=10, color="0563C1", underline="single")

    ws2 = wb.create_sheet("Per month")
    cnt = Counter((e["date"][:7], e["kind"]) for e in log)
    months = sorted({m for m, _ in cnt})
    rows2 = [[m] + [cnt.get((m, k), 0) for k in TYPES] for m in months]
    sheet(ws2, ["Month"] + list(TYPES.values()), rows2, [12, 14, 16, 14, 12, 12])
    wb.save(path)
