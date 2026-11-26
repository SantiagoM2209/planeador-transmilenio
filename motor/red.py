"""
La red de TransMilenio: carga de los CSV y requisitos R1 a R9.

Contrato (lo que llama el script del profesor):
    Red(carpeta)
    red.estado(nombre)                       R1
    red.autocompletar(prefijo, k)            R2
    red.rango(desde, hasta)                  R3
    red.proximo_bus(estacion, ruta, hora)    R4
    red.viaje(origen, destino)               R5
    red.ranking(k)                           R6
    red.agregar_parada(ruta, nueva, despues_de)   R7
    red.quitar_parada(ruta, estacion)             R7
    red.recorrido(ruta, al_reves=False)           R7
    red.cerrar(nombre), red.reabrir(nombre)       R8
    red.deshacer(), red.rehacer()                 R9

Los valores de retorno exactos están documentados en cada método y en el
README (sección "Contrato y retornos").
"""
import csv

from .estructuras import (
    TablaHash,
    ListaDoble,
    NodoParada,
    Pila,
    merge_sort,
    esta_ordenado,
    primer_mayor_igual,
)

MINUTOS_DIA = 24 * 60

_CON_TILDE = "ÁÉÍÓÚÜÑÀÈÌÒÙÂÊÎÔÛÄËÏÖ"
_SIN_TILDE = "AEIOUUNAEIOUAEIOUAEIO"


def normalizar(texto):
    """Mayúsculas, sin tildes y sin espacios sobrantes (mismas reglas que los CSV)."""
    if texto is None:
        return ""
    texto = str(texto).strip().upper()
    salida = []
    for c in texto:
        pos = _CON_TILDE.find(c)
        salida.append(c if pos < 0 else _SIN_TILDE[pos])
    return " ".join("".join(salida).split())


def hora_a_minutos(hora):
    """'HH:MM' (o 'HH:MM:SS', o un entero de minutos) -> minutos desde 00:00.
    Horas >= 24 se llevan al reloj real (25:10 -> 01:10), igual que la
    conversión del GTFS. Devuelve None si el formato no es válido."""
    if isinstance(hora, int):
        return hora % MINUTOS_DIA
    partes = str(hora).strip().split(":")
    if len(partes) < 2:
        return None
    if not (partes[0].isdigit() and partes[1].isdigit()):
        return None
    minutos = int(partes[0]) * 60 + int(partes[1])
    return minutos % MINUTOS_DIA


def minutos_a_hora(minutos):
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def _archivo(carpeta, nombre):
    """carpeta + "/" + nombre (os no está permitido en el motor; "/" funciona
    también en Windows)."""
    carpeta = str(carpeta)
    if carpeta.endswith("/") or carpeta.endswith("\\"):
        return carpeta + nombre
    return carpeta + "/" + nombre


class Estacion:
    """nombre, abierta (bool), buses (buses al día que paran aquí) y rutas
    (tabla hash nombre_ruta -> True con las rutas que hoy pasan por aquí)."""

    __slots__ = ("nombre", "abierta", "buses", "rutas")

    def __init__(self, nombre):
        self.nombre = nombre
        self.abierta = True
        self.buses = 0
        self.rutas = TablaHash(4)


class Ruta:
    """Una ruta en un solo sentido: lista doblemente enlazada de paradas."""

    __slots__ = ("nombre", "paradas")

    def __init__(self, nombre):
        self.nombre = nombre
        self.paradas = ListaDoble()


def _leer_csv(ruta_archivo, columnas):
    """Lee un CSV y devuelve filas como listas en el orden de `columnas`.
    Se usa csv.reader (no DictReader, que crea dict)."""
    filas = []
    with open(ruta_archivo, newline="", encoding="utf-8-sig") as f:
        lector = csv.reader(f)
        encabezado = None
        for fila in lector:
            if encabezado is None:
                encabezado = [c.strip().lower() for c in fila]
                posiciones = []
                for col in columnas:
                    pos = -1
                    for i in range(len(encabezado)):
                        if encabezado[i] == col:
                            pos = i
                    if pos < 0:
                        raise ValueError("%s no tiene la columna %s" % (ruta_archivo, col))
                    posiciones.append(pos)
                continue
            if len(fila) < len(encabezado):
                continue
            filas.append([fila[p].strip() for p in posiciones])
    return filas


