// Front del Planeador. Solo dibuja y llama la API, que a su vez solo llama al motor.
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function api(ruta, params) {
  const r = await fetch("/api/" + ruta + (params ? "?" + new URLSearchParams(params) : ""));
  return r.json();
}
async function post(ruta, cuerpo = {}) {
  const r = await fetch("/api/" + ruta, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  return r.json();
}

// Si el servidor (python app.py) no está corriendo, los botones no pueden llamar al motor.
window.addEventListener("unhandledrejection", (e) => {
  if (!e.reason || e.reason.name !== "TypeError") return;
  if ($("#sin-servidor")) return;
  const aviso = document.createElement("div");
  aviso.id = "sin-servidor";
  aviso.className = "aviso mal";
  aviso.style.cssText = "position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:99;max-width:90vw";
  aviso.textContent = "No hay conexión con el servidor. Abre una terminal en la carpeta del proyecto, ejecuta  python app.py  y entra a http://localhost:8000";
  document.body.appendChild(aviso);
});

let INFO = null;

// ---------------------------------------------------------------- pestañas
$$(".pestanas button").forEach((b) =>
  b.addEventListener("click", () => {
    $$(".pestanas button").forEach((x) => x.classList.toggle("activa", x === b));
    $$(".vista").forEach((v) => v.classList.toggle("activa", v.id === "v-" + b.dataset.vista));
    if (b.dataset.vista === "ranking") cargarRanking();
    history.replaceState(null, "", "#" + b.dataset.vista);
  })
);

// ---------------------------------------------------------------- autocompletar (R2)
// Todas las cajas de estación usan red.autocompletar(prefijo, k) del motor.
function autocompletar(contenedor) {
  const input = $("input", contenedor);
  const lista = document.createElement("ul");
  lista.className = "sugerencias";
  lista.hidden = true;
  lista.setAttribute("role", "listbox");
  contenedor.appendChild(lista);
  let items = [], sel = -1, turno = 0;

  async function pedir() {
    const pref = input.value;
    const k = contenedor.dataset.kFrom ? +$("#" + contenedor.dataset.kFrom).value : 8;
    const mio = ++turno;
    const res = await api("autocompletar", { prefijo: pref, k });
    if (mio !== turno) return;
    items = res; sel = -1;
    const p = pref.trim().length;
    lista.innerHTML = items.map((n, i) => `<li role="option" data-i="${i}"><b>${esc(n.slice(0, p))}</b>${esc(n.slice(p))}</li>`).join("");
    lista.hidden = items.length === 0 || document.activeElement !== input;
  }
  function elegir(i) {
    if (i < 0 || i >= items.length) return;
    input.value = items[i];
    lista.hidden = true;
    input.dispatchEvent(new Event("elegido"));
  }
  input.addEventListener("input", pedir);
  input.addEventListener("focus", pedir);
  input.addEventListener("blur", () => setTimeout(() => (lista.hidden = true), 120));
  input.addEventListener("keydown", (e) => {
    if (lista.hidden) return;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sel = (sel + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      $$("li", lista).forEach((li, i) => li.setAttribute("aria-selected", i === sel));
    } else if (e.key === "Enter" && sel >= 0) { e.preventDefault(); elegir(sel); }
    else if (e.key === "Escape") lista.hidden = true;
  });
  lista.addEventListener("mousedown", (e) => { const li = e.target.closest("li"); if (li) elegir(+li.dataset.i); });
}

function alEnter(input, accion) {
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && $(".sugerencias", input.parentNode)?.hidden !== false) accion(); });
}

// ---------------------------------------------------------------- R1
async function buscarEstado() {
  const nombre = $("#buscar").value;
  const r = await api("estado", { nombre });
  const caja = $("#res-estado");
  if (!r.existe) caja.innerHTML = `<div class="aviso mal">✕ <span><strong>${esc(nombre || "(vacío)")}</strong> no existe en la red.</span></div>`;
  else if (r.abierta) caja.innerHTML = `<div class="aviso ok">● <span><strong>${esc(nombre.toUpperCase())}</strong> existe y está <strong>abierta</strong>.</span></div>`;
  else caja.innerHTML = `<div class="aviso medio">◐ <span><strong>${esc(nombre.toUpperCase())}</strong> existe pero está <strong>cerrada</strong>.</span></div>`;
}
$("#btn-estado").onclick = buscarEstado;
alEnter($("#buscar"), buscarEstado);
$("#buscar").addEventListener("elegido", buscarEstado);

