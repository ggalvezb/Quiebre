"""
Cliente de los Web Services de Datos Abiertos de la Camara de Diputadas y Diputados.

Documentacion de los metodos: https://www.camara.cl/transparencia/datosAbiertos.aspx
Los servicios devuelven XML sin autenticacion.

Todo lo que se descarga queda cacheado en disco (carpeta cache/) para que la
actualizacion diaria solo pida lo nuevo.

Uso rapido para inspeccionar una respuesta cruda:
    python -m etl.api probe WSLegislativo retornarVotacionesXAnno prmAnno=2025
"""

from __future__ import annotations

import datetime as dt
import hashlib
import pathlib
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://opendata.camara.cl/camaradiputados/WServices"
UA = "quiebre-etl/1.0 (proyecto ciudadano de transparencia legislativa)"

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CACHE = RAIZ / "cache"

try:
    # algunas instalaciones de Python en Windows (p.ej. Anaconda) traen un
    # contexto SSL por defecto que no encuentra los certificados del sistema;
    # si certifi esta disponible lo usamos, sin volverlo una dependencia dura
    import certifi

    CONTEXTO_SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    CONTEXTO_SSL = ssl.create_default_context()


class ErrorAPI(RuntimeError):
    pass


def _quitar_namespaces(elem: ET.Element) -> ET.Element:
    for e in elem.iter():
        if isinstance(e.tag, str) and "}" in e.tag:
            e.tag = e.tag.split("}", 1)[1]
    return elem


def _ruta_cache(metodo: str, params: dict) -> pathlib.Path:
    clave = urllib.parse.urlencode(sorted(params.items()))
    firma = hashlib.sha1(clave.encode()).hexdigest()[:16] if clave else "sin_params"
    return CACHE / metodo / f"{firma}.xml"


def descargar(
    servicio: str,
    metodo: str,
    params: dict | None = None,
    usar_cache: bool = True,
    reintentos: int = 4,
    pausa: float = 0.4,
) -> ET.Element:
    """Llama a un metodo del web service y devuelve la raiz del XML ya sin namespaces."""
    params = params or {}
    ruta = _ruta_cache(metodo, params)

    if usar_cache and ruta.exists():
        return _quitar_namespaces(ET.fromstring(ruta.read_text(encoding="utf-8")))

    url = f"{BASE}/{servicio}.asmx/{metodo}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    ultimo_error = None
    for intento in range(reintentos):
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(pedido, timeout=60, context=CONTEXTO_SSL) as resp:
                crudo = resp.read().decode("utf-8", errors="replace")
            raiz = _quitar_namespaces(ET.fromstring(crudo))
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(crudo, encoding="utf-8")
            time.sleep(pausa)  # el servicio es publico, no lo saturemos
            return raiz
        except Exception as e:  # noqa: BLE001
            ultimo_error = e
            time.sleep(2 ** intento)

    raise ErrorAPI(f"No se pudo obtener {url}: {ultimo_error}")


# ---------------------------------------------------------------- utilidades


def txt(elem: ET.Element | None, *nombres: str, defecto: str = "") -> str:
    """Devuelve el texto del primer hijo que coincida con alguno de los nombres."""
    if elem is None:
        return defecto
    for nombre in nombres:
        hijo = elem.find(nombre)
        if hijo is not None and hijo.text:
            return hijo.text.strip()
    return defecto


def hijos(raiz: ET.Element, *nombres: str) -> list[ET.Element]:
    """Busca en cualquier nivel los elementos con alguno de esos nombres."""
    for nombre in nombres:
        encontrados = raiz.findall(f".//{nombre}")
        if encontrados:
            return encontrados
    return []


_RE_BOLETIN = re.compile(r"(\d{4,6}-\d{1,3})")


def extraer_boletin(descripcion: str) -> str:
    """El servicio no trae un campo Boletin aparte: viene dentro de
    Descripcion solo para votaciones de "Proyecto de Ley" (p.ej.
    "Boletin N 17324-33"). Resoluciones y acuerdos no tienen boletin."""
    m = _RE_BOLETIN.search(descripcion or "")
    return m.group(1) if m else ""


# ------------------------------------------------------------------ metodos


def periodo_legislativo_actual() -> dict:
    raiz = descargar("WSLegislativo", "retornarPeriodoLegislativoActual", usar_cache=False)
    return {
        "id": txt(raiz, "Id"),
        "nombre": txt(raiz, "Nombre"),
        "inicio": txt(raiz, "FechaInicio"),
        "termino": txt(raiz, "FechaTermino"),
    }


def diputados_periodo_actual() -> list[dict]:
    raiz = descargar("WSDiputado", "retornarDiputadosPeriodoActual", usar_cache=False)
    salida = []
    for d in hijos(raiz, "Diputado", "DiputadoPeriodo"):
        nodo = d.find("Diputado") if d.find("Diputado") is not None else d
        ident = txt(nodo, "Id", "DIPID")
        if not ident:
            continue
        salida.append(
            {
                "id": ident,
                "nombre": txt(nodo, "Nombre"),
                "apellido_paterno": txt(nodo, "ApellidoPaterno"),
                "apellido_materno": txt(nodo, "ApellidoMaterno"),
            }
        )
    # el servicio puede repetir al mismo diputado en distintos tramos
    unicos = {d["id"]: d for d in salida}
    return list(unicos.values())