class Red:
    def __init__(self, carpeta):
        # R1/R8: nombre -> Estacion
        self._estaciones = TablaHash(256)
        # R7: nombre_ruta -> Ruta
        self._rutas = TablaHash(64)
        # R7: (ruta, estacion) -> NodoParada
        self._nodos = TablaHash(1024)
        # R4: (ruta, estacion) -> arreglo ordenado de minutos
        self._horarios = TablaHash(1024)
        # R2/R3: arreglo de Estacion ordenado por nombre
        self._ordenadas = []
        # R6: arreglo de estaciones abiertas ordenado por buses (desc)
        self._ranking = []
        self._sucio = True
        # R9
        self._deshacer = Pila()
        self._rehacer = Pila()

        self._cargar(carpeta)

    # ------------------------------------------------------------------ carga
    def _estacion_o_crear(self, nombre):
        est = self._estaciones.obtener(nombre)
        if est is None:
            est = Estacion(nombre)
            self._estaciones.poner(nombre, est)
        return est

    def _cargar(self, carpeta):
        for fila in _leer_csv(_archivo(carpeta, "estaciones.csv"), ["nombre"]):
            nombre = normalizar(fila[0])
            if nombre != "":
                self._estacion_o_crear(nombre)

        # Rutas: se agrupan las filas por ruta y se ordenan por "orden".
        filas_por_ruta = TablaHash(64)
        for ruta, orden, estacion in _leer_csv(_archivo(carpeta, "rutas.csv"),
                                               ["ruta", "orden", "estacion"]):
            ruta = ruta.strip()
            estacion = normalizar(estacion)
            if ruta == "" or estacion == "":
                continue
            grupo = filas_por_ruta.obtener(ruta)
            if grupo is None:
                grupo = []
                filas_por_ruta.poner(ruta, grupo)
            grupo.append((int(orden), estacion))

        for nombre_ruta, grupo in filas_por_ruta.pares():
            ruta = Ruta(nombre_ruta)
            self._rutas.poner(nombre_ruta, ruta)
            if not esta_ordenado(grupo):
                grupo = merge_sort(grupo)
            for _, estacion in grupo:
                if self._nodos.contiene((nombre_ruta, estacion)):
                    continue  # una ruta pasa una sola vez por cada estación
                self._estacion_o_crear(estacion)
                nodo = NodoParada(estacion)
                ruta.paradas.agregar_al_final(nodo)
                self._nodos.poner((nombre_ruta, estacion), nodo)
                self._estaciones.obtener(estacion).rutas.poner(nombre_ruta, True)

        # Horarios: (ruta, estacion) -> arreglo de minutos, luego se ordena.
        for ruta, estacion, hora in _leer_csv(_archivo(carpeta, "horarios.csv"),
                                              ["ruta", "estacion", "hora"]):
            minutos = hora_a_minutos(hora)
            if minutos is None:
                continue
            clave = (ruta.strip(), normalizar(estacion))
            arreglo = self._horarios.obtener(clave)
            if arreglo is None:
                arreglo = []
                self._horarios.poner(clave, arreglo)
            arreglo.append(minutos)

        for clave, arreglo in self._horarios.pares():
            if not esta_ordenado(arreglo):
                self._horarios.poner(clave, merge_sort(arreglo))
            if self._nodos.contiene(clave):
                self._estaciones.obtener(clave[1]).buses += len(arreglo)

        self._ordenadas = merge_sort(self._estaciones.valores(), lambda e: e.nombre)
        self._sucio = True

    # ------------------------------------------------------------------ R1
    def estado(self, nombre):
        """R1. Devuelve (existe, abierta):
            (False, False) si la estación no existe,
            (True, True)   si existe y está abierta,
            (True, False)  si existe y está cerrada.
        O(1) promedio (tabla hash)."""
        est = self._estaciones.obtener(normalizar(nombre))
        if est is None:
            return (False, False)
        return (True, est.abierta)

    # ------------------------------------------------------------------ R2
    def autocompletar(self, prefijo, k):
        """R2. Lista de hasta k nombres de estaciones ABIERTAS que empiezan por
        prefijo, en orden alfabético. k <= 0 -> []. O(log n + k)."""
        prefijo = normalizar(prefijo)
        salida = []
        if k <= 0:
            return salida
        i = primer_mayor_igual(self._ordenadas, prefijo, lambda e: e.nombre)
        n = len(self._ordenadas)
        while i < n and len(salida) < k:
            est = self._ordenadas[i]
            if not est.nombre.startswith(prefijo):
                break
            if est.abierta:
                salida.append(est.nombre)
            i += 1
        return salida

    # ------------------------------------------------------------------ R3
    def rango(self, desde, hasta):
        """R3. Lista alfabética de las estaciones ABIERTAS con
        desde <= nombre <= hasta (ambos extremos incluidos; no tienen que
        existir). Si desde > hasta -> []. O(log n + m), m = estaciones en el rango."""
        desde = normalizar(desde)
        hasta = normalizar(hasta)
        salida = []
        if desde > hasta:
            return salida
        i = primer_mayor_igual(self._ordenadas, desde, lambda e: e.nombre)
        n = len(self._ordenadas)
        while i < n and self._ordenadas[i].nombre <= hasta:
            if self._ordenadas[i].abierta:
                salida.append(self._ordenadas[i].nombre)
            i += 1
        return salida

    # ------------------------------------------------------------------ R4
    def proximo_bus(self, estacion, ruta, hora):
        """R4. Hora 'HH:MM' del primer bus de `ruta` que pasa por `estacion` a
        la hora dada o después (si pasa justo a esa hora, cuenta).
        Devuelve None si: la estación no existe o está cerrada, la ruta no
        existe o hoy no pasa por esa estación, la hora es inválida, o ya no
        hay más buses ese día. O(log h), h = buses de esa ruta en esa estación."""
        estacion = normalizar(estacion)
        ruta = str(ruta).strip()
        est = self._estaciones.obtener(estacion)
        if est is None or not est.abierta:
            return None
        if not self._nodos.contiene((ruta, estacion)):
            return None
        minutos = hora_a_minutos(hora)
        if minutos is None:
            return None
        arreglo = self._horarios.obtener((ruta, estacion))
        if arreglo is None:
            return None
        i = primer_mayor_igual(arreglo, minutos)
        if i == len(arreglo):
            return None
        return minutos_a_hora(arreglo[i])

    # ------------------------------------------------------------------ R5
    def viaje(self, origen, destino):
        """R5. Viaje directo o con UN transbordo que pase por menos paradas.

        Devuelve una lista de tramos (ruta, estacion_sube, estacion_baja):
            [(ruta, origen, destino)]                         directo
            [(ruta1, origen, cambio), (ruta2, cambio, destino)]  un transbordo
            []    si origen == destino
            None  si alguna no existe, está cerrada o no hay viaje posible.
        Ver viaje_con_paradas para obtener también el número de paradas."""
        resultado = self.viaje_con_paradas(origen, destino)
        if resultado is None:
            return None
        return resultado[1]

    def viaje_con_paradas(self, origen, destino):
        """Igual que viaje pero devuelve (paradas, tramos). `paradas` cuenta las
        estaciones abiertas donde el bus para después de subir (incluye la de
        bajada). Las estaciones cerradas no cuentan: el bus pasa sin parar.
        Empates: gana el directo; luego el orden alfabético de (ruta, cambio)."""
        origen = normalizar(origen)
        destino = normalizar(destino)
        eo = self._estaciones.obtener(origen)
        ed = self._estaciones.obtener(destino)
        if eo is None or ed is None or not eo.abierta or not ed.abierta:
            return None
        if origen == destino:
            return (0, [])

        mejor = None   # (paradas, transbordos, desempate, tramos)

        # Hacia adelante desde el origen: estación -> (paradas, ruta)
        desde_origen = TablaHash(64)
        for nombre_ruta in eo.rutas.claves():
            nodo = self._nodos.obtener((nombre_ruta, origen)).siguiente
            paradas = 0
            while nodo is not None:
                est = self._estaciones.obtener(nodo.estacion)
                if est.abierta:
                    paradas += 1
                    previo = desde_origen.obtener(nodo.estacion)
                    if previo is None or (paradas, nombre_ruta) < previo:
                        desde_origen.poner(nodo.estacion, (paradas, nombre_ruta))
                    if nodo.estacion == destino:
                        candidato = (paradas, 0, (nombre_ruta,), [(nombre_ruta, origen, destino)])
                        if mejor is None or candidato[:3] < mejor[:3]:
                            mejor = candidato
                        break
                nodo = nodo.siguiente

        # Hacia atrás desde el destino: estación -> (paradas hasta destino, ruta)
        hacia_destino = TablaHash(64)
        for nombre_ruta in ed.rutas.claves():
            nodo = self._nodos.obtener((nombre_ruta, destino))
            paradas = 1                     # bajar en el destino cuenta 1
            nodo = nodo.anterior
            while nodo is not None:
                est = self._estaciones.obtener(nodo.estacion)
                if est.abierta:
                    previo = hacia_destino.obtener(nodo.estacion)
                    if previo is None or (paradas, nombre_ruta) < previo:
                        hacia_destino.poner(nodo.estacion, (paradas, nombre_ruta))
                    paradas += 1
                nodo = nodo.anterior

        # Combinar en cada posible estación de transbordo.
        for cambio, (p1, r1) in desde_origen.pares():
            if cambio == destino:
                continue
            otro = hacia_destino.obtener(cambio)
            if otro is None:
                continue
            p2, r2 = otro
            if r1 == r2:
                continue  # misma ruta: eso ya es el viaje directo
            candidato = (p1 + p2, 1, (r1, cambio, r2),
                         [(r1, origen, cambio), (r2, cambio, destino)])
            if mejor is None or candidato[:3] < mejor[:3]:
                mejor = candidato

        if mejor is None:
            return None
        return (mejor[0], mejor[3])

    # ------------------------------------------------------------------ R6
    def ranking(self, k):
        """R6. Lista de hasta k pares (nombre, buses_al_dia) de estaciones
        ABIERTAS, de más buses a menos; empates en orden alfabético.
        k <= 0 -> []. O(k) si nada cambió; tras un cambio se reordena una vez
        con merge sort, O(n log n)."""
        if self._sucio:
            abiertas = []
            for est in self._ordenadas:
                if est.abierta:
                    abiertas.append(est)
            self._ranking = merge_sort(abiertas, lambda e: (-e.buses, e.nombre))
            self._sucio = False
        salida = []
        i = 0
        while i < k and i < len(self._ranking):
            est = self._ranking[i]
            salida.append((est.nombre, est.buses))
            i += 1
        return salida

    # ------------------------------------------------------------------ R7
    def agregar_parada(self, ruta, nueva, despues_de):
        """R7. Inserta la estación `nueva` en `ruta` justo después de
        `despues_de` (si despues_de es None o "", al inicio de la ruta).
        Devuelve True si se hizo; False si la ruta o la estación no existen,
        despues_de no está en la ruta, o `nueva` ya está en la ruta. O(1)."""
        ruta = str(ruta).strip()
        nueva = normalizar(nueva)
        if self._rutas.obtener(ruta) is None:
            return False
        if self._estaciones.obtener(nueva) is None:
            return False
        if self._nodos.contiene((ruta, nueva)):
            return False
        if despues_de is None or normalizar(despues_de) == "":
            despues_de = None
        else:
            despues_de = normalizar(despues_de)
            if not self._nodos.contiene((ruta, despues_de)):
                return False
        self._insertar(ruta, nueva, despues_de)
        self._registrar(("AGREGAR", ruta, nueva, despues_de))
        return True

    def quitar_parada(self, ruta, estacion):
        """R7. Quita `estacion` de `ruta`. True si se hizo; False si la ruta no
        existe o no pasa por esa estación. O(1)."""
        ruta = str(ruta).strip()
        estacion = normalizar(estacion)
        nodo = self._nodos.obtener((ruta, estacion))
        if nodo is None:
            return False
        anterior = None if nodo.anterior is None else nodo.anterior.estacion
        self._quitar(ruta, estacion)
        self._registrar(("QUITAR", ruta, estacion, anterior))
        return True

    def recorrido(self, ruta, al_reves=False):
        """R7. Lista de nombres de las paradas de la ruta en orden (o al revés).
        Incluye las estaciones cerradas (la ruta pasa por ahí aunque no pare).
        Ruta inexistente -> []. O(p), p = paradas de la ruta."""
        r = self._rutas.obtener(str(ruta).strip())
        if r is None:
            return []
        return r.paradas.a_lista(al_reves)

    def _insertar(self, ruta, estacion, despues_de):
        r = self._rutas.obtener(ruta)
        referencia = None if despues_de is None else self._nodos.obtener((ruta, despues_de))
        nodo = NodoParada(estacion)
        r.paradas.insertar_despues(referencia, nodo)
        self._nodos.poner((ruta, estacion), nodo)
        est = self._estaciones.obtener(estacion)
        est.rutas.poner(ruta, True)
        arreglo = self._horarios.obtener((ruta, estacion))
        if arreglo is not None:
            est.buses += len(arreglo)
        self._sucio = True

    def _quitar(self, ruta, estacion):
        r = self._rutas.obtener(ruta)
        nodo = self._nodos.obtener((ruta, estacion))
        r.paradas.quitar(nodo)
        self._nodos.eliminar((ruta, estacion))
        est = self._estaciones.obtener(estacion)
        est.rutas.eliminar(ruta)
        arreglo = self._horarios.obtener((ruta, estacion))
        if arreglo is not None:
            est.buses -= len(arreglo)
        self._sucio = True

    # ------------------------------------------------------------------ R8
    def cerrar(self, nombre):
        """R8. Cierra la estación. True si cambió; False si no existe o ya
        estaba cerrada (en ese caso no se registra para deshacer). O(1)."""
        est = self._estaciones.obtener(normalizar(nombre))
        if est is None or not est.abierta:
            return False
        self._poner_abierta(est.nombre, False)
        self._registrar(("CERRAR", est.nombre))
        return True

    def reabrir(self, nombre):
        """R8. Reabre la estación. True si cambió; False si no existe o ya
        estaba abierta. O(1)."""
        est = self._estaciones.obtener(normalizar(nombre))
        if est is None or est.abierta:
            return False
        self._poner_abierta(est.nombre, True)
        self._registrar(("REABRIR", est.nombre))
        return True

    def _poner_abierta(self, nombre, valor):
        self._estaciones.obtener(nombre).abierta = valor
        self._sucio = True  # el ranking solo muestra abiertas

    # ------------------------------------------------------------------ R9
    def _registrar(self, operacion):
        self._deshacer.apilar(operacion)
        self._rehacer.vaciar()  # un cambio nuevo borra lo que había para rehacer

    def _aplicar(self, op, inversa):
        tipo = op[0]
        if tipo == "CERRAR":
            self._poner_abierta(op[1], inversa)
        elif tipo == "REABRIR":
            self._poner_abierta(op[1], not inversa)
        elif tipo == "AGREGAR":
            if inversa:
                self._quitar(op[1], op[2])
            else:
                self._insertar(op[1], op[2], op[3])
        elif tipo == "QUITAR":
            if inversa:
                self._insertar(op[1], op[2], op[3])
            else:
                self._quitar(op[1], op[2])

    def deshacer(self):
        """R9. Deshace el último cambio (cierre, reapertura, agregar o quitar
        parada). True si deshizo algo; False si no había nada. O(1)."""
        op = self._deshacer.desapilar()
        if op is None:
            return False
        self._aplicar(op, True)
        self._rehacer.apilar(op)
        return True

    def rehacer(self):
        """R9. Rehace el último cambio deshecho. True/False. O(1)."""
        op = self._rehacer.desapilar()
        if op is None:
            return False
        self._aplicar(op, False)
        self._deshacer.apilar(op)
        return True

    # --------------------------------------------- ayudas para el front/panel
    def nombres_estaciones(self):
        """Todas las estaciones (abiertas y cerradas) en orden alfabético."""
        return [e.nombre for e in self._ordenadas]

    def nombres_rutas(self):
        return merge_sort(self._rutas.claves())

    def rutas_de(self, estacion):
        """Rutas que hoy pasan por la estación, en orden alfabético."""
        est = self._estaciones.obtener(normalizar(estacion))
        if est is None:
            return []
        return merge_sort(est.rutas.claves())

    def cerradas(self):
        return [e.nombre for e in self._ordenadas if not e.abierta]

    def historial(self):
        """(tamaño pila deshacer, tamaño pila rehacer, última operación)."""
        return (len(self._deshacer), len(self._rehacer), self._deshacer.tope())

    def tamano(self):
        """(estaciones, rutas, pares ruta-estación con horario)."""
        return (len(self._estaciones), len(self._rutas), len(self._horarios))