// ---------------------------------------------------------------- R3
async function listarRango() {
  const r = await api("rango", { desde: $("#desde").value, hasta: $("#hasta").value });
  $("#res-rango").innerHTML = r.length
    ? `<p class="meta">${r.length} estaciones abiertas</p><ol class="lista-nombres">${r.map((n) => `<li>${esc(n)}</li>`).join("")}</ol>`
    : `<div class="aviso medio">No hay estaciones abiertas en ese rango.</div>`;
}
$("#btn-rango").onclick = listarRango;

// ---------------------------------------------------------------- R5 (+R4 para la hora)
async function planear() {
  const origen = $("#origen").value, destino = $("#destino").value, hora = $("#hora-viaje").value;
  const r = await api("viaje", { origen, destino });
  const caja = $("#res-viaje");
  if (!r) { caja.innerHTML = `<div class="aviso mal">No hay viaje directo ni con un transbordo (o alguna estación no existe o está cerrada).</div>`; return; }
  if (!r.tramos.length) { caja.innerHTML = `<div class="aviso ok">Ya estás ahí.</div>`; return; }
  let html = `<p class="meta"><strong>${r.paradas}</strong> paradas · ${r.tramos.length === 1 ? "directo" : "1 transbordo"}</p><ol class="tramos">`;
  let h = hora;
  for (let i = 0; i < r.tramos.length; i++) {
    const t = r.tramos[i];
    const bus = (await api("proximo_bus", { estacion: t.sube, ruta: t.ruta, hora: h })).hora;
    html += `<li class="${i ? "cambio" : ""}"><div class="estacion">${esc(t.sube)}</div>
      <div class="detalle">${i ? "Transbordo: toma" : "Toma"} la <span class="pildora">${esc(t.ruta)}</span>
      ${bus ? ` · próximo bus ${bus}` : " · no hay más buses hoy desde aquí"}</div></li>`;
    if (bus) h = bus;
  }
  html += `<li><div class="estacion">${esc(r.tramos[r.tramos.length - 1].baja)}</div><div class="detalle">Bájate aquí</div></li></ol>`;
  caja.innerHTML = html;
}
$("#btn-viaje").onclick = planear;

// ---------------------------------------------------------------- R4
async function cargarRutasDe() {
  const rutas = await api("rutas_de", { estacion: $("#pb-est").value });
  const s = $("#pb-ruta");
  s.innerHTML = rutas.length ? rutas.map((r) => `<option>${esc(r)}</option>`).join("") : `<option value="">(ninguna ruta)</option>`;
}
async function proximoBus() {
  const est = $("#pb-est").value, ruta = $("#pb-ruta").value, hora = $("#pb-hora").value;
  const r = await api("proximo_bus", { estacion: est, ruta, hora });
  $("#res-pb").innerHTML = r.hora
    ? `<div class="aviso ok">La <span class="pildora">${esc(ruta)}</span> pasa por <strong>${esc(est.toUpperCase())}</strong> a las <strong>${r.hora}</strong>.</div>`
    : `<div class="aviso medio">No hay más buses de esa ruta hoy después de ${esc(hora)} (o la estación está cerrada).</div>`;
}
$("#pb-est").addEventListener("elegido", cargarRutasDe);
$("#pb-est").addEventListener("change", cargarRutasDe);
$("#btn-pb").onclick = proximoBus;

// ---------------------------------------------------------------- R6
async function cargarRanking() {
  const k = $("#k-rank").value;
  $("#k-rank-val").textContent = k;
  const r = await api("ranking", { k });
  const max = r.length ? r[0].buses : 1;
  $("#res-ranking").innerHTML = r.map((e) => `<li><span>${esc(e.nombre)}</span><span class="b" style="width:${(100 * e.buses) / max}%"></span><span class="v">${e.buses.toLocaleString("es")}</span></li>`).join("");
}
$("#k-rank").addEventListener("input", cargarRanking);

