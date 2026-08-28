"""
Genera datos ficticios con el mismo esquema que build.py, para revisar el sitio
sin depender de la API. Los nombres son inventados.

    python -m etl.demo
"""

from __future__ import annotations

import datetime as dt
import json
import random

from .build import SALIDA, escribir

random.seed(11)

COALICIONES = {
    "Chile Vamos": (["UDI", "RN", "Evopoli"], 52, 0.965),
    "Republicanos y aliados": (["Republicano", "PNL", "PSC"], 38, 0.975),
    "Oficialismo": (["PS", "PPD", "PC", "FA", "FRVS"], 55, 0.955),
    "Democratas y Amarillos": (["Democratas", "Amarillos"], 10, 0.90),
}

NOMBRES = ["Ana", "Bruno", "Camila", "Diego", "Elena", "Felipe", "Gloria", "Hector", "Ines",
           "Joaquin", "Karla", "Lucas", "Marta", "Nicolas", "Olivia", "Pablo", "Rocio", "Sergio",
           "Teresa", "Ulises", "Valeria", "Ximena", "Yerko", "Zoe"]
APELLIDOS = ["Aravena", "Bustos", "Cifuentes", "Duarte", "Escalona", "Fuentealba", "Gajardo",
             "Huenchumilla", "Illanes", "Jaramillo", "Krause", "Leiva", "Molina", "Nunez",
             "Olate", "Paredes", "Quiroga", "Rebolledo", "Sandoval", "Tapia", "Urrutia",
             "Valdivia", "Wagner", "Yanez", "Zambrano"]

TEMAS = ["reforma previsional", "presupuesto 2026", "ley de seguridad", "permisos sectoriales",
         "royalty regional", "subsidio al arriendo", "ley de datos personales", "salario minimo",
         "reforma al sistema politico", "ley marco de suelos", "copago cero",
         "modernizacion del Estado", "delitos economicos", "regulacion de plataformas"]
GLOSA = ["en general", "en particular, articulo 1", "en particular, articulo 12",
         "indicacion renovada", "informe de comision mixta", "clausura del debate"]


def main() -> None:
    hoy = dt.date.today()
    n_vot = 420
    fechas = sorted(
        (hoy - dt.timedelta(days=random.randint(0, 540))).isoformat() for _ in range(n_vot)
    )

    diputados = []
    ident = 1000
    for coalicion, (partidos, escanos, disciplina) in COALICIONES.items():
        for _ in range(escanos):
            ident += 1
            propension = max(0.005, random.gauss(1 - disciplina, 0.022))
            diputados.append(
                {
                    "id": str(ident),
                    "nombre": f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)} {random.choice(APELLIDOS)}",
                    "partido": random.choice(partidos),
                    "coalicion": coalicion,
                    "distrito": str(random.randint(1, 28)),
                    "region": "",
                    "_propension": propension,
                }
            )

    lineas = [
        {c: random.choice("AC") for c in COALICIONES} for _ in range(n_vot)
    ]

    votaciones = []
    for i, fecha in enumerate(fechas):
        votaciones.append(
            {
                "id": str(90000 + i),
                "fecha": fecha,
                "descripcion": f"Proyecto sobre {random.choice(TEMAS)}, {random.choice(GLOSA)}",
                "boletin": f"{random.randint(14000, 16999)}-{random.randint(1, 25):02d}",
                "resultado": random.choice(["Aprobado", "Rechazado"]),
                "posiciones": lineas[i],
            }
        )

    for d in diputados:
        serie, quiebres = [], []
        computables = quiebre_peso = 0.0
        conteo = {"A": 0, "C": 0, "B": 0, "D": 0}
        for i in range(n_vot):
            if random.random() < 0.12:
                serie.append("D")
                quiebres.append("0")
                conteo["D"] += 1
                continue
            linea = lineas[i][d["coalicion"]]
            r = random.random()
            if r < d["_propension"]:
                opcion = "C" if linea == "A" else "A"
            elif r < d["_propension"] * 1.8:
                opcion = "B"
            else:
                opcion = linea
            serie.append(opcion)
            conteo[opcion] += 1
            computables += 1
            if opcion == "B":
                quiebre_peso += 0.5
                quiebres.append("0")
            elif opcion != linea:
                quiebre_peso += 1
                quiebres.append("1")
            else:
                quiebres.append("0")

        d.pop("_propension")
        d.update(
            {
                "computables": int(computables),
                "quiebres": round(quiebre_peso, 1),
                "indice": round(quiebre_peso / computables, 4) if computables else None,
                "indice_partido": round(quiebre_peso / computables * random.uniform(0.7, 1.1), 4)
                if computables
                else None,
                "votos": {
                    "a_favor": conteo["A"],
                    "en_contra": conteo["C"],
                    "abstencion": conteo["B"],
                    "dispensado": conteo["D"],
                },
                "serie": "".join(serie),
                "quiebre_serie": "".join(quiebres),
            }
        )

    diputados.sort(key=lambda d: -(d["indice"] or 0))

    coaliciones = []
    for nombre, (_, escanos, disciplina) in COALICIONES.items():
        coaliciones.append(
            {
                "nombre": nombre,
                "cohesion": round(disciplina - random.uniform(0, 0.03), 4),
                "votaciones_con_linea": n_vot,
                "integrantes": escanos,
            }
        )
    coaliciones.sort(key=lambda c: -c["cohesion"])

    meta = {
        "origen": "demo",
        "actualizado": dt.datetime.now().isoformat(timespec="seconds"),
        "desde": int(fechas[0][:4]),
        "hasta": int(fechas[-1][:4]),
        "n_votaciones": n_vot,
        "n_diputados": len(diputados),
        "rango_fechas": [fechas[0], fechas[-1]],
        "parametros": {"min_votantes_coalicion": 4, "peso_abstencion": 0.5,
                       "min_votaciones_para_ranking": 30},
        "partidos_sin_coalicion": [],
    }

    escribir(diputados, votaciones, coaliciones, meta)
    print(f"Datos de ejemplo escritos en {SALIDA}")


if __name__ == "__main__":
    main()
