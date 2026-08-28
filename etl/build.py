"""
Construye los datos del sitio a partir de los Web Services de la Camara.

    python -m etl.build --desde 2022
    python -m etl.build --desde 2022 --hasta 2026

Escribe en docs/data/: meta.json, diputados.json, votaciones.json, coaliciones.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import unicodedata
from collections import Counter, defaultdict

from . import api

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "data"
CONFIG = pathlib.Path(__file__).resolve().parent / "config" / "coaliciones.json"

SIN_COALICION = "Sin coalicion asignada"


def normaliza(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().strip()


def cargar_config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def mapa_partido_coalicion(config: dict) -> dict[str, str]:
    mapa = {}
    for coalicion, partidos in config["coaliciones"].items():
        for p in partidos:
            mapa[normaliza(p)] = coalicion
    return mapa


def coalicion_de(partido: str, mapa: dict[str, str]) -> str:
    n = normaliza(partido)
    if not n:
        return SIN_COALICION
    if n in mapa:
        return mapa[n]
    # coincidencia parcial: "Partido Socialista de Chile" contiene "partido socialista"
    for clave, coalicion in mapa.items():
        if clave and (clave in n or n in clave):
            return coalicion
    return SIN_COALICION


# --------------------------------------------------------------- extraccion


def recolectar(desde: int, hasta: int) -> tuple[list[dict], dict[str, dict]]:
    """Devuelve (votaciones ordenadas por fecha, votos por votacion)."""
    anno_actual = dt.date.today().year
    votaciones: list[dict] = []
    for anno in range(desde, hasta + 1):
        # el año en curso se vuelve a pedir siempre; los cerrados salen del cache
        print(f"  votaciones {anno}...", file=sys.stderr)
        votaciones += api.votaciones_del_anno(anno, usar_cache=anno < anno_actual)

    votaciones = [v for v in votaciones if v.get("fecha")]
    votaciones.sort(key=lambda v: (v["fecha"], v["id"]))

    detalles: dict[str, list[dict]] = {}
    for i, v in enumerate(votaciones, 1):
        if i % 50 == 0:
            print(f"  detalle {i}/{len(votaciones)}", file=sys.stderr)
        try:
            detalles[v["id"]] = api.detalle_votacion(v["id"])
        except api.ErrorAPI as e:
            print(f"  aviso: sin detalle para votacion {v['id']} ({e})", file=sys.stderr)
            detalles[v["id"]] = []

    return votaciones, detalles


def perfilar_diputados(detalles: dict, mapa: dict[str, str]) -> dict[str, dict]:
    """Universo de diputados que aparecen votando, con partido y coalicion."""
    vistos: dict[str, dict] = {}
    for votos in detalles.values():
        for voto in votos:
            ident = voto["diputado_id"]
            if ident not in vistos:
                vistos[ident] = {"id": ident, "nombre": voto.get("nombre", "")}
            elif not vistos[ident]["nombre"] and voto.get("nombre"):
                vistos[ident]["nombre"] = voto["nombre"]

    for i, (ident, dip) in enumerate(vistos.items(), 1):
        if i % 25 == 0:
            print(f"  ficha {i}/{len(vistos)}", file=sys.stderr)
        try:
            ficha = api.detalle_diputado(ident)
        except api.ErrorAPI:
            ficha = {"partido": "", "distrito": "", "region": ""}
        dip.update(ficha)
        dip["coalicion"] = coalicion_de(dip.get("partido", ""), mapa)
    return vistos


# ------------------------------------------------------------------ calculo


def calcular(votaciones, detalles, diputados, parametros):
    """Compara cada voto con la posicion mayoritaria de su coalicion y de su partido."""
    min_votantes = parametros["min_votantes_coalicion"]
    peso_abstencion = parametros["peso_abstencion"]

    # serie por diputado: un caracter por votacion
    n = len(votaciones)
    serie = {d: ["-"] * n for d in diputados}
    quiebre_coal = {d: ["0"] * n for d in diputados}
    quiebre_part = {d: ["0"] * n for d in diputados}

    acum = {
        d: {"computables": 0.0, "quiebres": 0.0, "part_computables": 0.0, "part_quiebres": 0.0,
            "A": 0, "C": 0, "B": 0, "D": 0}
        for d in diputados
    }
    cohesion_por_coalicion = defaultdict(list)
    posiciones_votacion = []

    for idx, v in enumerate(votaciones):
        votos = {x["diputado_id"]: x["opcion"] for x in detalles.get(v["id"], [])}
        if not votos:
            posiciones_votacion.append({})
            continue

        def posicion(grupo_de: str) -> dict[str, str]:
            conteo = defaultdict(Counter)
            for ident, opcion in votos.items():
                dip = diputados.get(ident)
                if not dip or opcion not in ("A", "C"):
                    continue
                conteo[dip.get(grupo_de) or SIN_COALICION][opcion] += 1
            posiciones = {}
            for grupo, c in conteo.items():
                total = c["A"] + c["C"]
                if total < min_votantes or c["A"] == c["C"]:
                    continue  # grupo chico o empatado: no hay linea que romper
                posiciones[grupo] = "A" if c["A"] > c["C"] else "C"
                if grupo_de == "coalicion":
                    cohesion_por_coalicion[grupo].append(abs(c["A"] - c["C"]) / total)
            return posiciones

        pos_coal = posicion("coalicion")
        pos_part = posicion("partido")
        posiciones_votacion.append(pos_coal)

        for ident, opcion in votos.items():
            dip = diputados.get(ident)
            if not dip:
                continue
            serie[ident][idx] = opcion
            if opcion in acum[ident]:
                acum[ident][opcion] += 1

            for clave, posiciones, quiebres, pre in (
                ("coalicion", pos_coal, quiebre_coal, ""),
                ("partido", pos_part, quiebre_part, "part_"),
            ):
                linea = posiciones.get(dip.get(clave))
                if linea is None or opcion not in ("A", "C", "B"):
                    continue
                acum[ident][f"{pre}computables"] += 1
                if opcion == "B":
                    acum[ident][f"{pre}quiebres"] += peso_abstencion
                elif opcion != linea:
                    acum[ident][f"{pre}quiebres"] += 1
                    quiebres[ident][idx] = "1"

    salida_dip = []
    for ident, dip in diputados.items():
        a = acum[ident]
        comp = a["computables"]
        comp_p = a["part_computables"]
        salida_dip.append(
            {
                "id": ident,
                "nombre": dip.get("nombre", "").strip() or f"Diputado {ident}",
                "partido": dip.get("partido", "") or "Sin registro",
                "coalicion": dip.get("coalicion", SIN_COALICION),
                "distrito": dip.get("distrito", ""),
                "region": dip.get("region", ""),
                "computables": round(comp),
                "quiebres": round(a["quiebres"], 1),
                "indice": round(a["quiebres"] / comp, 4) if comp else None,
                "indice_partido": round(a["part_quiebres"] / comp_p, 4) if comp_p else None,
                "votos": {"a_favor": a["A"], "en_contra": a["C"], "abstencion": a["B"], "dispensado": a["D"]},
                "serie": "".join(serie[ident]),
                "quiebre_serie": "".join(quiebre_coal[ident]),
            }
        )
    salida_dip.sort(key=lambda d: (-1 if d["indice"] is None else -d["indice"]))

    coaliciones = []
    for nombre, valores in cohesion_por_coalicion.items():
        if nombre == SIN_COALICION:
            continue
        coaliciones.append(
            {
                "nombre": nombre,
                "cohesion": round(sum(valores) / len(valores), 4) if valores else None,
                "votaciones_con_linea": len(valores),
                "integrantes": sum(1 for d in salida_dip if d["coalicion"] == nombre),
            }
        )
    coaliciones.sort(key=lambda c: -(c["cohesion"] or 0))

    salida_vot = [
        {
            "id": v["id"],
            "fecha": (v.get("fecha") or "")[:10],
            "descripcion": v.get("descripcion", ""),
            "boletin": v.get("boletin", ""),
            "resultado": v.get("resultado", ""),
            "posiciones": posiciones_votacion[i],
        }
        for i, v in enumerate(votaciones)
    ]

    return salida_dip, salida_vot, coaliciones


# -------------------------------------------------------------------- main


def escribir(diputados, votaciones, coaliciones, meta):
    SALIDA.mkdir(parents=True, exist_ok=True)
    for nombre, dato in (
        ("diputados", diputados),
        ("votaciones", votaciones),
        ("coaliciones", coaliciones),
        ("meta", meta),
    ):
        (SALIDA / f"{nombre}.json").write_text(
            json.dumps(dato, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    print(f"Listo. {len(diputados)} diputados y {len(votaciones)} votaciones en {SALIDA}")


def main() -> None:
    hoy = dt.date.today()
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", type=int, default=hoy.year - 1)
    ap.add_argument("--hasta", type=int, default=hoy.year)
    ap.add_argument("--desde-fecha", default=None, help="ISO yyyy-mm-dd; descarta votaciones anteriores")
    args = ap.parse_args()

    config = cargar_config()
    mapa = mapa_partido_coalicion(config)

    print("Descargando votaciones...", file=sys.stderr)
    votaciones, detalles = recolectar(args.desde, args.hasta)
    if args.desde_fecha:
        votaciones = [v for v in votaciones if v["fecha"] >= args.desde_fecha]
        detalles = {v["id"]: detalles[v["id"]] for v in votaciones}
    print("Descargando fichas de diputados...", file=sys.stderr)
    diputados = perfilar_diputados(detalles, mapa)
    print("Calculando indices...", file=sys.stderr)
    dip, vot, coal = calcular(votaciones, detalles, diputados, config["parametros"])

    sin_mapear = sorted({d["partido"] for d in dip if d["coalicion"] == SIN_COALICION and d["partido"]})
    if sin_mapear:
        print("Partidos sin coalicion asignada (revisa config/coaliciones.json):", file=sys.stderr)
        for p in sin_mapear:
            print(f"  - {p}", file=sys.stderr)

    meta = {
        "origen": "camara.cl/datosAbiertos",
        "actualizado": dt.datetime.now().isoformat(timespec="seconds"),
        "desde": args.desde,
        "hasta": args.hasta,
        "n_votaciones": len(vot),
        "n_diputados": len(dip),
        "rango_fechas": [vot[0]["fecha"], vot[-1]["fecha"]] if vot else ["", ""],
        "parametros": config["parametros"],
        "partidos_sin_coalicion": sin_mapear,
    }
    escribir(dip, vot, coal, meta)


if __name__ == "__main__":
    main()
