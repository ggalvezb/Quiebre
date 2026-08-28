/* Quiebre — vanilla JS, sin build. Lee los JSON que deja el ETL en data/. */

const estado = {
  diputados: [],
  votaciones: [],
  coaliciones: [],
  meta: {},
  filtro: { texto: "", coalicion: "", min: 30 },
  orden: "indice-desc",
  incluirIndependientes: false,
};

const ES_INDEPENDIENTE = (coalicion) => coalicion === "Independientes";

// los independientes no forman una coalicion real; agruparlos como si fuera
// una es una simplificacion editorial, asi que quedan ocultos salvo que el
// usuario los pida explicitamente
function diputadosVisibles() {
  return estado.incluirIndependientes
    ? estado.diputados
    : estado.diputados.filter((d) => !ES_INDEPENDIENTE(d.coalicion));
}

function coalicionesVisibles() {
  return estado.incluirIndependientes
    ? estado.coaliciones
    : estado.coaliciones.filter((c) => !ES_INDEPENDIENTE(c.nombre));
}

const $ = (sel) => document.querySelector(sel);
const pct = (v, dec = 1) => (v == null ? "—" : (v * 100).toFixed(dec) + "%");

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const ETIQUETA = {
  A: "a favor", C: "en contra", B: "se abstuvo",
  D: "fue dispensado (pareo)", N: "estuvo ausente", "-": "sin registro",
};

/* ------------------------------------------------------------ carga */

async function cargar() {
  const [dip, vot, coal, meta] = await Promise.all(
    ["diputados", "votaciones", "coaliciones", "meta"].map((n) =>
      fetch(`data/${n}.json`).then((r) => {
        if (!r.ok) throw new Error(`No se pudo leer data/${n}.json`);
        return r.json();
      })
    )
  );
  Object.assign(estado, { diputados: dip, votaciones: vot, coaliciones: coal, meta });
}

/* --------------------------------------------------- la tira de votos */

function tira(serie, quiebres, alto = 26, clase = "tira") {
  const n = serie.length || 1;
  const w = 1000;
  const paso = w / n;
  const trazos = { ausente: "", alineado: "", abstencion: "", "marca-quiebre": "" };

  for (let i = 0; i < n; i++) {
    const x = (i * paso + paso / 2).toFixed(2);
    const c = serie[i];
    if (quiebres[i] === "1") {
      trazos["marca-quiebre"] += `M${x} 0V${alto}`;
    } else if (c === "D" || c === "N" || c === "-") {
      trazos.ausente += `M${x} ${alto / 2 - 0.75}V${alto / 2 + 0.75}`;
    } else if (c === "B") {
      trazos.abstencion += `M${x} ${alto * 0.33}V${alto * 0.67}`;
    } else {
      trazos.alineado += `M${x} ${alto * 0.19}V${alto * 0.81}`;
    }
  }

  const paths = Object.entries(trazos)
    .filter(([, d]) => d)
    .map(([cls, d]) => `<path class="${cls}" d="${d}" vector-effect="non-scaling-stroke"/>`)
    .join("");

  return `<svg class="${clase}" viewBox="0 0 ${w} ${alto}" preserveAspectRatio="none"
    role="img" aria-label="Historial de votos, de la más antigua a la más reciente">${paths}</svg>`;
}

/* ------------------------------------------------------------- filas */

function filaHTML(d, puesto, campo = "indice", etiqueta = "QUIEBRE") {
  return `
    <button class="fila" data-id="${d.id}" type="button">
      <span class="puesto">${puesto != null ? String(puesto).padStart(2, "0") : ""}</span>
      <span class="nombre">${esc(d.nombre)}<small>Distrito ${esc(d.distrito) || "—"}</small></span>
      <span class="grupo"><b>${esc(d.partido)}</b>${esc(d.coalicion)}</span>
      <span class="celda-tira">${tira(d.serie, d.quiebre_serie)}</span>
      <span class="indice">${pct(d[campo])}<small>${etiqueta}</small></span>
    </button>`;
}

/* --------------------------------------------------------- secciones */

function pintarMarcador() {
  const m = estado.meta;
  const cortes = [
    ["Votaciones", m.n_votaciones],
    ["Diputados", m.n_diputados],
    ["Desde", (m.rango_fechas || [""])[0] || "—"],
    ["Actualizado", (m.actualizado || "").slice(0, 10)],
  ];
  $("#marcador").innerHTML = cortes
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");

  $("#pie-meta").textContent =
    `Fuente: ${m.origen}. Ventana ${m.desde}–${m.hasta}. ` +
    `Una abstención pesa ${m.parametros?.peso_abstencion ?? 0.5} de un quiebre.`;

  if (m.origen === "demo") {
    const aviso = $("#aviso");
    aviso.hidden = false;
    aviso.textContent =
      "Estos son datos de ejemplo generados para revisar el diseño. Ejecuta el ETL para reemplazarlos por los votos reales.";
  }
}