// ---------------------------------------------------------------- R7 R8 R9
async function cargarRecorrido() {
  const ruta = $("#op-ruta").value;
  const reves = $("#op-reves").checked;
  const rec = await api("recorrido", { ruta, al_reves: reves ? 1 : 0 });
  const cerradas = new Set(INFO.cerradas);
  $("#op-recorrido").innerHTML = rec.map((n) => `<li class="${cerradas.has(n) ? "cerrada" : ""}"><span class="parada">${esc(n)}<button title="Quitar ${esc(n)}" aria-label="Quitar ${esc(n)}" data-quitar="${esc(n)}">×</button></span></li>`).join("");
  const enOrden = reves ? [...rec].reverse() : rec;
  $("#op-despues").innerHTML = `<option value="">(al inicio)</option>` + enOrden.map((n) => `<option>${esc(n)}</option>`).join("");
  if (enOrden.length) $("#op-despues").value = enOrden[0];
}
$("#op-ruta").addEventListener("change", cargarRecorrido);
$("#op-reves").addEventListener("change", cargarRecorrido);
$("#op-recorrido").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-quitar]");
  if (!b) return;
  const r = await post("quitar_parada", { ruta: $("#op-ruta").value, estacion: b.dataset.quitar });
  mensajeOp(r.ok, r.ok ? `Se quitó ${b.dataset.quitar}.` : "No se pudo quitar.");
  aplicarInfo(r.info);
});
$("#btn-agregar").onclick = async () => {
  const nueva = $("#op-nueva").value;
  const r = await post("agregar_parada", { ruta: $("#op-ruta").value, nueva, despues_de: $("#op-despues").value });
  mensajeOp(r.ok, r.ok ? `Se agregó ${nueva.toUpperCase()}.` : "No se pudo agregar: la estación no existe, ya está en la ruta o la posición no es válida.");
  if (r.ok) $("#op-nueva").value = "";
  aplicarInfo(r.info);
};
function mensajeOp(ok, texto) {
  $("#res-op").innerHTML = `<div class="aviso ${ok ? "ok" : "mal"}">${esc(texto)}</div>`;
}
$("#btn-cerrar").onclick = async () => {
  const nombre = $("#op-est").value;
  const r = await post("cerrar", { nombre });
  if (!r.ok) alert("No se pudo cerrar: no existe o ya está cerrada.");
  else $("#op-est").value = "";
  aplicarInfo(r.info);
};
$("#lista-cerradas").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-reabrir]");
  if (b) aplicarInfo((await post("reabrir", { nombre: b.dataset.reabrir })).info);
});
$("#btn-deshacer").onclick = async () => { $("#res-op").innerHTML = ""; aplicarInfo((await post("deshacer")).info); };
$("#btn-rehacer").onclick = async () => { $("#res-op").innerHTML = ""; aplicarInfo((await post("rehacer")).info); };

const NOMBRE_OP = { CERRAR: "Cerrar", REABRIR: "Reabrir", AGREGAR: "Agregar parada", QUITAR: "Quitar parada" };
function aplicarInfo(info) {
  INFO = info;
  const t = info.tamano;
  $("#resumen-red").textContent = `${t.estaciones} estaciones · ${t.rutas} rutas · ${info.cerradas.length} cerradas`;
  $("#lista-cerradas").innerHTML = info.cerradas.length
    ? info.cerradas.map((n) => `<li>${esc(n)} <button data-reabrir="${esc(n)}">Reabrir</button></li>`).join("")
    : `<li class="vacio">Ninguna</li>`;
  const h = info.historial;
  $("#n-deshacer").textContent = h.deshacer;
  $("#n-rehacer").textContent = h.rehacer;
  $("#btn-deshacer").disabled = !h.deshacer;
  $("#btn-rehacer").disabled = !h.rehacer;
  $("#ultima-op").textContent = h.ultima
    ? `Tope de la pila: ${NOMBRE_OP[h.ultima[0]]} · ${h.ultima.slice(1).filter((x) => x).join(" · ")}`
    : "Sin cambios para deshacer.";
  if ($("#op-ruta").value) cargarRecorrido();
  if ($("#v-ranking").classList.contains("activa")) cargarRanking();
}

