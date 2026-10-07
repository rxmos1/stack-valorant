"""
Estadísticas de tus compañeros de Valorant usando la API de HenrikDev.

Para cada jugador descarga rango, RR y hasta N_PARTIDAS partidas competitivas recientes,
detecta con cuántos jugadores iba en grupo en cada partida (solo, dúo, trío, cuarteto o
stack de 5) y compara el rendimiento según el tamaño del grupo.

Uso:
    pip install requests
    python valorant_amigos.py
Si no tienes definida la variable HENRIK_API_KEY, el script te pide la clave al arrancar.

Genera resultados_valorant.md, resultados_valorant.json y resultados_valorant.html
(la web se abre sola al terminar; usa --no-abrir para evitarlo).
"""
import html
import json
import os
import sys
import time
import webbrowser
from urllib.parse import quote

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

API_KEY = (os.environ.get("HENRIK_API_KEY") or input("Pega tu clave de HenrikDev y pulsa Enter: ")).strip()
if not API_KEY:
    sys.exit("Falta la clave de la API.")

BASE = "https://api.henrikdev.xyz"
REGION = "eu"
PLATFORM = "pc"
N_PARTIDAS = 30          # partidas competitivas recientes por jugador
PAGINA = 10              # partidas que se piden por petición
PAUSA = float(os.environ.get("HENRIK_PAUSA", "3"))   # segundos entre peticiones

# Revisa que los nombres estén exactamente como en el juego.
JUGADORES = [
    ("Bulcaçan BenHazú", "4017"),
    ("nisk0", "kono"),
    ("FrozenMind", "9811"),
    ("lorcon", "EUW"),
    ("Abadyyy", "2497"),
    ("niskEiiiiiiiiiii", "EAZY"),
    ("FrenchPedicureค", "0104"),
]

ETIQUETA = {1: "Solo", 2: "Dúo", 3: "Trío", 4: "Cuarteto", 5: "Stack de 5"}
ORDEN_GRUPOS = ["Solo", "Dúo", "Trío", "Cuarteto", "Stack de 5"]

HEADERS = {"Authorization": API_KEY}


def get(path, params=None):
    """Devuelve (json_completo, error). Reintenta si la API responde 429."""
    url = f"{BASE}{path}"
    for intento in range(6):
        try:
            r = requests.get(url, headers=HEADERS, params=params, timeout=40)
        except requests.RequestException as e:
            return None, f"Conexión: {e}"
        if r.status_code == 429:
            print("   (límite de peticiones, espero 20 s...)")
            time.sleep(20)
            continue
        time.sleep(PAUSA)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:200]}"
        try:
            return r.json(), None
        except ValueError:
            return None, "Respuesta no válida"
    return None, "Límite de peticiones (429) persistente"


def etiqueta_grupo(n):
    return ETIQUETA.get(n, f"Grupo de {n}")


def datos_basicos(nombre, tag):
    """Rango, RR, pico, puuid e historial de RR por partida."""
    n, t = quote(nombre, safe=""), quote(tag, safe="")
    out = {"nombre": nombre, "tag": tag, "id": f"{nombre}#{tag}", "error": None, "partidas": []}

    j, err = get(f"/valorant/v3/mmr/{REGION}/{PLATFORM}/{n}/{t}")
    if err:
        out["error"] = f"MMR: {err}"
        return out
    mmr = j["data"]
    cur = mmr["current"]
    peak = mmr.get("peak")
    out["rango"] = cur["tier"]["name"]
    out["rr"] = cur["rr"]
    out["ultimo_cambio"] = cur["last_change"]
    out["pico"] = f'{peak["tier"]["name"]} ({peak["season"]["short"]})' if peak else "?"
    out["puuid"] = mmr["account"]["puuid"]

    # RR de cada partida: historial normal + historial almacenado (más largo)
    rr = {}
    j, _ = get(f"/valorant/v2/mmr-history/{REGION}/{PLATFORM}/{n}/{t}")
    if j and isinstance(j.get("data"), dict):
        for h in j["data"].get("history", []):
            rr[h["match_id"]] = h["last_change"]
    j, _ = get(f"/valorant/v2/stored-mmr-history/{REGION}/{PLATFORM}/{n}/{t}", {"size": N_PARTIDAS})
    if j and isinstance(j.get("data"), list):
        for h in j["data"]:
            rr.setdefault(h["match_id"], h.get("last_change", h.get("rr")))
    out["rr_por_partida"] = rr
    return out


