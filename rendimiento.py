"""
R11 · Benchmarks del motor con redes de tamaño creciente (n, 2n, 4n, ...).

Está FUERA de motor/: solo usa el motor a través de su contrato público
(from motor import Red, simular_fila) y puede usar cualquier librería.

Cómo se agranda la red: se copia la red real `factor` veces. La copia j
renombra estaciones ("AGUAS" -> "AGUAS #2") y rutas ("1-1" -> "1-1#2"), así
n (número de estaciones), el número de rutas y el número de horarios crecen
exactamente por `factor`. Es el mismo método que usa el script del profesor:
duplicar la red y ver cómo crece el tiempo.

Uso por consola:
    python rendimiento.py            # imprime la tabla de resultados
"""
import csv
import gc
import math
import os
import random
import statistics
import tempfile
import time

from motor import Red, simular_fila

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
CACHE = os.path.join(tempfile.gettempdir(), "transmilenio_bench")


# --------------------------------------------------------------- redes escaladas
def _leer(carpeta, archivo):
    with open(os.path.join(carpeta, archivo), newline="", encoding="utf-8") as f:
        filas = list(csv.reader(f))
    return filas[0], filas[1:]


def crear_red_escalada(factor, base=BASE, cache=CACHE):
    """Escribe (o reutiliza) la red base copiada `factor` veces y devuelve la carpeta."""
    destino = os.path.join(cache, "x%d" % factor)
    if os.path.exists(os.path.join(destino, "horarios.csv")):
        return destino
    os.makedirs(destino, exist_ok=True)
    sufijo_est = lambda j: "" if j == 1 else " #%d" % j
    sufijo_ruta = lambda j: "" if j == 1 else "#%d" % j

    enc, est = _leer(base, "estaciones.csv")
    with open(os.path.join(destino, "estaciones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(enc)
        for j in range(1, factor + 1):
            for (nombre,) in est:
                w.writerow([nombre + sufijo_est(j)])

    enc, rutas = _leer(base, "rutas.csv")
    with open(os.path.join(destino, "rutas.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(enc)
        for j in range(1, factor + 1):
            for ruta, orden, estacion in rutas:
                w.writerow([ruta + sufijo_ruta(j), orden, estacion + sufijo_est(j)])

    enc, hor = _leer(base, "horarios.csv")
    tmp = os.path.join(destino, "horarios.tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(enc)
        for j in range(1, factor + 1):
            for ruta, estacion, hora in hor:
                w.writerow([ruta + sufijo_ruta(j), estacion + sufijo_est(j), hora])
    os.replace(tmp, os.path.join(destino, "horarios.csv"))
    return destino


def crear_red_horarios(h, cache=CACHE):
    """Red mínima de 1 ruta y 2 estaciones con h buses en la primera estación.
    Sirve para ver R4 contra h (con la red duplicada h no crece)."""
    destino = os.path.join(cache, "h%d" % h)
    if os.path.exists(os.path.join(destino, "horarios.csv")):
        return destino
    os.makedirs(destino, exist_ok=True)
    with open(os.path.join(destino, "estaciones.csv"), "w", newline="") as f:
        f.write("nombre\nA\nB\n")
    with open(os.path.join(destino, "rutas.csv"), "w", newline="") as f:
        f.write("ruta,orden,estacion\nR,1,A\nR,2,B\n")
    rnd = random.Random(h)
    minutos = sorted(rnd.randrange(1440) for _ in range(h))
    with open(os.path.join(destino, "horarios.csv"), "w", newline="") as f:
        f.write("ruta,estacion,hora\n")
        for m in minutos:
            f.write("R,A,%02d:%02d\n" % (m // 60, m % 60))
    return destino


# --------------------------------------------------------------- cronómetro
def cronometrar(funcion, argumentos, lotes=5):
    """Corre funcion(*a) para cada a en argumentos, `lotes` veces.
    Devuelve la MEDIANA del tiempo por llamada (segundos): la mediana descarta
    lotes interrumpidos por el sistema operativo.

    Igual que el módulo timeit, se apaga el recolector de basura de Python
    mientras se mide: sus recolecciones recorren TODOS los objetos vivos, así
    que con una red grande harían ver más lenta una operación O(1) que no
    cambió (se estaría midiendo el recolector, no la estructura)."""
    tiempos = []
    gc.collect()
    gc.disable()
    try:
        for _ in range(lotes):
            t0 = time.perf_counter()
            for a in argumentos:
                funcion(*a)
            tiempos.append((time.perf_counter() - t0) / len(argumentos))
    finally:
        gc.enable()
    return statistics.median(tiempos)


# --------------------------------------------------------------- complejidades
CURVAS = {
    "O(1)": lambda n: 1.0,
    "O(log n)": lambda n: math.log2(max(n, 2)),
    "O(n)": lambda n: float(n),
    "O(n log n)": lambda n: n * math.log2(max(n, 2)),
}

OPERACIONES = [
    # clave, requisito, etiqueta, complejidad esperada, qué es n, explicación
    ("carga", "Carga", "Red(carpeta)", "O(n)", "n = filas de los CSV (crece con la red)",
     "Leer cada fila e insertarla en tablas hash es O(1) amortizado por fila. Si los "
     "horarios vienen desordenados se suma O(h log h) por par (ruta, estación), pero "
     "h no crece al duplicar la red, así que la carga crece lineal."),
    ("r1", "R1", "estado(nombre)", "O(1)", "n = estaciones",
     "Tabla hash: una cubeta por consulta (la cubeta más llena tiene ~4 pares). Con la "
     "red x8 sube un poco, pero no es la estructura: medimos la red x1 sola (1.55 us) y "
     "con la x8 cargada en memoria (2.01 us). Es la caché del procesador: con más "
     "objetos vivos los datos quedan más dispersos en RAM."),
    ("r2", "R2", "autocompletar(prefijo, 10)", "O(log n)", "n = estaciones, k = 10 fijo",
     "Búsqueda binaria del primer nombre >= prefijo y luego se leen k seguidos. Con k "
     "fijo domina log n, que casi no se nota al duplicar (log 2n = log n + 1)."),
    ("r3", "R3", "rango(desde, hasta) con m = 10", "O(log n)", "n = estaciones, m = 10 fijo",
     "Búsqueda binaria de 'desde' y recorrido de las m estaciones del rango. Si el "
     "rango creciera con la red el costo sería O(log n + m), lineal en m."),
    ("r4", "R4", "proximo_bus(estacion, ruta, hora)", "O(1)", "h = buses por (ruta, estación): no crece al duplicar",
     "Al duplicar la red cada par (ruta, estación) conserva sus h buses, así que la "
     "búsqueda binaria hace el mismo trabajo: plano. La gráfica 'R4 vs h' muestra el "
     "log h cuando sí crece h."),
    ("r4h", "R4", "proximo_bus con h creciente", "O(log n)", "n = h, buses de esa ruta en esa estación",
     "Búsqueda binaria en el arreglo ordenado de minutos: cada vez que h se duplica se "
     "hace una comparación más."),
    ("r5", "R5", "viaje(origen, destino)", "O(1)", "Exenta. Costo O(R·p): R rutas del origen/destino, p paradas por ruta",
     "R5 no depende de n: solo recorre las rutas que pasan por el origen y el destino. "
     "Al duplicar la red esas rutas no cambian, por eso es plano. Se varía según los pares sorteados."),
    ("r6", "R6", "ranking(10) sin cambios", "O(1)", "k = 10 fijo; n = estaciones",
     "El arreglo ya está ordenado (bandera sucio = False): leer los primeros k es O(k)."),
    ("r6s", "R6", "ranking(10) tras un cierre", "O(n log n)", "n = estaciones abiertas",
     "Un cierre marca sucio = True y la siguiente consulta reordena con merge sort, "
     "O(n log n). Por eso solo se reordena cuando algo cambió."),
    ("r7", "R7", "agregar_parada + quitar_parada", "O(1)", "n = estaciones",
     "Tabla hash (ruta, estación) -> nodo y cambio de 4 punteros en la lista doble."),
    ("r7r", "R7", "recorrido(ruta)", "O(1)", "p = paradas de la ruta: no crece al duplicar",
     "Recorre la lista enlazada: O(p). Al duplicar la red cada ruta conserva sus p paradas."),
    ("r8", "R8", "cerrar + reabrir", "O(1)", "n = estaciones",
     "Tabla hash para hallar la estación y cambiar el booleano abierta."),
    ("r9", "R9", "deshacer + rehacer", "O(1)", "n = estaciones",
     "Dos pilas sobre arreglos: apilar y desapilar al final."),
    ("r10", "R10", "simular_fila(llegadas, 3, 100)", "O(n)", "n = pasajeros",
     "Cola FIFO con índice frente: cada pasajero entra y sale una vez, O(1) cada vez."),
]


def _argumentos(red, rnd, cantidad):
    nombres = red.nombres_estaciones()
    rutas = red.nombres_rutas()
    pares = []
    for ruta in rutas:
        for est in red.recorrido(ruta):
            pares.append((ruta, est))
    elegir = lambda arr: [arr[rnd.randrange(len(arr))] for _ in range(cantidad)]
    horas = ["%02d:%02d" % (rnd.randrange(5, 22), rnd.randrange(60)) for _ in range(cantidad)]
    est = elegir(nombres)
    idx = [rnd.randrange(len(nombres) - 10) for _ in range(cantidad)]
    return {
        "r1": [(e,) for e in est],
        "r2": [(e[:3], 10) for e in est],
        "r3": [(nombres[i], nombres[i + 9]) for i in idx],
        "r4": [(e, r, h) for (r, e), h in zip(elegir(pares), horas)],
        "r5": [(a, b) for a, b in zip(est, elegir(nombres))][: max(20, cantidad // 20)],
        "pares": elegir(pares),
        "est": est,
    }


def benchmark(factores=(1, 2, 4, 8), consultas=2000, semilla=7, al_avanzar=None):
    """Devuelve una lista de resultados, uno por operación:
        {clave, requisito, operacion, esperada, que_es_n, explicacion,
         n: [...], tiempos_us: [...], esperado_us: [...], razones: [...], veredicto}
    """
    rnd = random.Random(semilla)
    medidas = {op[0]: ([], []) for op in OPERACIONES}

    def anotar(clave, n, segundos):
        medidas[clave][0].append(n)
        medidas[clave][1].append(segundos * 1e6)

    for paso, factor in enumerate(factores):
        if al_avanzar:
            al_avanzar("Red x%d" % factor, paso / (len(factores) + 1))
        carpeta = crear_red_escalada(factor)
        t0 = time.perf_counter()
        red = Red(carpeta)
        carga = time.perf_counter() - t0
        n = red.tamano()[0]
        anotar("carga", n, carga)
        a = _argumentos(red, rnd, consultas)

        anotar("r1", n, cronometrar(red.estado, a["r1"]))
        anotar("r2", n, cronometrar(red.autocompletar, a["r2"]))
        anotar("r3", n, cronometrar(red.rango, a["r3"]))
        anotar("r4", n, cronometrar(red.proximo_bus, a["r4"]))
        anotar("r5", n, cronometrar(red.viaje, a["r5"], lotes=3))
        red.ranking(10)
        anotar("r6", n, cronometrar(red.ranking, [(10,)] * consultas))

        objetivo = a["est"][0]
        def cierre_y_ranking():
            red.cerrar(objetivo)
            red.ranking(10)
            red.reabrir(objetivo)
            red.ranking(10)
        anotar("r6s", n, cronometrar(cierre_y_ranking, [()] * 10, lotes=3) / 2)

        # R7: quitar una parada intermedia y volver a ponerla en su sitio.
        pares_r7 = []
        for ruta, est in a["pares"]:
            rec = red.recorrido(ruta)
            if len(rec) >= 3 and est != rec[0]:
                pares_r7.append((ruta, est, rec[_posicion(rec, est) - 1]))
        def quitar_y_agregar(ruta, est, anterior):
            red.quitar_parada(ruta, est)
            red.agregar_parada(ruta, est, anterior)
        anotar("r7", n, cronometrar(quitar_y_agregar, pares_r7) / 2)
        anotar("r7r", n, cronometrar(red.recorrido, [(r,) for r, _ in a["pares"]]))

        def cerrar_reabrir(e):
            red.cerrar(e)
            red.reabrir(e)
        anotar("r8", n, cronometrar(cerrar_reabrir, a["r1"]) / 2)
        red.cerrar(objetivo)
        def deshacer_rehacer():
            red.deshacer()
            red.rehacer()
        anotar("r9", n, cronometrar(deshacer_rehacer, [()] * consultas) / 2)
        red.deshacer()

        pasajeros = 50_000 * factor
        llegadas = sorted(rnd.uniform(0, 3600) for _ in range(pasajeros))
        anotar("r10", pasajeros, cronometrar(simular_fila, [(llegadas, 3, 100)], lotes=3))
        del red

    if al_avanzar:
        al_avanzar("R4 contra h", len(factores) / (len(factores) + 1))
    for h in [1000 * f for f in (1, 2, 4, 8, 16, 32, 64)]:
        red = Red(crear_red_horarios(h))
        horas = [("A", "R", "%02d:%02d" % (rnd.randrange(24), rnd.randrange(60)))
                 for _ in range(consultas)]
        anotar("r4h", h, cronometrar(red.proximo_bus, horas))

    resultados = []
    for clave, req, etiqueta, esperada, que_es_n, explicacion in OPERACIONES:
        ns, ts = medidas[clave]
        curva = CURVAS[esperada]
        # La curva esperada se ancla en la primera medición: c * f(n).
        c = ts[0] / curva(ns[0])
        esperado = [c * curva(x) for x in ns]
        razones = [ts[i] / ts[i - 1] for i in range(1, len(ts))]
        razones_esp = [curva(ns[i]) / curva(ns[i - 1]) for i in range(1, len(ns))]
        resultados.append({
            "clave": clave, "requisito": req, "operacion": etiqueta,
            "esperada": esperada, "que_es_n": que_es_n, "explicacion": explicacion,
            "n": ns, "tiempos_us": ts, "esperado_us": esperado,
            "razones": razones, "razones_esperadas": razones_esp,
            "veredicto": veredicto(razones, razones_esp),
        })
    if al_avanzar:
        al_avanzar("Listo", 1.0)
    return resultados


def _posicion(arreglo, x):
    for i, y in enumerate(arreglo):
        if y == x:
            return i
    return -1


def veredicto(razones, razones_esperadas):
    """Mismo criterio del script del profesor: duplicar n y mirar la razón
    t(2n) / t(n). Se toma la MEDIANA de las razones medidas (una duplicación
    con ruido no decide sola) y se compara con la razón teórica f(2n) / f(n):
        O(1) -> 1,  O(log n) -> ~1.1,  O(n) -> 2,  O(n log n) -> ~2.2
    Tolerancia de 50 % por ruido del cronómetro y efectos de caché."""
    medida = statistics.median(razones)
    teorica = statistics.median(razones_esperadas)
    if medida > teorica * 1.5:
        return "crece más de lo esperado"
    if medida < teorica / 1.5:
        return "más rápido de lo esperado"
    return "coincide"


if __name__ == "__main__":
    for r in benchmark(al_avanzar=lambda m, p: print("...", m)):
        print("%-4s %-36s %-11s %-34s %-24s %s" % (
            r["requisito"], r["operacion"], r["esperada"],
            " ".join("%.2f" % t for t in r["tiempos_us"]),
            " ".join("%.2f" % t for t in r["razones"]), r["veredicto"]))
