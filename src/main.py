"""main.py — diplo_es : surveille le BOE (II.A et II.B, tous ministères) et prépare UNE alerte récapitulative
pour AGS Espagne. N'envoie RIEN : l'alerte est déposée dans data/outbox.json, puis tools/create_outlook_drafts.ps1
crée un brouillon Outlook que tu relis et envoies toi-même (décision IT).

Usage (depuis src/) :
  python3 main.py --days-back 8                  # run normal
  python3 main.py --days-back 8 --dry-run        # n'écrit rien, affiche l'alerte
  python3 main.py --days-back 365 --backfill     # historique : journal + Excel, AUCUNE alerte
  python3 main.py --days-back 3 --save-samples   # sauvegarde des réponses brutes dans data/samples/ (diagnostic)
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date, timedelta

import requests

import boe
import digest as digest_mod
import state
import tracking
from classify import Movement, classify, extract_details, group

DETAIL_KINDS = ("resolution", "vacancy")


def outbox_has(outbox: list[dict], notif_id: str) -> bool:
    return any(it.get("id") == notif_id for it in outbox)


def days(d_from: date, d_to: date):
    d = d_from
    while d <= d_to:
        yield d
        d += timedelta(days=1)


def collect(d_from: date, d_to: date, seen: set[str], session, *, save_samples: bool = False,
            fetch_details: bool = True):
    """Retourne (mouvements nouveaux groupés, ids vus ce run, nombre de jours avec BOE)."""
    new: list[Movement] = []
    new_ids: set[str] = set()
    n_days = 0
    sample_dir = state.DATA / "samples"
    saved = 0
    for d in days(d_from, d_to):
        payload = boe.fetch_sumario(d, session)
        time.sleep(0.2)
        if payload is None:
            continue
        n_days += 1
        if save_samples and n_days == 1:
            sample_dir.mkdir(parents=True, exist_ok=True)
            (sample_dir / f"sumario_{d:%Y%m%d}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        for item in boe.iter_items(payload):
            if item["id"] in seen or item["id"] in new_ids:
                continue
            item["date"] = d.isoformat()
            mv = classify(item)
            if not mv:
                continue
            new_ids.add(item["id"])
            if mv.kind in DETAIL_KINDS and (fetch_details or save_samples):
                raw = None
                try:
                    r = session.get(item["url_xml"], headers={"User-Agent": boe.HEADERS["User-Agent"]}, timeout=30)
                    r.raise_for_status()
                    raw = r.text
                except requests.RequestException:
                    pass
                if raw:
                    if save_samples and saved < 6:
                        sample_dir.mkdir(parents=True, exist_ok=True)
                        (sample_dir / f"{item['id']}.xml").write_text(raw, encoding="utf-8")
                        saved += 1
                    if fetch_details:
                        mv.details = extract_details(boe.xml_to_text(raw))
            new.append(mv)
    return group(new), new_ids, n_days


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days-back", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="N'écrit rien, affiche l'alerte.")
    ap.add_argument("--backfill", action="store_true",
                    help="Historique : remplit le journal et l'Excel, ne met AUCUNE alerte en file (ex. --days-back 365).")
    ap.add_argument("--reset", action="store_true", help="Repart de zéro (vide seen, journal, outbox).")
    ap.add_argument("--test-recipient", default=None, help="Adresse unique à la place des destinataires de config.json.")
    ap.add_argument("--save-samples", action="store_true", help="Sauvegarde des réponses brutes dans data/samples/.")
    args = ap.parse_args()

    today = date.today()
    d_from = today - timedelta(days=args.days_back)
    seen = set() if args.reset else state.load_seen()
    log = [] if args.reset else state.load_log()
    outbox = [] if args.reset else state.load_outbox()
    if args.reset:
        print("RESET : seen, journal et outbox repartent de zéro.")

    session = requests.Session()
    movements, new_ids, n_days = collect(d_from, today, seen, session, save_samples=args.save_samples,
                                         fetch_details=not args.backfill)
    print(f"{n_days} jour(s) de BOE lus entre {d_from} et {today} ; {len(movements)} mouvement(s) nouveau(x).")
    if n_days == 0:
        print("⚠ AUCUN BOE lu : vérifie l'accès à boe.es (l'API ne répond pas ou pas en JSON).")

    kinds = {}
    for m in movements:
        kinds[m.kind] = kinds.get(m.kind, 0) + 1
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(kinds.items())) if kinds else "  rien de nouveau")

    if args.backfill:
        print("[backfill] journal et Excel mis à jour, aucune alerte mise en file.")
        if not args.dry_run:
            log += tracking.log_rows(movements, today.isoformat())
            seen |= new_ids
            state.save_seen(seen); state.save_log(log); state.save_outbox(outbox)
            tracking.write_xlsx(log)
        return

    dig = digest_mod.build(movements, d_from, today) if movements else None
    if dig:
        cfg = state.load_config()
        recipients = [args.test_recipient] if args.test_recipient else cfg.get("recipients", [])
        print("\n" + "=" * 70)
        print("TO:", ", ".join(recipients) or "(aucun destinataire dans config.json)")
        print("SUBJECT:", dig["subject"])
        print("-" * 70)
        print(dig["body"])
        print("=" * 70)
        if not args.dry_run:
            if not recipients:
                print("⚠ Aucun destinataire : alerte NON mise en file (renseigne config.json).")
            else:
                outbox.append({"id": dig["id"], "created": today.isoformat(), "to": recipients,
                               "subject": dig["subject"], "body": dig["body"],
                               "meta": {"name": f"BOE alert {today.isoformat()}", "event": "digest",
                                        "location": "", "branch": "AGS Spain", "link": dig["link"]}})
    if dig and not args.dry_run and not outbox_has(outbox, dig["id"]):
        print("⚠ Rien n'a été écrit (pas de destinataire) : les mouvements ne sont pas marqués comme vus, ils reviendront au prochain run.")
        return
    if not args.dry_run:
        log += tracking.log_rows(movements, today.isoformat())
        seen |= new_ids
        state.save_seen(seen); state.save_log(log); state.save_outbox(outbox)
        tracking.write_xlsx(log)
    print(f"\n{len(movements)} mouvement(s), {'alerte mise en file dans data/outbox.json' if dig and not args.dry_run else 'aucune écriture' if args.dry_run else 'pas d alerte'} (aucun envoi par ce script).")


if __name__ == "__main__":
    main()
