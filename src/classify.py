"""classify.py — Transforme les titres du BOE en mouvements.

Types :
  appointment  nomination d'un ambassadeur (Real Decreto « se designa ... »), nom + lieu dans le titre
  cese         fin de mission d'un ambassadeur (« se dispone el cese de ... como Embajador »)
  resolution   résolution qui ATTRIBUE des postes à l'étranger (noms dans l'annexe, pas dans le titre)
  vacancy      convocation de postes à pourvoir à l'étranger (signal en avance, sans nom)
  check        texte qui ressemble à un mouvement à l'étranger mais qu'on ne sait pas lire : à vérifier
Tout le reste (universités, fonction publique nationale...) est ignoré.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

NAME = r"(?:don|doña|D\.|Dña\.)\s+(?P<name>[^,.]+(?:\s+[^,.]+)*?)"

RE_DESIGNA = re.compile(
    r"por el que se (?:designa|nombra) (?P<cargo>Embajador(?:a)?\b.*?) a " + NAME + r"\s*\.?$", re.I)
RE_CESE = re.compile(
    r"por el que se dispone el cese de " + NAME + r" como (?P<cargo>Embajador(?:a)?\b.*?)\s*\.?$", re.I)
RE_PLACE = re.compile(r"\bde España\s+(?:en|ante)\s+(?P<place>.+)$", re.I)
RE_PLACE2 = re.compile(r"\b(?:en|ante)\s+(?P<place>.+)$", re.I)

# Indices qu'un texte concerne un poste à l'étranger.
CUES = re.compile(
    r"en el exterior|en el extranjero|Embajada|Consulado|Consejer[ií]as?\b|Representaci[oó]n Permanente|"
    r"Agregadur|Agregad[oa]s?\b|Oficinas? Econ[oó]micas? y Comerciales?|Carrera Diplom[aá]tica|"
    r"Servicio Exterior|asesor(?:es|as)? t[eé]cnic|Misi[oó]n Diplom|Embajador",
    re.I)
EXCLUDE = re.compile(r"acuerdan ascensos|Consejo Escolar|catedr[aá]tic|profesor|Universidad", re.I)
RE_CONVOCA = re.compile(r"por la que se convoca", re.I)
RE_RESUELVE = re.compile(r"por la que se resuelve", re.I)


@dataclass
class Movement:
    kind: str                      # appointment | cese | resolution | vacancy | check
    date: str                      # AAAA-MM-JJ (jour de publication)
    boe_ids: list[str]
    urls: list[str]
    ministry: str = ""
    person: str = ""
    posts: list[str] = field(default_factory=list)    # fonctions (ex. « Embajador de España en Canadá »)
    places: list[str] = field(default_factory=list)   # pays / organisation
    summary: str = ""              # pour resolution / vacancy / check : le titre allégé
    details: list[str] = field(default_factory=list)  # lignes extraites du texte complet (resolution / vacancy)
    title: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}|{self.person.lower()}|{self.date}" if self.person else f"{self.kind}|{self.boe_ids[0]}"


def _clean_place(p: str) -> str:
    p = p.strip(" .")
    p = re.sub(r"^(?:la\s+Rep[uú]blica\s+(?:Socialista\s+Democr[aá]tica\s+|Democr[aá]tica\s+|Popular\s+)?de\s+|el\s+Reino\s+de\s+|el\s+Estado\s+de\s+)", "", p, flags=re.I)
    p = re.sub(r"^(?:la|el|las|los)\s+", "", p, flags=re.I)
    return p[:1].upper() + p[1:]


def _place(cargo: str) -> str:
    m = RE_PLACE.search(cargo) or RE_PLACE2.search(cargo)
    return _clean_place(m.group("place")) if m else cargo.strip(" .")


def _short(title: str) -> str:
    """Retire « Resolución de 17 de junio de 2026, de la Subsecretaría, » etc. pour ne garder que l'objet."""
    t = re.sub(r"^(Real Decreto|Orden|Resolución|Acuerdo)[^,]*,[^,]*?\b\d{4},?\s*", "", title, count=1)
    m = re.search(r"por (?:el|la) que se (.*)$", title, re.I)
    r = (m.group(1) if m else t).strip(" .")
    return r[:1].upper() + r[1:]


def classify(item: dict) -> Movement | None:
    """Un item du sommaire -> Movement (ou None si hors sujet). Ne lit que le titre."""
    title, sec = item["title"], item["section"]
    if not sec.upper().startswith("2"):      # II.A (nominations) et II.B (concours) seulement
        return None
    if EXCLUDE.search(title):
        return None
    base = dict(date=item.get("date", ""), boe_ids=[item["id"]], urls=[item["url_html"]],
                ministry=item["department"], title=title)

    m = RE_DESIGNA.search(title)
    if m:
        cargo = m.group("cargo").strip()
        return Movement(kind="appointment", person=m.group("name").strip(), posts=[cargo], places=[_place(cargo)], **base)
    m = RE_CESE.search(title)
    if m:
        cargo = m.group("cargo").strip()
        return Movement(kind="cese", person=m.group("name").strip(), posts=[cargo], places=[_place(cargo)], **base)

    if CUES.search(title):
        if RE_RESUELVE.search(title):
            return Movement(kind="resolution", summary=_short(title), **base)
        if RE_CONVOCA.search(title):
            return Movement(kind="vacancy", summary=_short(title), **base)
        return Movement(kind="check", summary=_short(title), **base)
    return None


def group(movements: list[Movement]) -> list[Movement]:
    """Une personne + un événement + un jour = UN mouvement (ex. 5 décrets de cese pour 5 accréditations)."""
    out: dict[str, Movement] = {}
    for mv in movements:
        if mv.kind not in ("appointment", "cese"):
            out[mv.key + "|" + mv.boe_ids[0]] = mv
            continue
        k = mv.key
        if k in out:
            o = out[k]
            o.boe_ids += mv.boe_ids
            o.urls += mv.urls
            o.posts += mv.posts
            o.places += mv.places
        else:
            out[k] = mv
    return list(out.values())


# --- Détail des résolutions / convocations : lignes utiles du texte complet -------------------

def extract_details(text: str, limit: int = 25) -> list[str]:
    """Garde les lignes de l'annexe qui parlent d'un poste (cue) ou ressemblent à une ligne de tableau.
    Extraction volontairement simple : le lien BOE reste la référence."""
    if not text:
        return []
    idx = re.search(r"\bANEXO\b", text)
    body = text[idx.start():] if idx else text
    lines = []
    for ln in body.splitlines():
        ln = ln.strip()
        if len(ln) < 12 or len(ln) > 400:
            continue
        if CUES.search(ln) or ln.count("|") >= 2:
            lines.append(ln[:220])
    seen, uniq = set(), []
    for ln in lines:
        if ln not in seen:
            seen.add(ln)
            uniq.append(ln)
    return uniq[:limit]
