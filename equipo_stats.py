"""Estadisticas de EQUIPO (pistolas, ataque/defensa, primeras bajas, ronda 2...) -> equipo.json"""
import json
import datetime
from urllib.parse import quote
import valorant_amigos as va

NOMBRES = [x[0].lower() for x in va.JUGADORES]
partidas = {}
for nombre, tag in va.JUGADORES:
    n, t = quote(nombre, safe=""), quote(tag, safe="")
    j, err = va.get(f"/valorant/v4/matches/{va.REGION}/{va.PLATFORM}/{n}/{t}", {"mode": "competitive", "size": 30})
    if err:
        print("ERROR", nombre, err); continue
    for m in j.get("data") or []:
        if not m["metadata"].get("is_completed", True): continue
        mid = m["metadata"]["match_id"]
        yo = next((p for p in m["players"] if p["name"].lower() == nombre.lower()), None)
        if not yo:
            print("sin jugador", nombre, mid); continue
        if mid in partidas: continue
        mi = yo["team_id"]
        otro = [p["team_id"] for p in m["players"] if p["team_id"] != mi][0]
        equipos = {p["puuid"]: p["team_id"] for p in m["players"]}
        rs = {r["id"]: r for r in (m.get("rounds") or [])}
        if 0 not in rs: continue
        atq = None
        for r in m.get("rounds") or []:
            if r["id"] < 12 and r.get("plant") and r["plant"].get("player"):
                atq = r["plant"]["player"]["team"]; break
        pist = []
        for rid in (0, 12):
            if rid not in rs: continue
            gano = rs[rid].get("winning_team") == mi
            lado = None
            if atq is not None:
                a = atq if rid == 0 else [x for x in (mi, otro) if x != atq][0]
                lado = "atq" if a == mi else "def"
            sig = rs.get(rid + 1)
            pist.append({"r": rid + 1, "lado": lado, "gano": gano,
                         "r2": None if not sig else sig.get("winning_team") == mi})
        a = [0, 0]; d = [0, 0]
        if atq is not None:
            for rid, r in rs.items():
                if rid >= 24: continue
                ataca = atq if rid < 12 else [x for x in (mi, otro) if x != atq][0]
                lado = a if ataca == mi else d
                lado[1] += 1
                if r.get("winning_team") == mi: lado[0] += 1
        # primera baja de cada ronda: rondas ganadas cuando la consigue el equipo / el rival
        fb = [0, 0]; fbc = [0, 0]
        por_ronda = {}
        for kl in m.get("kills") or []:
            por_ronda.setdefault(kl["round"], []).append(kl)
        for rid, ks in por_ronda.items():
            ks.sort(key=lambda z: z.get("time_in_round_in_ms") or 0)
            eqk = equipos.get(ks[0]["killer"]["puuid"])
            gano = rs.get(rid, {}).get("winning_team") == mi
            dest = fb if eqk == mi else fbc
            dest[1] += 1
            if gano: dest[0] += 1
        tm = next((x for x in m["teams"] if x["team_id"] == mi), {})
        partidas[mid] = {
            "id": mid, "inicio": m["metadata"].get("started_at"), "mapa": m["metadata"]["map"]["name"],
            "w": bool(tm.get("won")), "marcador": f"{tm.get('rounds', {}).get('won')}-{tm.get('rounds', {}).get('lost')}",
            "pist": pist, "atq": a, "def": d, "fb": fb, "fbc": fbc,
            "n": sum(1 for p in m["players"] if p["team_id"] == mi and p["name"].lower() in NOMBRES),
        }

lista = sorted(partidas.values(), key=lambda x: x["inicio"] or "")
json.dump({"actualizado": datetime.datetime.utcnow().isoformat() + "Z", "partidas": lista},
          open("equipo.json", "w", encoding="utf-8"), ensure_ascii=False)
tot = [0, 0]
for p in lista:
    for x in p["pist"]:
        tot[1] += 1; tot[0] += x["gano"]
print("partidas", len(lista), "pistolas ganadas/jugadas", tot)
