"""
Planeador de viajes TransMilenio · aplicación web.

    python app.py            -> abre http://localhost:8000

Solo usa la librería estándar (http.server, json, threading): no hay que
instalar nada. Este archivo NO tiene reglas del sistema: cada endpoint llama
un método del motor y devuelve el resultado en JSON. Lo único que hace aquí es
leer parámetros, generar llegadas aleatorias para el simulador y armar el
histograma de esperas para dibujarlo.
"""
import json
import os
import random
import sys
import threading
import traceback
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from motor import Red, simular_fila, resumen_fila
import rendimiento

RAIZ = os.path.dirname(os.path.abspath(__file__))
DATOS = os.path.join(RAIZ, "datos")
ESTATICOS = os.path.join(RAIZ, "web")
PUERTO = int(os.environ.get("PUERTO", "8000"))

red = Red(DATOS)
candado = threading.Lock()

benchmark_estado = {"corriendo": False, "mensaje": "", "progreso": 0.0,
                    "resultados": None, "error": None}


def info():
    est, rutas, pares = red.tamano()
    d, h, ultima = red.historial()
    return {
        "estaciones": red.nombres_estaciones(),
        "rutas": red.nombres_rutas(),
        "cerradas": red.cerradas(),
        "tamano": {"estaciones": est, "rutas": rutas, "pares": pares},
        "historial": {"deshacer": d, "rehacer": h, "ultima": list(ultima) if ultima else None},
    }


def tramos_json(tramos):
    return [{"ruta": r, "sube": s, "baja": b} for r, s, b in tramos]


def api_get(ruta, q):
    g = lambda k, d="": q.get(k, [d])[0]
    if ruta == "info":
        return info()
    if ruta == "estado":
        existe, abierta = red.estado(g("nombre"))
        return {"existe": existe, "abierta": abierta}
    if ruta == "autocompletar":
        return red.autocompletar(g("prefijo"), int(g("k", "10")))
    if ruta == "rango":
        return red.rango(g("desde"), g("hasta"))
    if ruta == "rutas_de":
        return red.rutas_de(g("estacion"))
    if ruta == "proximo_bus":
        return {"hora": red.proximo_bus(g("estacion"), g("ruta"), g("hora"))}
    if ruta == "viaje":
        r = red.viaje_con_paradas(g("origen"), g("destino"))
        if r is None:
            return None
        return {"paradas": r[0], "tramos": tramos_json(r[1])}
    if ruta == "ranking":
        return [{"nombre": n, "buses": b} for n, b in red.ranking(int(g("k", "10")))]
    if ruta == "recorrido":
        return red.recorrido(g("ruta"), g("al_reves") == "1")
    if ruta == "benchmark":
        return {k: benchmark_estado[k] for k in benchmark_estado}
    raise KeyError(ruta)


def api_post(ruta, cuerpo):
    c = lambda k, d=None: cuerpo.get(k, d)
    if ruta == "agregar_parada":
        ok = red.agregar_parada(c("ruta"), c("nueva"), c("despues_de") or None)
    elif ruta == "quitar_parada":
        ok = red.quitar_parada(c("ruta"), c("estacion"))
    elif ruta == "cerrar":
        ok = red.cerrar(c("nombre"))
    elif ruta == "reabrir":
        ok = red.reabrir(c("nombre"))
    elif ruta == "deshacer":
        ok = red.deshacer()
    elif ruta == "rehacer":
        ok = red.rehacer()
    elif ruta == "fila":
        return simular(cuerpo)
    elif ruta == "benchmark":
        return lanzar_benchmark(cuerpo)
    else:
        raise KeyError(ruta)
    return {"ok": ok, "info": info()}