def partidas_jugador(jug, nombres_por_puuid):
    n, t = quote(jug["nombre"], safe=""), quote(jug["tag"], safe="")
    vistos, partidas = set(), []
    for inicio in range(0, N_PARTIDAS, PAGINA):
        tam = min(PAGINA, N_PARTIDAS - inicio)
        j, err = get(f"/valorant/v4/matches/{REGION}/{PLATFORM}/{n}/{t}",
                     {"mode": "competitive", "size": tam, "start": inicio})
        if err:
            jug["error"] = f"Partidas: {err}"
            break
        lote = j.get("data") or []
        for m in lote:
            mid = m["metadata"]["match_id"]
            if mid in vistos or not m["metadata"].get("is_completed", True):
                continue
            vistos.add(mid)
            yo = next((p for p in m["players"] if p["puuid"] == jug["puuid"]), None)
            if not yo:
                continue
            equipo = next((tm for tm in m["teams"] if tm["team_id"] == yo["team_id"]), None)
            rondas = (m["teams"][0]["rounds"]["won"] + m["teams"][0]["rounds"]["lost"]) if m["teams"] else 0
            rondas = rondas or 1
            en_grupo = [p for p in m["players"]
                        if p["team_id"] == yo["team_id"] and p["party_id"] == yo["party_id"]]
            con = sorted(nombres_por_puuid[p["puuid"]] for p in en_grupo
                         if p["puuid"] != jug["puuid"] and p["puuid"] in nombres_por_puuid)
            marc = []
            for p in m["players"]:
                ps_ = p["stats"]
                marc.append({
                    "equipo": "mio" if p["team_id"] == yo["team_id"] else "rival",
                    # solo se guarda el nombre de los jugadores del grupo; el resto queda anónimo
                    "nombre": nombres_por_puuid.get(p["puuid"]),
                    "agente": p["agent"]["name"],
                    "k": ps_["kills"], "d": ps_["deaths"], "a": ps_["assists"],
                    "acs": round(ps_["score"] / rondas),
                    "party": p.get("party_id"),
                })
            marc.sort(key=lambda x: (x["equipo"] != "mio", -x["acs"]))
            # party_id se sustituye por un número para no publicar identificadores
            ids = {}
            for x in marc:
                x["party"] = ids.setdefault(x["party"], len(ids) + 1)
            s = yo["stats"]
            tiros = s["headshots"] + s["bodyshots"] + s["legshots"]
            pb = pm = mk = None
            try:
                por_ronda = {}
                for kl in m.get("kills") or []:
                    por_ronda.setdefault(kl["round"], []).append(kl)
                pb = pm = mk = 0
                for ks in por_ronda.values():
                    ks.sort(key=lambda z: z.get("time_in_round_in_ms") or 0)
                    if ks[0]["killer"]["puuid"] == jug["puuid"]:
                        pb += 1
                    if ks[0]["victim"]["puuid"] == jug["puuid"]:
                        pm += 1
                    if sum(1 for z in ks if z["killer"]["puuid"] == jug["puuid"]) >= 3:
                        mk += 1
            except Exception:
                pb = pm = mk = None
            partidas.append({
                "match_id": mid,
                "inicio": m["metadata"]["started_at"],
                "fecha": m["metadata"]["started_at"][:10],
                "mapa": m["metadata"]["map"]["name"],
                "agente": yo["agent"]["name"],
                "victoria": bool(equipo and equipo["won"]),
                "marcador": f'{equipo["rounds"]["won"]}-{equipo["rounds"]["lost"]}' if equipo else "?",
                "k": s["kills"], "d": s["deaths"], "a": s["assists"],
                "acs": round(s["score"] / rondas),
                "adr": round(s["damage"]["dealt"] / rondas),
                "hs": round(100 * s["headshots"] / tiros) if tiros else 0,
                "rr": jug["rr_por_partida"].get(mid),
                "grupo_n": len(en_grupo),
                "grupo": etiqueta_grupo(len(en_grupo)),
                "con": con,
                "marcador_jugadores": marc,
                "primeras_bajas": pb, "primeras_muertes": pm, "multikills": mk,
            })
        if len(lote) < tam:
            break
    jug["partidas"] = partidas[:N_PARTIDAS]