def detalle_diputado(diputado_id: str) -> dict:
    """Trae la militancia (partido) vigente de un diputado.

    El esquema de WSDiputado.retornarDiputado (confirmado via su WSDL) no
    trae distrito ni region, asi que no se pueden sacar de aqui.
    """
    raiz = descargar("WSDiputado", "retornarDiputado", {"prmDiputadoId": diputado_id})

    hoy = dt.date.today().isoformat()
    partido, ultimo_inicio = "", ""
    for mil in hijos(raiz, "Militancia"):
        p = mil.find("Partido")
        nombre = txt(p, "Nombre", "Alias") if p is not None else ""
        if not nombre:
            continue
        inicio, termino = txt(mil, "FechaInicio")[:10], txt(mil, "FechaTermino")[:10]
        # cada militancia trae su propio rango de fechas (no siempre en orden
        # cronologico); la vigente es la que contiene la fecha de hoy
        if inicio <= hoy and (not termino or hoy <= termino):
            return {"id": diputado_id, "partido": nombre}
        if inicio > ultimo_inicio:
            ultimo_inicio, partido = inicio, nombre

    return {"id": diputado_id, "partido": partido}


def votaciones_del_anno(anno: int, usar_cache: bool = True) -> list[dict]:
    raiz = descargar(
        "WSLegislativo",
        "retornarVotacionesXAnno",
        {"prmAnno": anno},
        usar_cache=usar_cache,
    )
    salida = []
    for v in hijos(raiz, "Votacion", "VotacionProyectoLey"):
        ident = txt(v, "Id")
        if not ident:
            continue
        descripcion = txt(v, "Descripcion", "Articulo", "Tipo")
        salida.append(
            {
                "id": ident,
                "fecha": txt(v, "Fecha"),
                "descripcion": descripcion,
                "boletin": txt(v, "Boletin", "NumeroBoletin") or extraer_boletin(descripcion),
                "resultado": txt(v.find("Resultado"), "Nombre") or txt(v, "Resultado"),
                "tipo": txt(v.find("Tipo"), "Nombre") or txt(v, "Tipo"),
                "quorum": txt(v.find("Quorum"), "Nombre") or txt(v, "Quorum"),
                "total_si": txt(v, "TotalSi", defecto="0"),
                "total_no": txt(v, "TotalNo", defecto="0"),
                "total_abstencion": txt(v, "TotalAbstencion", defecto="0"),
                "total_dispensado": txt(v, "TotalDispensado", defecto="0"),
            }
        )
    return salida


OPCIONES = {
    "afirm": "A",      # a favor
    "favor": "A",
    "contra": "C",     # en contra
    "absten": "B",     # abstencion
    "dispens": "D",    # dispensado (pareo formal, autorizado de antemano)
    "pareo": "D",
    "no vota": "N",    # ausente el dia de la votacion, sin pareo formal
}


def normalizar_opcion(texto: str) -> str:
    """"No Vota" (ausencia simple) y "Dispensado" (pareo formal) se
    distinguen porque son cosas distintas para efectos de asistencia,
    aunque ninguna de las dos entra en el denominador del quiebre."""
    t = (texto or "").strip().lower()
    for clave, codigo in OPCIONES.items():
        if clave in t:
            return codigo
    return "-"


def detalle_votacion(votacion_id: str) -> list[dict]:
    """Devuelve [{diputado_id, opcion}] para una votacion. Se cachea para siempre."""
    raiz = descargar("WSLegislativo", "retornarVotacionDetalle", {"prmVotacionId": votacion_id})
    salida = []
    for voto in hijos(raiz, "Voto"):
        dip = voto.find("Diputado")
        ident = txt(dip, "Id") if dip is not None else txt(voto, "DiputadoId")
        if not ident:
            continue
        nodo_opcion = voto.find("OpcionVoto")
        etiqueta = (nodo_opcion.text if nodo_opcion is not None else "") or ""
        nombre = " ".join(
            p
            for p in [
                txt(dip, "Nombre"),
                txt(dip, "ApellidoPaterno"),
                txt(dip, "ApellidoMaterno"),
            ]
            if p
        )
        salida.append(
            {"diputado_id": ident, "nombre": nombre, "opcion": normalizar_opcion(etiqueta)}
        )
    return salida


# ------------------------------------------------------------------- probe

if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "probe":
        servicio, metodo = sys.argv[2], sys.argv[3]
        params = dict(p.split("=", 1) for p in sys.argv[4:])
        raiz = descargar(servicio, metodo, params, usar_cache=False)
        if hasattr(ET, "indent"):  # Python 3.9+
            ET.indent(raiz, space="  ")
        print(ET.tostring(raiz, encoding="unicode")[:6000])
    else:
        print(__doc__)