function pintarDestacados() {
  const min = estado.meta.parametros?.min_votaciones_para_ranking ?? 30;
  const top = diputadosVisibles()
    .filter((d) => d.indice != null && d.computables >= min)
    .slice(0, 12);

  $("#bajada-destacados").textContent =
    `Los doce con mayor índice de quiebre entre quienes participaron en al menos ${min} votaciones con línea de coalición definida.`;

  $("#destacados-lista").innerHTML = top
    .map((d, i) => `<li>${filaHTML(d, i + 1)}</li>`)
    .join("");
}

function pintarCohesion() {
  const coaliciones = coalicionesVisibles();
  const max = Math.max(...coaliciones.map((c) => c.cohesion || 0), 1);
  $("#barras-cohesion").innerHTML = coaliciones
    .map(
      (c) => `
      <div class="barra">
        <span class="nom">${esc(c.nombre)}<small>${c.integrantes} integrantes · ${c.votaciones_con_linea} votaciones con línea</small></span>
        <span class="pista"><span class="relleno" style="width:${((c.cohesion || 0) / max) * 100}%"></span></span>
        <span class="val">${pct(c.cohesion, 0)}</span>
      </div>`
    )
    .join("");
}

function pintarAsistencia() {
  const min = estado.meta.parametros?.min_votaciones_para_ranking ?? 30;
  const visibles = diputadosVisibles();

  const votosEmitidos = (d) => d.votos.a_favor + d.votos.en_contra + d.votos.abstencion;
  const top = visibles
    .filter((d) => d.asistencia != null && votosEmitidos(d) >= min)
    .sort((a, b) => a.asistencia - b.asistencia)
    .slice(0, 12);
  $("#asistencia-lista").innerHTML = top
    .map((d, i) => `<li>${filaHTML(d, i + 1, "asistencia", "ASISTENCIA")}</li>`)
    .join("");

  const porCoalicion = new Map();
  for (const d of visibles) {
    if (d.asistencia == null) continue;
    if (!porCoalicion.has(d.coalicion)) porCoalicion.set(d.coalicion, []);
    porCoalicion.get(d.coalicion).push(d.asistencia);
  }
  const promedios = [...porCoalicion.entries()]
    .map(([nombre, vals]) => ({
      nombre,
      promedio: vals.reduce((s, v) => s + v, 0) / vals.length,
      integrantes: vals.length,
    }))
    .sort((a, b) => b.promedio - a.promedio);

  $("#barras-asistencia").innerHTML = promedios
    .map(
      (c) => `
      <div class="barra">
        <span class="nom">${esc(c.nombre)}<small>${c.integrantes} integrantes</small></span>
        <span class="pista"><span class="relleno" style="width:${c.promedio * 100}%"></span></span>
        <span class="val">${pct(c.promedio, 0)}</span>
      </div>`
    )
    .join("");

  const global = visibles.filter((d) => d.asistencia != null);
  const promedioGlobal = global.reduce((s, d) => s + d.asistencia, 0) / (global.length || 1);
  $("#bajada-asistencia").textContent =
    `Asistencia promedio de la Cámara: ${pct(promedioGlobal, 0)}. ` +
    `Los doce que menos asistieron entre quienes emitieron al menos ${min} votos en la ventana de datos.`;
}

function listaFiltrada() {
  const { texto, coalicion, min } = estado.filtro;
  const t = texto.trim().toLowerCase();
  let lista = diputadosVisibles().filter((d) => {
    if (coalicion && d.coalicion !== coalicion) return false;
    if (d.computables < min) return false;
    if (t && !`${esc(d.nombre)} ${esc(d.partido)} ${esc(d.coalicion)}`.toLowerCase().includes(t)) return false;
    return true;
  });

  const cmp = {
    "indice-desc": (a, b) => (b.indice ?? -1) - (a.indice ?? -1),
    "indice-asc": (a, b) => (a.indice ?? 9) - (b.indice ?? 9),
    "asistencia-asc": (a, b) => (a.asistencia ?? 9) - (b.asistencia ?? 9),
    "asistencia-desc": (a, b) => (b.asistencia ?? -1) - (a.asistencia ?? -1),
    nombre: (a, b) => a.nombre.localeCompare(b.nombre, "es"),
    partido: (a, b) => a.partido.localeCompare(b.partido, "es") || a.nombre.localeCompare(b.nombre, "es"),
    "computables-desc": (a, b) => b.computables - a.computables,
  }[estado.orden];

  return lista.sort(cmp);
}

