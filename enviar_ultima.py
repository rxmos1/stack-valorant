"""Reenvía a Discord el aviso de la última partida de un jugador (envío manual)."""
import json
import os
import sys

import valorant_amigos as va

buscado = (os.environ.get("AVISO_JUGADOR") or "niskei").strip().lower()
datos = json.load(open("data.json", encoding="utf-8"))
js = datos.get("jugadores", [])
js = js if isinstance(js, list) else list(js.values())


def nom(j):
    return (j.get("nombre") or j.get("name") or "")


base = [j for j in js if buscado in nom(j).lower()]
if not base:
    sys.exit("No encuentro a ese jugador en data.json")
jug = base[0]
ps = sorted(jug.get("partidas", []), key=lambda m: m.get("inicio") or "", reverse=True)
if not ps:
    sys.exit("Ese jugador no tiene partidas")
mid = ps[0].get("match_id")
nuevos = {}
for j in js:
    ms = [m for m in j.get("partidas", []) if m.get("match_id") == mid]
    if ms:
        d = dict(j)
        d["partidas"] = ms
        nuevos[(nom(j), "")] = d
print("Partida", mid, "con", len(nuevos), "jugador(es) del grupo")
va.avisar_discord(nuevos, {}, max_horas=24 * 365)
