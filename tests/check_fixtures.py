"""Vérifie la classification, le regroupement, la tolérance du parcours JSON et l'alerte, sur des titres RÉELS du BOE
(décrets du 27/10/2026, Real Decretos désignant des ambassadeurs, résolutions Carrière diplomatique / Travail / Économie).
Lancé par le workflow avant chaque run : échoue (et bloque) en cas de régression. Aucun accès réseau."""

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import boe  # noqa: E402
import digest  # noqa: E402
from classify import classify, extract_details, group  # noqa: E402

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


payload = json.loads((ROOT / "fixtures" / "sumario_20261028.json").read_text(encoding="utf-8"))
items = list(boe.iter_items(payload))
check(len(items) == 16, f"parcours JSON : {len(items)} items lus au lieu de 16")
check(any(i["id"] == "BOE-A-2026-90004" for i in items), "parcours : item sous epigrafe/item en objet unique non lu")
check({i["section"] for i in items} == {"2A", "2B", "1"}, "parcours : sections mal lues")

mvs = []
for it in items:
    it["date"] = "2026-10-28"
    mv = classify(it)
    if mv:
        mvs.append(mv)
kinds = sorted(m.kind for m in mvs)
check(kinds.count("cese") == 6, f"cese : {kinds.count('cese')} au lieu de 6")
check(kinds.count("appointment") == 3, f"appointment : {kinds.count('appointment')} au lieu de 3 (Canada, Inde, UE)")
check(kinds.count("resolution") == 1, "résolution Carrière diplomatique non reconnue")
check(kinds.count("vacancy") == 1, "convocation Consejerías de Trabajo non reconnue")
check("check" not in kinds, "faux positif 'check'")
check(not any("BOE-A-2026-90003" in m.boe_ids or "BOE-A-2026-22453" in m.boe_ids or "BOE-A-2026-90005" in m.boe_ids or "BOE-A-2026-23140" in m.boe_ids or "BOE-A-2026-22923" in m.boe_ids for m in mvs),
      "bruit (université, cabinet, section I) classé à tort")

g = group(mvs)
ceses = {m.person: m for m in g if m.kind == "cese"}
check(len(ceses) == 2, f"regroupement : {len(ceses)} personnes en cese au lieu de 2")
mp = ceses.get("Juan Antonio March Pujol")
check(mp is not None and len(mp.places) == 5 and len(mp.boe_ids) == 5, "March Pujol : 5 décrets doivent donner UN mouvement à 5 lieux")
check(ceses.get("Alfredo Martínez Serrano") is not None and ceses["Alfredo Martínez Serrano"].places == ["Canadá"], "Martínez Serrano / Canadá")
check(mp is not None and mp.places[0] == "India" and mp.places[-1] == "Sri Lanka", f"nettoyage des lieux : {mp and mp.places}")
app = {m.person: m for m in g if m.kind == "appointment"}
check(app.get("Marcos Alonso Alonso") is not None and app["Marcos Alonso Alonso"].places == ["Unión Europea"], "représentant permanent UE")
check(app.get("María Luisa Benítez-Donoso Tarascón") is not None, "nomination au féminin (Embajadora) non lue")

d = digest.build(g, date(2026, 10, 21), date(2026, 10, 28))
check(d is not None and "3 appointments" in d["subject"] and "2 ends of mission" in d["subject"], f"objet de l'alerte : {d and d['subject']}")
check(d is not None and "5 accreditations" in d["body"] and "March Pujol" in d["body"], "alerte : regroupement non affiché")
check(digest.build([], date(2026, 10, 21), date(2026, 10, 28)) is None, "pas d'alerte quand rien de nouveau")

xml = ("<texto><p>Resolución ...</p><p>ANEXO</p><table><tr><td>1</td><td>Apellido Nombre</td><td>Cónsul General</td>"
       "<td>Consulado General de España en Marsella</td></tr></table><p>Otra frase sin interés para el test.</p></texto>")
det = extract_details(boe.xml_to_text(xml))
check(any("Marsella" in x for x in det), f"extraction du détail d'annexe : {det}")

if failures:
    print("ÉCHECS :")
    for f in failures:
        print(" -", f)
    sys.exit(1)
print("OK : classification, regroupement, parcours JSON, alerte")
