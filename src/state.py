"""state.py — Fichiers d'état (data/*.json) : seen, outbox, journal des mouvements."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
KEEP_DAYS = 30


def _load(name: str, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _save(name: str, obj) -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_seen() -> set[str]:
    return set(_load("seen.json", []))


def save_seen(s: set[str]) -> None:
    _save("seen.json", sorted(s))


def load_log() -> list[dict]:
    return _load("movements.json", [])


def save_log(log: list[dict]) -> None:
    _save("movements.json", log)


def load_outbox() -> list[dict]:
    items = _load("outbox.json", [])
    limit = date.today() - timedelta(days=KEEP_DAYS)
    kept = []
    for it in items:
        try:
            if datetime.fromisoformat(it["created"]).date() < limit:
                continue
        except (KeyError, ValueError):
            pass
        kept.append(it)
    return kept


def save_outbox(items: list[dict]) -> None:
    _save("outbox.json", items)


def load_config() -> dict:
    p = ROOT / "config.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"recipients": []}
