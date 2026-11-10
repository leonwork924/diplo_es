"""digest.py — Construit l'alerte (un seul e-mail récapitulatif par run), en anglais."""

from __future__ import annotations

import hashlib
from datetime import date

from classify import Movement

LABELS = {
    "appointment": "Appointments",
    "cese": "Ends of mission (cese)",
    "resolution": "Posts awarded (names in the BOE annex)",
    "vacancy": "Vacancies (no name yet)",
    "check": "To check (looks like a move abroad, could not be read automatically)",
}
ORDER = ["appointment", "cese", "resolution", "vacancy", "check"]
SINGULAR = {"appointment": "appointment", "cese": "end of mission", "resolution": "awarded-posts text",
            "vacancy": "vacancy", "check": "to check"}
PLURAL = {"appointment": "appointments", "cese": "ends of mission", "resolution": "awarded-posts texts",
          "vacancy": "vacancies", "check": "to check"}


def _uniq(xs: list[str]) -> list[str]:
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _fmt(mv: Movement) -> str:
    links = "\n".join(f"      {u}" for u in _uniq(mv.urls))
    if mv.kind in ("appointment", "cese"):
        places = _uniq(mv.places)
        where = places[0] if len(places) == 1 else "; ".join(places)
        posts = _uniq(mv.posts)
        head = f"  - {mv.person} -- {posts[0] if len(posts) == 1 else str(len(places)) + ' accreditations'}"
        lines = [head, f"      Where: {where}", f"      Ministry: {mv.ministry}  |  BOE date: {mv.date}"]
        if len(places) > 1:
            lines.append(f"      (one person, {len(mv.boe_ids)} BOE texts: shown as a single move)")
        return "\n".join(lines) + "\n" + links
    lines = [f"  - {mv.summary}", f"      Ministry: {mv.ministry}  |  BOE date: {mv.date}"]
    for d in mv.details:
        lines.append(f"      > {d}")
    if mv.details:
        lines.append("      (lines extracted automatically from the BOE text: check the link)")
    return "\n".join(lines) + "\n" + links


def build(movements: list[Movement], d_from: date, d_to: date) -> dict | None:
    if not movements:
        return None
    counts = {k: sum(1 for m in movements if m.kind == k) for k in ORDER}
    parts = [f"{n} {SINGULAR[k] if n == 1 else PLURAL[k]}" for k, n in counts.items() if n]
    period = d_to.isoformat() if d_from == d_to else f"{d_from.isoformat()} to {d_to.isoformat()}"
    subject = f"[Diplo ES] BOE alert {period} -- " + ", ".join(parts)
    body = [f"BOE alert, {period}: {', '.join(parts)}.", ""]
    for k in ORDER:
        group = sorted((m for m in movements if m.kind == k), key=lambda m: (m.date, m.person or m.summary))
        if not group:
            continue
        body.append(f"{LABELS[k].upper()} ({len(group)})")
        body.extend(_fmt(m) for m in group)
        body.append("")
    body.append("Source: Boletin Oficial del Estado (BOE), sections II.A and II.B, all ministries.")
    body.append("Automatic alert: please check the BOE link before contacting anyone.")
    ids = sorted(i for m in movements for i in m.boe_ids)
    h = hashlib.sha1("|".join(ids).encode()).hexdigest()[:8]
    return {"id": f"BOE-DIGEST:{d_to.isoformat()}:{h}", "subject": subject, "body": "\n".join(body),
            "link": f"https://www.boe.es/boe/dias/{d_to:%Y/%m/%d}/", "counts": counts}