const CAMPO_TABLA = {
  "asistencia-asc": ["asistencia", "ASISTENCIA"],
  "asistencia-desc": ["asistencia", "ASISTENCIA"],
};

function pintarTabla() {
  const lista = listaFiltrada();
  const [campo, etiqueta] = CAMPO_TABLA[estado.orden] || ["indice", "QUIEBRE"];
  $("#conteo").textContent = `${lista.length} de ${diputadosVisibles().length}`;
  $("#tabla").innerHTML = lista.length
    ? lista.map((d) => filaHTML(d, null, campo, etiqueta)).join("")
    : `<p class="vacio">Ningún diputado calza con esos filtros. Prueba bajando el mínimo de votaciones o borrando la búsqueda.</p>`;
}

/* -------------------------------------------------------------- ficha */

function medianaCoalicion(coalicion) {
  const vals = diputadosVisibles()
    .filter((d) => d.coalicion === coalicion && d.indice != null)
    .map((d) => d.indice)
    .sort((a, b) => a - b);
  if (!vals.length) return null;
  const m = Math.floor(vals.length / 2);
  return vals.length % 2 ? vals[m] : (vals[m - 1] + vals[m]) / 2;
}

function abrirFicha(id) {
  const visibles = diputadosVisibles();
  const d = visibles.find((x) => x.id === id);
  if (!d) return;

  const mediana = medianaCoalicion(d.coalicion);
  const puesto = visibles.filter((x) => x.indice != null).findIndex((x) => x.id === id) + 1;

  const quiebres = [];
  for (let i = d.quiebre_serie.length - 1; i >= 0 && quiebres.length < 25; i--) {
    if (d.quiebre_serie[i] === "1") quiebres.push(i);
  }

  const filasQuiebre = quiebres
    .map((i) => {
      const v = estado.votaciones[i] || {};
      const linea = (v.posiciones || {})[d.coalicion];
      return `<li>
        <time datetime="${v.fecha || ""}">${v.fecha || ""}</time>
        <div>
          <p>${esc(v.descripcion) || "Votación sin descripción en la fuente"}${v.boletin ? ` <span class="boletin">Boletín ${esc(v.boletin)}</span>` : ""}</p>
          <p class="contraste">Él o ella votó <b>${ETIQUETA[d.serie[i]]}</b>; su coalición, ${ETIQUETA[linea] || "sin posición registrada"}.</p>
        </div>
      </li>`;
    })
    .join("");

  $("#ficha-cuerpo").innerHTML = `
    <div class="ficha-encabezado">
      <p class="eyebrow" style="color:var(--tinta-3)">Puesto ${puesto} de ${visibles.length}</p>
      <h3>${esc(d.nombre)}</h3>
      <p class="grupo">${esc(d.partido)} · ${esc(d.coalicion)} · Distrito ${esc(d.distrito) || "—"}</p>
    </div>

    <dl class="cifras">
      <div class="cifra destacada">
        <dt>Índice de quiebre</dt><dd>${pct(d.indice)}</dd>
        <p>de sus votos van contra la coalición</p>
      </div>
      <div class="cifra">
        <dt>Mediana de su coalición</dt><dd>${pct(mediana)}</dd>
        <p>${mediana != null && d.indice != null ? (d.indice > mediana ? "se aparta más que la mitad de sus pares" : "se aparta menos que la mitad de sus pares") : ""}</p>
      </div>
      <div class="cifra">
        <dt>Frente a su partido</dt><dd>${pct(d.indice_partido)}</dd>
        <p>mismo cálculo, contra el partido</p>
      </div>
      <div class="cifra">
        <dt>Asistencia</dt><dd>${pct(d.asistencia)}</dd>
        <p>de las votaciones de esta ventana</p>
      </div>
      <div class="cifra">
        <dt>Votaciones contadas</dt><dd>${d.computables}</dd>
        <p>${d.votos.ausente} ausencias, ${d.votos.dispensado} pareos</p>
      </div>
    </dl>

    <div class="bloque">
      <h4>Su historial completo, votación por votación</h4>
      ${tira(d.serie, d.quiebre_serie, 46, "tira tira-detalle")}
      <p class="pista-dato" id="pista-tira">Pasa el cursor sobre la tira para ver cada votación.</p>
      <p class="leyenda">
        <span><i style="background:var(--tinta);opacity:.5"></i> con su coalición</span>
        <span><i style="background:var(--quiebre)"></i> contra su coalición</span>
        <span><i style="background:var(--tinta-2);opacity:.35"></i> abstención</span>
        <span><i style="background:var(--tinta-3);opacity:.35"></i> ausente o pareo</span>
      </p>
    </div>

    <div class="bloque">
      <h4>Últimas veces que se apartó</h4>
      ${filasQuiebre ? `<ul class="quiebres">${filasQuiebre}</ul>` : `<p class="bajada">No hay quiebres registrados en esta ventana de tiempo.</p>`}
    </div>`;

  conectarPistaTira(d);
  $("#ficha").showModal();
}

