"""
Estructuras de datos básicas, escritas desde cero con list usada como arreglo.

Reglas del motor: nada de dict, set, sorted, .sort(), min/max sobre
colecciones, "x in lista", .index(), .count(), bisect, heapq, collections ni
functools. Solo list, str, for, y los módulos csv, time y random.

Contenido:
    TablaHash        tabla hash con encadenamiento (cubetas = listas)
    merge_sort       ordenamiento estable O(n log n)
    primer_mayor_igual   búsqueda binaria (lower bound) O(log n)
    NodoParada / ListaDoble   lista doblemente enlazada
    Pila             LIFO sobre arreglo
    Cola             FIFO sobre arreglo con índice "frente"
"""


# ---------------------------------------------------------------------------
# Tabla hash con encadenamiento
# ---------------------------------------------------------------------------
class TablaHash:
    """Arreglo de cubetas; cada cubeta es una lista de pares [clave, valor].

    - hash(clave) % capacidad elige la cubeta.
    - Si el factor de carga (elementos / cubetas) pasa de 0.75 se duplica el
      arreglo y se reinsertan todos los pares (rehash). Como se duplica, el
      costo total del rehash se reparte: O(1) amortizado por inserción.
    - Búsqueda, inserción y borrado: O(1) promedio.
    """

    def __init__(self, capacidad=16):
        self._capacidad = capacidad
        self._cubetas = [[] for _ in range(capacidad)]
        self._tamano = 0

    def __len__(self):
        return self._tamano

    def _cubeta(self, clave):
        return self._cubetas[hash(clave) % self._capacidad]

    def poner(self, clave, valor):
        cubeta = self._cubeta(clave)
        for par in cubeta:
            if par[0] == clave:
                par[1] = valor
                return
        cubeta.append([clave, valor])
        self._tamano += 1
        if self._tamano * 4 > self._capacidad * 3:
            self._crecer()

    def obtener(self, clave, defecto=None):
        for par in self._cubeta(clave):
            if par[0] == clave:
                return par[1]
        return defecto

    def contiene(self, clave):
        for par in self._cubeta(clave):
            if par[0] == clave:
                return True
        return False

    def eliminar(self, clave):
        cubeta = self._cubeta(clave)
        for i in range(len(cubeta)):
            if cubeta[i][0] == clave:
                # Intercambia con el último y saca el último: O(1).
                cubeta[i] = cubeta[len(cubeta) - 1]
                cubeta.pop()
                self._tamano -= 1
                return True
        return False

    def _crecer(self):
        viejas = self._cubetas
        self._capacidad *= 2
        self._cubetas = [[] for _ in range(self._capacidad)]
        for cubeta in viejas:
            for par in cubeta:
                self._cubetas[hash(par[0]) % self._capacidad].append(par)

    def claves(self):
        salida = []
        for cubeta in self._cubetas:
            for par in cubeta:
                salida.append(par[0])
        return salida

    def valores(self):
        salida = []
        for cubeta in self._cubetas:
            for par in cubeta:
                salida.append(par[1])
        return salida

    def pares(self):
        salida = []
        for cubeta in self._cubetas:
            for par in cubeta:
                salida.append((par[0], par[1]))
        return salida


# ---------------------------------------------------------------------------
# Merge sort (estable) y búsqueda binaria
# ---------------------------------------------------------------------------
def merge_sort(arreglo, clave=None):
    """Devuelve un arreglo NUEVO ordenado de menor a mayor según clave(x).

    Divide a la mitad, ordena cada mitad y mezcla: O(n log n) siempre, y es
    estable (empates conservan el orden original). Se ordenan pares
    (clave, posición) para no comparar nunca los objetos en sí.
    """
    n = len(arreglo)
    if clave is None:
        pares = [(arreglo[i], i) for i in range(n)]
    else:
        pares = [(clave(arreglo[i]), i) for i in range(n)]
    pares = _merge_sort_pares(pares)
    return [arreglo[par[1]] for par in pares]


def _merge_sort_pares(a):
    n = len(a)
    if n <= 1:
        return a
    mitad = n // 2
    izq = _merge_sort_pares(a[:mitad])
    der = _merge_sort_pares(a[mitad:])
    return _mezclar(izq, der)


def _mezclar(izq, der):
    salida = []
    i = 0
    j = 0
    ni = len(izq)
    nd = len(der)
    while i < ni and j < nd:
        if izq[i] <= der[j]:
            salida.append(izq[i])
            i += 1
        else:
            salida.append(der[j])
            j += 1
    while i < ni:
        salida.append(izq[i])
        i += 1
    while j < nd:
        salida.append(der[j])
        j += 1
    return salida