def resumen(ps):
    """Estadísticas agregadas de una lista de partidas."""
    n = len(ps)
    if not n:
        return None
    v = sum(1 for x in ps if x["victoria"])
    k, d = sum(x["k"] for x in ps), sum(x["d"] for x in ps)
    rrs = [x["rr"] for x in ps if x["rr"] is not None]
    return {
        "n": n, "v": v, "d_": n - v, "wr": round(100 * v / n),
        "kd": k / max(d, 1),
        "acs": round(sum(x["acs"] for x in ps) / n),
        "adr": round(sum(x["adr"] for x in ps) / n),
        "hs": round(sum(x["hs"] for x in ps) / n),
        "rr": sum(rrs) if rrs else None,
        "rr_n": len(rrs),
    }


def por_grupo(ps):
    res = {}
    for g in ORDEN_GRUPOS + sorted({x["grupo"] for x in ps} - set(ORDEN_GRUPOS)):
        sub = [x for x in ps if x["grupo"] == g]
        if sub:
            res[g] = resumen(sub)
    return res


def fmt_rr(v):
    return "-" if v is None else f"{v:+d}"


# ------------------------------------------------------------------ Markdown
def tabla_grupos_md(d):
    f = ["| Grupo | Partidas | V-D | % victorias | K/D | ACS | ADR | HS% | RR neto |",
         "|---|---|---|---|---|---|---|---|---|"]
    for g, r in d.items():
        f.append(f"| {g} | {r['n']} | {r['v']}-{r['d_']} | {r['wr']}% | {r['kd']:.2f} | {r['acs']} | "
                 f"{r['adr']} | {r['hs']} | {fmt_rr(r['rr'])} |")
    return f


def resumen_md(jug):
    if jug.get("error") and "rango" not in jug:
        return f"## {jug['id']}\n\nError: {jug['error']}\n"
    ps = jug["partidas"]
    L = [f"## {jug['id']}", "",
         f"**Rango:** {jug['rango']} ({jug['rr']} RR) · **Pico:** {jug['pico']} · "
         f"**Último cambio de RR:** {jug['ultimo_cambio']:+d}"]
    r = resumen(ps)
    if r:
        L.append(f"**Últimas {r['n']}:** {r['v']}V-{r['d_']}D ({r['wr']}%) · K/D {r['kd']:.2f} · "
                 f"ACS medio {r['acs']} · ADR medio {r['adr']} · HS% medio {r['hs']} · "
                 f"RR neto {fmt_rr(r['rr'])} (en {r['rr_n']} partidas con dato)")
        L += ["", "**Según con cuántos jugaba**", ""] + tabla_grupos_md(por_grupo(ps))
        L += ["", "| Fecha | Mapa | Agente | Grupo | Con | Resultado | K/D/A | ACS | ADR | HS% | RR |",
              "|---|---|---|---|---|---|---|---|---|---|---|"]
        for x in ps:
            res = ("Victoria" if x["victoria"] else "Derrota") + " " + x["marcador"]
            L.append(f"| {x['fecha']} | {x['mapa']} | {x['agente']} | {x['grupo']} | "
                     f"{', '.join(x['con']) or '-'} | {res} | {x['k']}/{x['d']}/{x['a']} | "
                     f"{x['acs']} | {x['adr']} | {x['hs']} | {fmt_rr(x['rr'])} |")
    if jug.get("error"):
        L.append(f"\n(Aviso: {jug['error']})")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#f1f5f6;--surface:#fff;--fg:#14232a;--muted:#576a72;--line:#d6e0e3;--chip:#e5edef;--accent:#0a7a87;--win:#1a8447;--loss:#c13a3a}
