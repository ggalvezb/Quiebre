/* Quiebre — pagina de asistencia. Comparte datos con app.js pero no su render. */

const estado = {
  diputados: [],
  meta: {},
  filtro: { texto: "" },
  orden: "asistencia-asc",
  incluirIndependientes: false,
};

const ES_INDEPENDIENTE = (coalicion) => coalicion === "Independientes";

// el mapa de coaliciones original (etl/config/coaliciones.json) no se toca;
// esto es solo el nombre que se muestra en el sitio
const NOMBRE_MOSTRADO = { Oficialismo: "Oposición" };
const nombreCoalicion = (c) => NOMBRE_MOSTRADO[c] || c;

function diputadosVisibles() {
  return estado.incluirIndependientes
    ? estado.diputados
    : estado.diputados.filter((d) => !ES_INDEPENDIENTE(d.coalicion));
}

const $ = (sel) => document.querySelector(sel);
const pct = (v, dec = 0) => (v == null ? "—" : (v * 100).toFixed(dec) + "%");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------ carga */

async function cargar() {
  const [dip, meta] = await Promise.all(
    ["diputados", "meta"].map((n) =>
      fetch(`data/${n}.json`).then((r) => {
        if (!r.ok) throw new Error(`No se pudo leer data/${n}.json`);
        return r.json();
      })
    )
  );
  Object.assign(estado, { diputados: dip, meta });
}

/* -------------------------------------------------------- barra apilada */

function stackHTML(d) {
  const { a_favor, en_contra, abstencion, ausente, dispensado } = d.votos;
  const segmentos = [
    { clase: "seg-presente", n: a_favor + en_contra + abstencion },
    { clase: "seg-ausente", n: ausente },
    { clase: "seg-dispensado", n: dispensado },
  ].filter((s) => s.n > 0);

  return segmentos
    .map((s) => `<span class="seg ${s.clase}" style="flex-grow:${s.n}" title="${s.n}"></span>`)
    .join("");
}

function filaHTML(d, puesto) {
  return `
    <button class="stack-fila" data-id="${d.id}" type="button" title="${esc(d.nombre)}: ${pct(d.asistencia)} de asistencia">
      <span class="puesto">${String(puesto).padStart(2, "0")}</span>
      <span class="nombre">${esc(d.nombre)}<small>${esc(d.partido)} · ${esc(nombreCoalicion(d.coalicion))}</small></span>
      <span class="stack">${stackHTML(d)}</span>
      <span class="indice">${pct(d.asistencia)}<small>ASISTENCIA</small></span>
    </button>`;
}

/* --------------------------------------------------------- secciones */

function pintarMarcador() {
  const m = estado.meta;
  const visibles = diputadosVisibles().filter((d) => d.asistencia != null);
  const promedio = visibles.reduce((s, d) => s + d.asistencia, 0) / (visibles.length || 1);

  const cortes = [
    ["Diputados", visibles.length],
    ["Asistencia promedio", pct(promedio)],
    ["Desde", (m.rango_fechas || [""])[0] || "—"],
    ["Actualizado", (m.actualizado || "").slice(0, 10)],
  ];
  $("#marcador").innerHTML = cortes
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");

  $("#pie-meta").textContent = `Fuente: ${m.origen}. Ventana ${m.desde}–${m.hasta}.`;
}

function listaFiltrada() {
  const { texto } = estado.filtro;
  const t = texto.trim().toLowerCase();
  let lista = diputadosVisibles().filter((d) => {
    if (d.asistencia == null) return false;
    if (t && !`${esc(d.nombre)} ${esc(d.partido)} ${esc(d.coalicion)} ${esc(nombreCoalicion(d.coalicion))}`.toLowerCase().includes(t)) return false;
    return true;
  });

  const cmp = {
    "asistencia-asc": (a, b) => a.asistencia - b.asistencia,
    "asistencia-desc": (a, b) => b.asistencia - a.asistencia,
    nombre: (a, b) => a.nombre.localeCompare(b.nombre, "es"),
    coalicion: (a, b) =>
      nombreCoalicion(a.coalicion).localeCompare(nombreCoalicion(b.coalicion), "es") ||
      a.nombre.localeCompare(b.nombre, "es"),
  }[estado.orden];

  return lista.sort(cmp);
}

function pintarComposicion() {
  const lista = listaFiltrada();
  $("#conteo").textContent = `${lista.length} de ${diputadosVisibles().length}`;
  $("#bajada-composicion").textContent =
    "Cada barra resume toda la ventana de datos: qué proporción de las votaciones el diputado " +
    "votó, estuvo ausente o fue dispensado.";
  $("#stack-lista").innerHTML = lista.length
    ? lista.map((d, i) => filaHTML(d, i + 1)).join("")
    : `<p class="vacio">Ningún diputado calza con esa búsqueda.</p>`;
}

function pintarComparativoCoaliciones() {
  const visibles = diputadosVisibles().filter((d) => d.asistencia != null);
  const porCoalicion = new Map();
  for (const d of visibles) {
    if (!porCoalicion.has(d.coalicion)) porCoalicion.set(d.coalicion, []);
    porCoalicion.get(d.coalicion).push(d.asistencia);
  }
  const filas = [...porCoalicion.entries()]
    .map(([nombre, vals]) => ({
      nombre,
      promedio: vals.reduce((s, v) => s + v, 0) / vals.length,
      integrantes: vals.length,
    }))
    .sort((a, b) => b.promedio - a.promedio);

  const eje = `
    <div class="chart-fila chart-eje">
      <span class="chart-etiqueta"></span>
      <div class="chart-pista chart-pista-eje">
        <span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span>
      </div>
      <span class="chart-val"></span>
    </div>`;

  const filasHTML = filas
    .map(
      (c) => `
      <div class="chart-fila">
        <span class="chart-etiqueta">${esc(nombreCoalicion(c.nombre))}<small>${c.integrantes} integrantes</small></span>
        <div class="chart-pista">
          <span class="chart-barra" style="width:${c.promedio * 100}%"></span>
        </div>
        <span class="chart-val">${pct(c.promedio)}</span>
      </div>`
    )
    .join("");

  $("#chart-coaliciones").innerHTML = eje + filasHTML;
}

/* ------------------------------------------------------------ eventos */

function conectar() {
  $("#buscar").addEventListener("input", (e) => {
    estado.filtro.texto = e.target.value;
    pintarComposicion();
  });

  $("#orden").addEventListener("change", (e) => {
    estado.orden = e.target.value;
    pintarComposicion();
  });

  $("#incluir-independientes").addEventListener("change", (e) => {
    estado.incluirIndependientes = e.target.checked;
    pintarMarcador();
    pintarComposicion();
    pintarComparativoCoaliciones();
  });
}

/* -------------------------------------------------------------- inicio */

cargar()
  .then(() => {
    pintarMarcador();
    pintarComposicion();
    pintarComparativoCoaliciones();
    conectar();
  })
  .catch((err) => {
    $("#stack-lista").innerHTML = `<p class="vacio">No se pudieron cargar los datos: ${err.message}.
      Genera los archivos con <code>python -m etl.build</code> o <code>python -m etl.demo</code>
      y sirve la carpeta docs con <code>python -m http.server</code>.</p>`;
    console.error(err);
  });