def esta_ordenado(arreglo):
    """O(n). Sirve para no ordenar lo que ya viene ordenado."""
    for i in range(1, len(arreglo)):
        if arreglo[i - 1] > arreglo[i]:
            return False
    return True


def primer_mayor_igual(arreglo, objetivo, clave=None):
    """Búsqueda binaria: primer índice i con clave(arreglo[i]) >= objetivo.

    Si todos son menores devuelve len(arreglo). O(log n).
    """
    bajo = 0
    alto = len(arreglo)
    while bajo < alto:
        medio = (bajo + alto) // 2
        valor = arreglo[medio] if clave is None else clave(arreglo[medio])
        if valor < objetivo:
            bajo = medio + 1
        else:
            alto = medio
    return bajo


# ---------------------------------------------------------------------------
# Lista doblemente enlazada
# ---------------------------------------------------------------------------
class NodoParada:
    __slots__ = ("estacion", "anterior", "siguiente")

    def __init__(self, estacion):
        self.estacion = estacion      # nombre de la estación (str)
        self.anterior = None
        self.siguiente = None


class ListaDoble:
    """Cabeza, cola y tamaño. Insertar después de un nodo conocido y quitar un
    nodo conocido son O(1): solo se cambian punteros."""

    def __init__(self):
        self.cabeza = None
        self.cola = None
        self.tamano = 0

    def agregar_al_final(self, nodo):
        nodo.anterior = self.cola
        nodo.siguiente = None
        if self.cola is None:
            self.cabeza = nodo
        else:
            self.cola.siguiente = nodo
        self.cola = nodo
        self.tamano += 1

    def insertar_despues(self, referencia, nodo):
        """Inserta nodo después de referencia. Si referencia es None, al inicio."""
        if referencia is None:
            nodo.anterior = None
            nodo.siguiente = self.cabeza
            if self.cabeza is None:
                self.cola = nodo
            else:
                self.cabeza.anterior = nodo
            self.cabeza = nodo
        else:
            nodo.anterior = referencia
            nodo.siguiente = referencia.siguiente
            if referencia.siguiente is None:
                self.cola = nodo
            else:
                referencia.siguiente.anterior = nodo
            referencia.siguiente = nodo
        self.tamano += 1

    def quitar(self, nodo):
        if nodo.anterior is None:
            self.cabeza = nodo.siguiente
        else:
            nodo.anterior.siguiente = nodo.siguiente
        if nodo.siguiente is None:
            self.cola = nodo.anterior
        else:
            nodo.siguiente.anterior = nodo.anterior
        nodo.anterior = None
        nodo.siguiente = None
        self.tamano -= 1

    def a_lista(self, al_reves=False):
        salida = []
        nodo = self.cola if al_reves else self.cabeza
        while nodo is not None:
            salida.append(nodo.estacion)
            nodo = nodo.anterior if al_reves else nodo.siguiente
        return salida


# ---------------------------------------------------------------------------
# Pila y Cola
# ---------------------------------------------------------------------------
class Pila:
    """LIFO. append y pop sobre el FINAL del arreglo: O(1) amortizado."""

    def __init__(self):
        self._datos = []

    def apilar(self, x):
        self._datos.append(x)

    def desapilar(self):
        if len(self._datos) == 0:
            return None
        return self._datos.pop()

    def tope(self):
        if len(self._datos) == 0:
            return None
        return self._datos[len(self._datos) - 1]

    def vacia(self):
        return len(self._datos) == 0

    def vaciar(self):
        self._datos = []

    def __len__(self):
        return len(self._datos)


class Cola:
    """FIFO sobre un arreglo con un índice "frente".

    encolar = append al final (O(1) amortizado). desencolar = leer
    datos[frente] y avanzar frente (O(1)); nunca se hace pop(0), que movería
    todos los elementos (O(n)). Cuando la parte ya atendida ocupa más de la
    mitad del arreglo se compacta: cada elemento se copia a lo sumo una vez
    por cada vez que se atendió, así que sigue siendo O(1) amortizado.
    """

    def __init__(self):
        self._datos = []
        self._frente = 0

    def encolar(self, x):
        self._datos.append(x)

    def desencolar(self):
        if self._frente >= len(self._datos):
            return None
        x = self._datos[self._frente]
        self._frente += 1
        if self._frente > 1024 and self._frente * 2 > len(self._datos):
            self._datos = self._datos[self._frente:]
            self._frente = 0
        return x

    def vacia(self):
        return self._frente >= len(self._datos)

    def __len__(self):
        return len(self._datos) - self._frente
