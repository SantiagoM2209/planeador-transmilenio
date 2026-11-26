"""
Conversión del GTFS de TransMilenio a los tres CSV que lee el motor.

Uso:
    python convertir_gtfs.py [ruta_al_zip] [carpeta_salida]

Por defecto lee gtfs/GTFS-2021-07-14.zip y escribe en datos/.

Este script está FUERA del motor, así que aquí se permite cualquier librería
(usamos pandas, unicodedata, re, zipfile).

Decisiones (documentadas también en el README):
  * Solo se toma el componente TRONCAL (route_desc == "TRONCAL"): son las
    estaciones de TransMilenio propiamente dichas.
  * Solo se toman los viajes de un DÍA HÁBIL típico (servicios con
    wednesday == 1 en calendar.txt). Así "buses al día" tiene sentido.
  * Una estación tiene varios vagones/plataformas en el GTFS
    ("Ricaurte A - 1 ó 5", "Portal Sur T9"...). El nombre de la estación es el
    nombre de la parada sin el sufijo de vagón/plataforma.
  * Nombres en MAYÚSCULAS, sin tildes, espacios colapsados, sin repetidos.
  * Cada ruta va en un solo sentido: un mismo route_short_name tiene varios
    patrones de paradas (sentidos y variantes). Cada patrón distinto es una
    ruta del CSV. Si hay un solo patrón se conserva el nombre ("A51"); si hay
    varios se numeran "1-1", "1-2", ... de más viajes a menos.
  * Dentro de un patrón, paradas consecutivas en la misma estación (dos
    vagones) se fusionan y si una estación reaparece más adelante se ignora la
    repetición: así (ruta, estacion) es único, que es lo que exige R7.
  * Horas: HH:MM truncando los segundos. Las horas >= 24:00 (servicio que sigue
    después de medianoche, p. ej. 25:10) se pasan a la hora real del reloj
    restando 24 (25:10 -> 01:10), porque el horario se repite todos los días
    y el bus de las 25:10 es exactamente el que un usuario ve pasar a la 01:10.
  * Se eliminan horarios exactamente repetidos (ruta, estacion, hora).
"""
import csv
import os
import re
import sys
import unicodedata
import zipfile

import pandas as pd

SUFIJO_VAGON = re.compile(r"\s+[A-Z]\s*-\s*\d.*$")          # " A - 2 ó 5"
SUFIJO_PORTAL = re.compile(r"\s+T\s*-?\s*\d+\s*[A-Z]?\s*$", re.I)  # " T-3B", " T9"


def normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = "".join(c for c in texto if c.isascii())  # quita "º" de "1º de Mayo"
    texto = re.sub(r"\s+", " ", texto).strip().upper()
    return texto


def nombre_estacion(stop_name):
    nombre = SUFIJO_VAGON.sub("", str(stop_name))
    nombre = SUFIJO_PORTAL.sub("", nombre)
    return normalizar(nombre)


def a_minutos(hhmmss):
    partes = str(hhmmss).strip().split(":")
    return int(partes[0]) * 60 + int(partes[1])


def a_hhmm(minutos):
    minutos = minutos % (24 * 60)  # 25:10 -> 01:10
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def convertir(zip_path, salida):
    z = zipfile.ZipFile(zip_path)
    leer = lambda n, **kw: pd.read_csv(z.open(n), dtype=str, encoding="utf-8", **kw)

    routes = leer("routes.txt")
    routes = routes[routes["route_desc"].str.upper() == "TRONCAL"]
    nombre_ruta = dict(zip(routes["route_id"], routes["route_short_name"].map(normalizar)))

    cal = leer("calendar.txt")
    servicios = set(cal.loc[cal["wednesday"] == "1", "service_id"])

    trips = leer("trips.txt")
    trips = trips[trips["route_id"].isin(nombre_ruta) & trips["service_id"].isin(servicios)]
    ruta_de_viaje = dict(zip(trips["trip_id"], trips["route_id"].map(nombre_ruta)))
    print("Viajes troncales de día hábil:", len(ruta_de_viaje))

    stops = leer("stops.txt")
    estacion_de_parada = dict(zip(stops["stop_id"], stops["stop_name"].map(nombre_estacion)))

    # stop_times pesa ~300 MB: se lee por bloques y se filtra.
    partes = []
    columnas = ["trip_id", "departure_time", "stop_id", "stop_sequence"]
    for bloque in pd.read_csv(z.open("stop_times.txt"), dtype=str, usecols=columnas,
                              chunksize=1_000_000):
        partes.append(bloque[bloque["trip_id"].isin(ruta_de_viaje)])
    st = pd.concat(partes, ignore_index=True)
    st["seq"] = st["stop_sequence"].astype(int)
    st["min"] = st["departure_time"].map(a_minutos)
    st["estacion"] = st["stop_id"].map(estacion_de_parada)
    st = st.dropna(subset=["estacion"]).sort_values(["trip_id", "seq"])

    # Patrón (secuencia de estaciones) de cada viaje.
    patrones = {}   # (ruta_base, tupla_estaciones) -> lista de [(estacion, minuto)] por viaje
    for trip_id, grupo in st.groupby("trip_id", sort=False):
        vistos, paradas = set(), []
        for est, minuto in zip(grupo["estacion"], grupo["min"]):
            if est in vistos:
                continue
            vistos.add(est)
            paradas.append((est, minuto))
        if len(paradas) < 2:
            continue
        clave = (ruta_de_viaje[trip_id], tuple(e for e, _ in paradas))
        patrones.setdefault(clave, []).append(paradas)

    # Nombrar patrones por ruta base.
    por_base = {}
    for (base, secuencia), viajes in patrones.items():
        por_base.setdefault(base, []).append((secuencia, viajes))

    filas_rutas, horarios = [], set()
    for base in sorted(por_base):
        variantes = sorted(por_base[base], key=lambda x: (-len(x[1]), x[0]))
        for i, (secuencia, viajes) in enumerate(variantes, 1):
            ruta = base if len(variantes) == 1 else "%s-%d" % (base, i)
            for orden, est in enumerate(secuencia, 1):
                filas_rutas.append((ruta, orden, est))
            for paradas in viajes:
                for est, minuto in paradas:
                    horarios.add((ruta, est, a_hhmm(minuto)))

    estaciones = sorted({est for _, _, est in filas_rutas})

    os.makedirs(salida, exist_ok=True)
    with open(os.path.join(salida, "estaciones.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["nombre"])
        for e in estaciones:
            w.writerow([e])
    with open(os.path.join(salida, "rutas.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ruta", "orden", "estacion"])
        w.writerows(filas_rutas)
    with open(os.path.join(salida, "horarios.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ruta", "estacion", "hora"])
        w.writerows(sorted(horarios))

    print("estaciones:", len(estaciones))
    print("rutas:", len({r for r, _, _ in filas_rutas}), "filas:", len(filas_rutas))
    print("horarios:", len(horarios))


if __name__ == "__main__":
    zip_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("gtfs", "GTFS-2021-07-14.zip")
    salida = sys.argv[2] if len(sys.argv) > 2 else "datos"
    convertir(zip_path, salida)
