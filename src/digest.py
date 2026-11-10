"""digest.py — Construit l'alerte (un seul e-mail récapitulatif par run), en anglais."""

from __future__ import annotations

import hashlib
import re
import unicodedata
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


def _ascii(x: str) -> str:
    return unicodedata.normalize("NFKD", x).encode("ascii", "ignore").decode().lower()


def guess_email(person: str) -> str:
    """prénom.premier-nom@maec.es (format confirmé par AGS Spain ; à vérifier pour les noms composés)."""
    parts = [w for w in re.split(r"\s+", person.strip()) if w]
    if len(parts) < 2:
        return ""
    return f"{re.sub(r'[^a-z]', '', _ascii(parts[0]))}.{re.sub(r'[^a-z-]', '', _ascii(parts[1]))}@maec.es"


TEMPLATE = """DRAFT EMAIL TO AN APPOINTED DIPLOMAT (AGS Spain template, in Spanish)
Fill in the blanks before sending. Only for appointments, not for ends of mission.

Estimado Sr./Sra. ____________,

Primeramente, quisiera darle la enhorabuena por su nombramiento. De acuerdo con la publicacion del BOE se trasladara desde __________ a __________, por lo que me dirijo a usted para presentarle nuestra compania y poner a su disposicion toda nuestra estructura y experiencia en mudanzas internacionales.

AGS se establecio en Espana en el anio 1993, ofreciendo a nuestros clientes, desde entonces, nuestra experiencia en esta industria y nuestra red propia mundial, ya que estamos situados, con 147 delegaciones y almacenes propios, en 100 paises en todo el mundo, ademas de mas de 300 agentes de confianza (adjunto presentacion de la empresa).

Toda esta infraestructura nos permite coordinar las mudanzas desde nuestras oficinas de Madrid, llevando a cabo sus traslados en primera persona desde cualquier lugar hasta cualquier destino, garantizandoles una seleccion cuidada de todos los profesionales que intervienen en los mismos. En el caso particular de su traslado, tenga en cuenta que tenemos delegacion propia ____________.

Si lo desea, puede consultar nuestra pagina web: www.ags-globalsolutions.com

En el caso de que quiera que le asesoremos y presentemos presupuesto para el traslado de sus enseres, el primer paso es realizar una visita para poder valorar el volumen de los enseres que desea trasladar y cualquier particularidad que conlleve su mudanza.

Para ello le agradeceria que me indicara la siguiente informacion:
  - Direccion de origen:
  - Disponibilidad para la visita:
  - Telefono de contacto:
  - Volumen autorizado:
  - Fechas estimadas de recogida:
  - Fecha de toma de posesion del cargo en destino:
  - Inventario valorado:
"""


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
        if mv.kind == "appointment" and guess_email(mv.person or ""):
            lines.append(f"      Suggested email: {guess_email(mv.person)} (firstname.surname@maec.es, please verify)")
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
    if counts.get("appointment"):
        body.append("-" * 60)
        body.append(TEMPLATE)
        body.append("-" * 60)
    body.append("Source: Boletin Oficial del Estado (BOE), sections II.A and II.B, all ministries.")
    body.append("Automatic alert: please check the BOE link before contacting anyone.")
    ids = sorted(i for m in movements for i in m.boe_ids)
    h = hashlib.sha1("|".join(ids).encode()).hexdigest()[:8]
    return {"id": f"BOE-DIGEST:{d_to.isoformat()}:{h}", "subject": subject, "body": "\n".join(body),
            "link": f"https://www.boe.es/boe/dias/{d_to:%Y/%m/%d}/", "counts": counts}