function conectarPistaTira(d) {
  const svg = $("#ficha-cuerpo .tira-detalle");
  const pista = $("#pista-tira");
  if (!svg) return;

  const mover = (ev) => {
    const caja = svg.getBoundingClientRect();
    const x = (ev.touches ? ev.touches[0].clientX : ev.clientX) - caja.left;
    const i = Math.min(d.serie.length - 1, Math.max(0, Math.floor((x / caja.width) * d.serie.length)));
    const v = estado.votaciones[i] || {};
    const linea = (v.posiciones || {})[d.coalicion];
    pista.textContent =
      `${v.fecha || ""} · votó ${ETIQUETA[d.serie[i]]}` +
      (linea ? ` · coalición ${ETIQUETA[linea]}` : " · coalición sin posición") +
      (v.descripcion ? ` · ${v.descripcion}` : "");
  };

  svg.addEventListener("mousemove", mover);
  svg.addEventListener("touchmove", mover, { passive: true });
  svg.addEventListener("mouseleave", () => {
    pista.textContent = "Pasa el cursor sobre la tira para ver cada votación.";
  });
}

/* ------------------------------------------------------------ eventos */

function conectar() {
  let yaBajo = false;
  $("#buscar").addEventListener("input", (e) => {
    estado.filtro.texto = e.target.value;
    if (estado.filtro.texto.trim() && estado.filtro.min > 0) {
      estado.filtro.min = 0; // al buscar por nombre, nadie debería quedar escondido
      $("#filtro-min").value = "0";
    }
    pintarTabla();
    if (!yaBajo && estado.filtro.texto.trim().length > 1) {
      yaBajo = true;
      $("#ranking").scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });

  $("#filtro-coalicion").addEventListener("change", (e) => {
    estado.filtro.coalicion = e.target.value;
    pintarTabla();
  });

  $("#filtro-min").addEventListener("change", (e) => {
    estado.filtro.min = Number(e.target.value);
    pintarTabla();
  });

  $("#orden").addEventListener("change", (e) => {
    estado.orden = e.target.value;
    pintarTabla();
  });

  document.addEventListener("click", (e) => {
    const fila = e.target.closest(".fila");
    if (fila) abrirFicha(fila.dataset.id);
  });

  $("#cerrar-ficha").addEventListener("click", () => $("#ficha").close());
  $("#ficha").addEventListener("click", (e) => {
    if (e.target === $("#ficha")) $("#ficha").close();
  });

  $("#incluir-independientes").addEventListener("change", (e) => {
    estado.incluirIndependientes = e.target.checked;
    estado.filtro.coalicion = "";
    $("#filtro-coalicion").value = "";
    poblarFiltroCoalicion();
    pintarDestacados();
    pintarCohesion();
    pintarAsistencia();
    pintarTabla();
  });
}

function poblarFiltroCoalicion() {
  const coaliciones = [...new Set(diputadosVisibles().map((d) => d.coalicion))].sort();
  const select = $("#filtro-coalicion");
  select.innerHTML =
    `<option value="">Todas</option>` +
    coaliciones.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("");
}

/* -------------------------------------------------------------- inicio */

cargar()
  .then(() => {
    poblarFiltroCoalicion();
    estado.filtro.min = estado.meta.parametros?.min_votaciones_para_ranking ?? 30;
    $("#filtro-min").value = String(estado.filtro.min);

    pintarMarcador();
    pintarDestacados();
    pintarCohesion();
    pintarAsistencia();
    pintarTabla();
    conectar();
  })
  .catch((err) => {
    $("#tabla").innerHTML = `<p class="vacio">No se pudieron cargar los datos: ${err.message}.
      Genera los archivos con <code>python -m etl.build</code> o <code>python -m etl.demo</code>
      y sirve la carpeta docs con <code>python -m http.server</code>.</p>`;
    console.error(err);
  });