def simular(cuerpo):
    n = max(1, min(int(cuerpo.get("pasajeros", 100000)), 2_000_000))
    duracion = float(cuerpo.get("duracion", 60))          # minutos de hora pico
    frecuencia = float(cuerpo.get("frecuencia", 2))
    capacidad = int(cuerpo.get("capacidad", 160))
    pico = cuerpo.get("patron", "pico") == "pico"
    rnd = random.Random(int(cuerpo.get("semilla", 1)))
    if pico:  # más gente en la mitad de la hora pico (triangular)
        llegadas = [rnd.triangular(0, duracion, duracion / 2) for _ in range(n)]
    else:
        llegadas = [rnd.uniform(0, duracion) for _ in range(n)]
    llegadas.sort()
    import time
    t0 = time.perf_counter()
    salidas = simular_fila(llegadas, frecuencia, capacidad)
    ms = (time.perf_counter() - t0) * 1000
    if salidas is None:
        return {"error": "frecuencia y capacidad deben ser mayores que 0"}
    promedio, maxima, buses = resumen_fila(llegadas, salidas)
    # Histograma de espera promedio por minuto de llegada (para graficar).
    cubetas = max(1, int(duracion))
    suma = [0.0] * cubetas
    cuenta = [0] * cubetas
    for a, s in zip(llegadas, salidas):
        i = min(cubetas - 1, int(a))
        suma[i] += s - a
        cuenta[i] += 1
    return {
        "pasajeros": n, "promedio": promedio, "maxima": maxima, "buses": buses,
        "ms": ms, "fin": salidas[-1],
        "por_minuto": [suma[i] / cuenta[i] if cuenta[i] else 0 for i in range(cubetas)],
        "llegadas_por_minuto": cuenta,
    }


def lanzar_benchmark(cuerpo):
    if benchmark_estado["corriendo"]:
        return benchmark_estado
    factores = cuerpo.get("factores") or [1, 2, 4, 8]
    factores = [int(f) for f in factores if 1 <= int(f) <= 32]

    def trabajo():
        try:
            def avance(msg, p):
                benchmark_estado["mensaje"] = msg
                benchmark_estado["progreso"] = p
            benchmark_estado["resultados"] = rendimiento.benchmark(factores, al_avanzar=avance)
        except Exception as e:  # se muestra en la página
            benchmark_estado["error"] = repr(e)
            traceback.print_exc()
        finally:
            benchmark_estado["corriendo"] = False

    benchmark_estado.update({"corriendo": True, "mensaje": "Preparando redes", "progreso": 0.0,
                             "error": None, "resultados": None})
    threading.Thread(target=trabajo, daemon=True).start()
    return benchmark_estado


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def responder(self, codigo, datos, tipo="application/json; charset=utf-8"):
        cuerpo = datos if isinstance(datos, bytes) else json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path.startswith("/api/"):
            try:
                with candado:
                    self.responder(200, api_get(url.path[5:], parse_qs(url.query)))
            except KeyError:
                self.responder(404, {"error": "no existe"})
            except Exception as e:
                self.responder(400, {"error": str(e)})
            return
        nombre = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
        ruta = os.path.normpath(os.path.join(ESTATICOS, nombre))
        if not ruta.startswith(ESTATICOS) or not os.path.isfile(ruta):
            self.responder(404, b"no encontrado", "text/plain")
            return
        tipos = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
        with open(ruta, "rb") as f:
            self.responder(200, f.read(), tipos.get(os.path.splitext(ruta)[1], "application/octet-stream"))

    def do_POST(self):
        url = urlparse(self.path)
        largo = int(self.headers.get("Content-Length", 0) or 0)
        try:
            cuerpo = json.loads(self.rfile.read(largo) or b"{}")
            if url.path == "/api/benchmark":
                self.responder(200, api_post("benchmark", cuerpo))
                return
            with candado:
                self.responder(200, api_post(url.path[5:], cuerpo))
        except KeyError:
            self.responder(404, {"error": "no existe"})
        except Exception as e:
            self.responder(400, {"error": str(e)})


if __name__ == "__main__":
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    direccion = "http://localhost:%d" % PUERTO
    print("Planeador TransMilenio en %s  (Ctrl+C para salir)" % direccion)
    if "--sin-navegador" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(direccion)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