// ---------------------------------------------------------------- R10
$("#btn-fila").onclick = async () => {
  const b = $("#btn-fila");
  b.disabled = true; b.textContent = "Simulando…";
  const r = await post("fila", {
    pasajeros: +$("#f-n").value, duracion: +$("#f-dur").value, frecuencia: +$("#f-frec").value,
    capacidad: +$("#f-cap").value, patron: $("#f-pat").value,
  });
  b.disabled = false; b.textContent = "Simular";
  if (r.error) { $("#res-fila").innerHTML = `<div class="aviso mal">${esc(r.error)}</div>`; $("#graf-fila").innerHTML = ""; return; }
  const f = (x, d = 1) => x.toLocaleString("es", { maximumFractionDigits: d });
  $("#res-fila").innerHTML = `<div class="stats">
    <div class="stat"><div class="n">${f(r.pasajeros, 0)}</div><div class="t">pasajeros</div></div>
    <div class="stat"><div class="n">${f(r.promedio)} min</div><div class="t">espera promedio</div></div>
    <div class="stat"><div class="n">${f(r.maxima)} min</div><div class="t">espera máxima</div></div>
    <div class="stat"><div class="n">${f(r.buses, 0)}</div><div class="t">buses usados</div></div>
    <div class="stat"><div class="n">${f(r.fin)} min</div><div class="t">sale el último</div></div>
    <div class="stat"><div class="n">${f(r.ms)} ms</div><div class="t">tiempo del motor</div></div></div>`;
  const xs = r.por_minuto.map((_, i) => i);
  $("#graf-fila").innerHTML = grafica(xs, [
    { vals: r.por_minuto, color: "var(--rojo)", nombre: "espera promedio (min)" },
  ], { titulo: "Espera promedio según el minuto de llegada", xlab: "minuto de llegada", ylab: "min", alto: 230, ancho: 900 });
};

// ---------------------------------------------------------------- gráficas SVG
function grafica(xs, series, o = {}) {
  const W = o.ancho || 360, H = o.alto || 200, m = { l: 52, r: 12, t: o.titulo ? 22 : 10, b: 34 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const tx = o.xlog ? (x) => Math.log2(x) : (x) => x;
  const x0 = tx(xs[0]), x1 = tx(xs[xs.length - 1]) || 1;
  let ymax = 0;
  series.forEach((s) => s.vals.forEach((v) => (ymax = Math.max(ymax, v))));
  ymax = ymax * 1.1 || 1;
  const X = (x) => m.l + (x1 === x0 ? iw / 2 : ((tx(x) - x0) / (x1 - x0)) * iw);
  const Y = (y) => m.t + ih - (y / ymax) * ih;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.titulo || "gráfica")}">`;
  if (o.titulo) svg += `<text x="${m.l}" y="14" font-size="12" fill="#6a6c73">${esc(o.titulo)}</text>`;
  for (let i = 0; i <= 4; i++) {
    const v = (ymax / 4) * i, y = Y(v);
    svg += `<line x1="${m.l}" x2="${W - m.r}" y1="${y}" y2="${y}" stroke="#ecebe5"/>`;
    svg += `<text x="${m.l - 6}" y="${y + 4}" font-size="10.5" text-anchor="end" fill="#8a8c92">${fmt(v)}</text>`;
  }
  const marcas = o.xlog ? xs : xs.filter((_, i) => i % Math.ceil(xs.length / 10) === 0);
  marcas.forEach((x) => (svg += `<text x="${X(x)}" y="${H - m.b + 16}" font-size="10.5" text-anchor="middle" fill="#8a8c92">${fmt(x)}</text>`));
  svg += `<text x="${m.l + iw / 2}" y="${H - 4}" font-size="11" text-anchor="middle" fill="#6a6c73">${esc(o.xlab || "")}</text>`;
  svg += `<text x="12" y="${m.t + ih / 2}" font-size="11" fill="#6a6c73" transform="rotate(-90 12 ${m.t + ih / 2})" text-anchor="middle">${esc(o.ylab || "")}</text>`;
  series.forEach((s) => {
    const pts = xs.map((x, i) => `${X(x).toFixed(1)},${Y(s.vals[i]).toFixed(1)}`).join(" ");
    svg += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2" ${s.punteada ? 'stroke-dasharray="5 4"' : ""} stroke-linejoin="round"/>`;
    if (!s.punteada && xs.length < 40) xs.forEach((x, i) => (svg += `<circle cx="${X(x)}" cy="${Y(s.vals[i])}" r="3" fill="${s.color}"><title>${fmt(x)}: ${fmt(s.vals[i])}</title></circle>`));
  });
  return svg + "</svg>";
}
function fmt(v) {
  if (Number.isInteger(v) && v < 1e4) return String(v);
  if (v >= 1e6) return (v / 1e6).toFixed(v >= 1e7 ? 0 : 1) + "M";
  if (v >= 1e4) return (v / 1e3).toFixed(0) + "k";
  if (v >= 100) return Math.round(v).toString();
  if (v >= 10) return v.toFixed(1);
  return v.toFixed(2);
}