@media (prefers-color-scheme:dark){:root{--bg:#0d1a1f;--surface:#14252b;--fg:#e3edf0;--muted:#8ea3ab;--line:#25383f;--chip:#1b3037;--accent:#4fc4d0;--win:#4cc27f;--loss:#f06b6b;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,"Segoe UI",sans-serif;padding:24px 16px}
.wrap{max-width:1100px;margin:0 auto;display:flex;flex-direction:column;gap:24px}
h1{margin:0;font-size:34px}h2{margin:0 0 10px;font-size:18px}
.sub,.foot{color:var(--muted);font-size:12px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:16px;min-width:0}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse}
th,td{padding:7px 10px;text-align:left;white-space:nowrap}
th{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line)}
td{border-top:1px solid var(--line)}
.n{text-align:right;font-variant-numeric:tabular-nums;font-family:ui-monospace,Menlo,Consolas,monospace}
th.n{text-align:right}
.w{color:var(--win);font-weight:600}.l{color:var(--loss);font-weight:600}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,520px),1fr));gap:18px}
.card h3{margin:0}.card .rk{color:var(--accent);font-weight:600;margin:2px 0 10px}
.kpis{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}
.kpi{background:var(--chip);border-radius:8px;padding:6px 10px;font-size:12px;color:var(--muted)}
.kpi b{display:block;font-size:16px;color:var(--fg)}
.err{color:var(--loss)}
h4{margin:14px 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:500}
"""


def tabla_grupos_html(d, titulo_col="Grupo"):
    e = html.escape
    filas = ""
    for g, r in d.items():
        cls = "w" if r["wr"] >= 50 else "l"
        filas += (f"<tr><td>{e(g)}</td><td class='n'>{r['n']}</td><td class='n'>{r['v']}-{r['d_']}</td>"
                  f"<td class='n {cls}'>{r['wr']}%</td><td class='n'>{r['kd']:.2f}</td>"
                  f"<td class='n'>{r['acs']}</td><td class='n'>{r['adr']}</td><td class='n'>{r['hs']}</td>"
                  f"<td class='n'>{fmt_rr(r['rr'])}</td></tr>")
    return (f"<div class='scroll'><table><tr><th>{e(titulo_col)}</th><th class='n'>Partidas</th><th class='n'>V-D</th>"
            f"<th class='n'>% vict.</th><th class='n'>K/D</th><th class='n'>ACS</th><th class='n'>ADR</th>"
            f"<th class='n'>HS%</th><th class='n'>RR neto</th></tr>{filas}</table></div>")


def tarjeta_html(jug):
    e = html.escape
    if jug.get("error") and "rango" not in jug:
        return f"<div class='panel card'><h3>{e(jug['id'])}</h3><p class='err'>{e(jug['error'])}</p></div>"
    ps = jug["partidas"]
    r = resumen(ps)
    kp = [("Rango", f"{jug['rango']} · {jug['rr']} RR"), ("Pico", jug["pico"])]
    if r:
        kp += [(f"Últimas {r['n']}", f"{r['v']}V-{r['d_']}D ({r['wr']}%)"), ("K/D", f"{r['kd']:.2f}"),
               ("ACS", str(r["acs"])), ("ADR", str(r["adr"])), ("HS%", str(r["hs"])), ("RR neto", fmt_rr(r["rr"]))]
    kpis = "".join(f"<div class='kpi'>{e(a)}<b>{e(b)}</b></div>" for a, b in kp)
    cuerpo = ""
    if ps:
        cuerpo += "<h4>Según con cuántos jugaba</h4>" + tabla_grupos_html(por_grupo(ps))
        filas = ""
        for x in ps:
            cls = "w" if x["victoria"] else "l"
            filas += (f"<tr><td>{e(x['fecha'])}</td><td>{e(x['mapa'])}</td><td>{e(x['agente'])}</td>"
                      f"<td>{e(x['grupo'])}</td><td class='{cls}'>{'Victoria' if x['victoria'] else 'Derrota'} {e(x['marcador'])}</td>"
                      f"<td class='n'>{x['k']}/{x['d']}/{x['a']}</td><td class='n'>{x['acs']}</td>"
                      f"<td class='n'>{x['adr']}</td><td class='n'>{x['hs']}</td><td class='n'>{fmt_rr(x['rr'])}</td></tr>")
        cuerpo += ("<h4>Partidas</h4><div class='scroll'><table><tr><th>Fecha</th><th>Mapa</th><th>Agente</th>"
                   "<th>Grupo</th><th>Resultado</th><th class='n'>K/D/A</th><th class='n'>ACS</th><th class='n'>ADR</th>"
                   f"<th class='n'>HS%</th><th class='n'>RR</th></tr>{filas}</table></div>")
    aviso = f"<p class='err'>{e(jug['error'])}</p>" if jug.get("error") else ""
    return (f"<div class='panel card'><h3>{e(jug['id'])}</h3><div class='rk'>{e(jug['rango'])}</div>"
            f"<div class='kpis'>{kpis}</div>{cuerpo}{aviso}</div>")


def pagina_html(datos):
    e = html.escape
    todas = [x for j in datos for x in j["partidas"]]
    glob = tabla_grupos_html(por_grupo(todas), "Grupo (todos los jugadores)") if todas else ""
    # una fila por jugador y tamaño de grupo: % de victorias
    cab = "".join(f"<th class='n'>{g}</th>" for g in ORDEN_GRUPOS)
    filas = ""
    for j in datos:
        if not j["partidas"]:
            continue
        g = por_grupo(j["partidas"])
        celdas = "".join(
            (f"<td class='n'>{g[k]['wr']}% <span class='sub'>({g[k]['n']})</span></td>" if k in g else "<td class='n'>-</td>")
            for k in ORDEN_GRUPOS)
        filas += f"<tr><td>{e(j['id'])}</td>{celdas}</tr>"
    comp = (f"<div class='scroll'><table><tr><th>Jugador</th>{cab}</tr>{filas}</table></div>"
            "<p class='sub'>% de victorias y, entre paréntesis, número de partidas en ese tipo de grupo.</p>") if filas else ""
    tarjetas = "".join(tarjeta_html(j) for j in datos)
    ahora = time.strftime("%d/%m/%Y %H:%M")
    return (f"<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>Stack Valorant</title><style>{CSS}</style></head><body><div class='wrap'>"
            f"<header><h1>Stack Valorant</h1><div class='sub'>Actualizado {ahora} · últimas {N_PARTIDAS} partidas "
            f"competitivas por jugador</div></header>"
            f"<section class='panel'><h2>Rendimiento según el tamaño del grupo</h2>{glob}</section>"
            f"<section class='panel'><h2>% de victorias por jugador y tipo de grupo</h2>{comp}</section>"
            f"<section><div class='cards'>{tarjetas}</div></section>"
            f"<p class='foot'>Fuente: API de HenrikDev. El tamaño del grupo es el número de jugadores del mismo equipo "
            f"que iban en la misma party, sean o no del grupo.</p></div></body></html>")


# ---------------------------------------------------------------------- main
def main():
    print("Fase 1/2: rango y RR de cada jugador")
    datos = []
    for nombre, tag in JUGADORES:
        print(f" - {nombre}#{tag}")
        datos.append(datos_basicos(nombre, tag))
    nombres_por_puuid = {d["puuid"]: d["nombre"] for d in datos if d.get("puuid")}

    print("Fase 2/2: partidas (tarda unos minutos)")
    for d in datos:
        if "puuid" not in d:
            continue
        print(f" - {d['id']}")
        partidas_jugador(d, nombres_por_puuid)
        print(f"   {len(d['partidas'])} partidas")

    for d in datos:
        d.pop("rr_por_partida", None)
        d.pop("puuid", None)

    todas = [x for d in datos for x in d["partidas"]]
    texto = "# Compañeros de Valorant\n\n"
    if todas:
        texto += ("## Todos los jugadores juntos, según el tamaño del grupo\n\n"
                  + "\n".join(tabla_grupos_md(por_grupo(todas))) + "\n\n")
    texto += "\n".join(resumen_md(d) for d in datos)

    with open("resultados_valorant.md", "w", encoding="utf-8") as f:
        f.write(texto)
    with open("resultados_valorant.json", "w", encoding="utf-8") as f:
        json.dump({"actualizado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                   "n_partidas": N_PARTIDAS, "jugadores": datos}, f, ensure_ascii=False, indent=1)
    with open("resultados_valorant.html", "w", encoding="utf-8") as f:
        f.write(pagina_html(datos))
    print(texto)
    print("\nGuardado en resultados_valorant.md, resultados_valorant.json y resultados_valorant.html")
    if "--no-abrir" not in sys.argv:
        try:
            webbrowser.open("file://" + os.path.abspath("resultados_valorant.html"))
        except Exception:
            pass


if __name__ == "__main__":
    main()
