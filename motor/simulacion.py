"""
R10 · Fila de abordaje en hora pico.

simular_fila(llegadas, frecuencia, capacidad)

    llegadas    arreglo con la hora de llegada de cada pasajero (números en la
                misma unidad que frecuencia, p. ej. minutos o segundos desde el
                inicio de la simulación).
    frecuencia  cada cuánto sale un bus. Los buses salen en 0, f, 2f, 3f, ...
    capacidad   cupo de cada bus.

Reglas:
    * La gente sube en orden de llegada (FIFO).
    * Un pasajero que llega exactamente cuando sale un bus alcanza a subir.
    * Si un bus se llena, los demás esperan el siguiente.

Devuelve un arreglo `salidas` del mismo tamaño que `llegadas`:
salidas[i] = hora a la que sale el bus en el que se va el pasajero i (en el
mismo orden de entrada). La espera del pasajero i es salidas[i] - llegadas[i].
Devuelve None si frecuencia <= 0 o capacidad <= 0 (nadie se iría nunca).
llegadas vacío -> [].

Complejidad: O(n + b), n = pasajeros, b = buses que salen con alguien.
Cada pasajero entra y sale de la cola una sola vez (O(1) cada operación, sin
pop(0)). Los buses vacíos no se simulan uno por uno: si la fila está vacía se
salta directo al primer bus después de la siguiente llegada. Si las llegadas
no vienen en orden, se ordenan antes con merge sort: O(n log n).
"""
from .estructuras import Cola, merge_sort, esta_ordenado


def simular_fila(llegadas, frecuencia, capacidad):
    if frecuencia is None or capacidad is None or frecuencia <= 0 or capacidad <= 0:
        return None
    n = len(llegadas)
    salidas = [0] * n
    if n == 0:
        return salidas

    # Índices de pasajeros en orden de llegada (estable ante empates).
    if esta_ordenado(llegadas):
        orden = range(n)
    else:
        orden = merge_sort(list(range(n)), lambda i: llegadas[i])

    fila = Cola()
    siguiente = 0          # posición en `orden` del próximo pasajero por llegar
    atendidos = 0
    bus = 0                # hora de salida del bus actual

    while atendidos < n:
        if fila.vacia():
            # Saltar al primer bus que sale en o después de la próxima llegada.
            llegada = llegadas[orden[siguiente]]
            if bus < llegada:
                bus = (llegada // frecuencia) * frecuencia
                if bus < llegada:
                    bus += frecuencia
        # Todos los que llegaron hasta la salida de este bus hacen fila.
        while siguiente < n and llegadas[orden[siguiente]] <= bus:
            fila.encolar(orden[siguiente])
            siguiente += 1
        # Suben hasta `capacidad`, en orden de llegada.
        cupo = capacidad
        while cupo > 0 and not fila.vacia():
            pasajero = fila.desencolar()
            salidas[pasajero] = bus
            atendidos += 1
            cupo -= 1
        bus += frecuencia

    return salidas


def resumen_fila(llegadas, salidas):
    """(espera_promedio, espera_maxima, buses_usados) a partir del resultado de
    simular_fila. O(n). Los buses usados se cuentan como cambios de hora de
    salida en orden de llegada."""
    n = len(llegadas)
    if salidas is None or n == 0:
        return (0, 0, 0)
    total = 0
    maxima = salidas[0] - llegadas[0]
    for i in range(n):
        espera = salidas[i] - llegadas[i]
        total += espera
        if espera > maxima:
            maxima = espera
    # Cada bus tiene una hora distinta; recorrer las salidas ordenadas.
    ordenadas = salidas if esta_ordenado(salidas) else merge_sort(salidas)
    buses = 1
    for i in range(1, n):
        if ordenadas[i] != ordenadas[i - 1]:
            buses += 1
    return (total / n, maxima, buses)