// ---------------------------------------------------------------- R11
const CLASE_VEREDICTO = { "coincide": "coincide", "crece más de lo esperado": "crece", "más rápido de lo esperado": "rapido" };
$("#btn-bench").onclick = async () => {
  const factores = $$(".factores input:checked").map((x) => +x.value);
  if (factores.length < 2) { alert("Elige al menos dos tamaños."); return; }
  $("#btn-bench").disabled = true;
  $("#bench-progreso").hidden = false;
  await post("benchmark", { factores });
  seguirBenchmark();
};
async function seguirBenchmark() {
  const e = await api("benchmark");
  $(".barra-prog span").style.width = Math.round(e.progreso * 100) + "%";
  $("#bench-progreso p").textContent = e.corriendo ? `Midiendo: ${e.mensaje}…` : e.error ? "Error: " + e.error : "Listo.";
  if (e.corriendo) { setTimeout(seguirBenchmark, 600); return; }
  $("#btn-bench").disabled = false;
  if (e.resultados) pintarBenchmark(e.resultados);
}
function pintarBenchmark(res) {
  const us = (v) => (v >= 1000 ? (v / 1000).toLocaleString("es", { maximumFractionDigits: 1 }) + " ms" : v.toLocaleString("es", { maximumFractionDigits: 2 }) + " µs");
  let t = `<div class="tabla-bench-envoltura"><table class="tabla-bench"><thead><tr><th>Req.</th><th>Operación</th><th>Esperada</th><th>Tiempo por tamaño</th><th>t(2n)/t(n) medido</th><th>esperado</th><th>Veredicto</th></tr></thead><tbody>`;
  res.forEach((r) => {
    t += `<tr><td><span class="req">${esc(r.requisito)}</span></td><td>${esc(r.operacion)}</td><td><code>${esc(r.esperada)}</code></td>
      <td class="num">${r.tiempos_us.map(us).join(" → ")}</td>
      <td class="num">${r.razones.map((x) => x.toFixed(2)).join(" · ")}</td>
      <td class="num">${r.razones_esperadas.map((x) => x.toFixed(2)).join(" · ")}</td>
      <td><span class="veredicto ${CLASE_VEREDICTO[r.veredicto]}">${esc(r.veredicto)}</span></td></tr>`;
  });
  $("#bench-tabla").innerHTML = t + "</tbody></table></div>";
  $("#bench-graficas").innerHTML = res.map((r) => `<article class="tarjeta graf-card">
      <header><span class="req">${esc(r.requisito)}</span><h3>${esc(r.operacion)}</h3></header>
      <p class="que">Esperada <code>${esc(r.esperada)}</code> · ${esc(r.que_es_n)}</p>
      <div class="graf">${grafica(r.n, [
        { vals: r.esperado_us, color: "#555", punteada: true },
        { vals: r.tiempos_us, color: "var(--rojo)" },
      ], { xlog: true, xlab: r.clave === "r10" ? "pasajeros" : r.clave === "r4h" ? "h (buses)" : "n (estaciones)", ylab: "µs por llamada" })}</div>
      <div class="leyenda"><span><i></i>medido</span><span><i class="esp"></i>esperado ${esc(r.esperada)}</span><span class="veredicto ${CLASE_VEREDICTO[r.veredicto]}">${esc(r.veredicto)}</span></div>
      <p class="expl">${esc(r.explicacion)}</p></article>`).join("");
}

// ---------------------------------------------------------------- inicio
(async function () {
  $$(".auto").forEach(autocompletar);
  const info = await api("info");
  $("#op-ruta").innerHTML = info.rutas.map((r) => `<option>${esc(r)}</option>`).join("");
  aplicarInfo(info);
  cargarRutasDe();
  const vista = location.hash.slice(1);
  if (vista) $(`.pestanas [data-vista="${vista}"]`)?.click();
  // Resultados de un benchmark anterior, si el servidor los tiene.
  const e = await api("benchmark");
  if (e.corriendo) { $("#bench-progreso").hidden = false; $("#btn-bench").disabled = true; seguirBenchmark(); }
  else if (e.resultados) pintarBenchmark(e.resultados);
})();
