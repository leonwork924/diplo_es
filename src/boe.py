"""boe.py — Lecture du sommaire du BOE via l'API officielle (open data, gratuite, sans clé).

Endpoint documenté : GET https://boe.es/datosabiertos/api/boe/sumario/AAAAMMDD
(Accept: application/json ou application/xml). Hiérarchie : sumario > diario > seccion
(codigo, nombre) > departamento (nombre) > epigrafe (nombre) > item (identificador, titulo,
url_pdf, url_html, url_xml).

Le parcours est volontairement tolérant : un niveau peut être une liste OU un objet seul,
l'epigrafe peut manquer, les URL peuvent être du texte ou un objet {"texto": ...}.
⚠ Écrit d'après la documentation, sans avoir pu appeler l'API depuis le bac à sable : le
premier run (dry-run) sert de test. Utilise --save-samples pour sauvegarder des réponses brutes.
"""

from __future__ import annotations

import html
import re
import time
from datetime import date
from typing import Iterator

import requests

API = "https://boe.es/datosabiertos/api/boe/sumario/{d}"
XML_URL = "https://www.boe.es/diario_boe/xml.php?id={id}"
HTML_URL = "https://www.boe.es/diario_boe/txt.php?id={id}"
HEADERS = {"Accept": "application/json", "User-Agent": "diplo-es/1.0 (AGS internal tool)"}


def _as_list(x) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _url(v) -> str:
    if isinstance(v, dict):
        return str(v.get("texto") or v.get("#text") or "")
    return str(v or "")


def fetch_sumario(d: date, session: requests.Session | None = None, retries: int = 3) -> dict | None:
    """Sommaire JSON d'un jour, ou None s'il n'y a pas de BOE ce jour-là (404)."""
    s = session or requests
    url = API.format(d=d.strftime("%Y%m%d"))
    last = None
    for attempt in range(retries):
        try:
            r = s.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:  # réseau, 5xx, JSON invalide
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"BOE {d} : échec après {retries} essais ({last})")


def _sumario_root(payload: dict) -> dict:
    for path in (("data", "sumario"), ("response", "data", "sumario"), ("sumario",)):
        node = payload
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if isinstance(node, dict):
            return node
    return payload  # on tente quand même : walk() est tolérant


_LEVELS = ("seccion", "departamento", "epigrafe")


def _walk(node, ctx: dict) -> Iterator[dict]:
    if isinstance(node, list):
        for x in node:
            yield from _walk(x, ctx)
    elif isinstance(node, dict):
        if "identificador" in node and "titulo" in node:
            yield {
                "id": str(node["identificador"]),
                "title": re.sub(r"\s+", " ", str(node["titulo"])).strip(),
                "section": str(ctx.get("seccion_codigo") or ""),
                "section_name": str(ctx.get("seccion_nombre") or ""),
                "department": str(ctx.get("departamento_nombre") or ""),
                "epigraph": str(ctx.get("epigrafe_nombre") or ""),
                "url_html": _url(node.get("url_html")) or HTML_URL.format(id=node["identificador"]),
                "url_xml": _url(node.get("url_xml")) or XML_URL.format(id=node["identificador"]),
                "url_pdf": _url(node.get("url_pdf")),
            }
            return
        for k, v in node.items():
            if k in _LEVELS:
                for child in _as_list(v):
                    if not isinstance(child, dict):
                        continue
                    c = dict(ctx)
                    c[k + "_codigo"] = child.get("codigo", "")
                    c[k + "_nombre"] = child.get("nombre", "")
                    yield from _walk(child, c)
            elif isinstance(v, (list, dict)):
                yield from _walk(v, ctx)


def iter_items(payload: dict) -> Iterator[dict]:
    yield from _walk(_sumario_root(payload), {})


def fetch_text(url: str, session: requests.Session | None = None) -> str | None:
    """Texte brut (balises retirées) d'un document BOE (XML). None si échec."""
    s = session or requests
    try:
        r = s.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=30)
        r.raise_for_status()
    except requests.RequestException:
        return None
    return xml_to_text(r.text)


def xml_to_text(raw: str) -> str:
    t = re.sub(r"(?i)</(p|tr|li|h\d|div)>|<br\s*/?>", "\n", raw)
    t = re.sub(r"(?i)</t[dh]>", " | ", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip(" |") for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)
