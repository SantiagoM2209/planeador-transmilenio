"""
Verificación del motor:

  1. AUDITORÍA (módulo ast): recorre todos los .py de motor/ y falla si
     encuentra algo prohibido por las reglas del proyecto.
  2. PRUEBAS UNITARIAS de R1 a R10 con una red pequeña hecha a mano
     (casos borde incluidos) y con la red real de datos/.
  3. PRUEBA DE DUPLICACIÓN n -> 2n: mide cada operación (menos R5) en la red
     real y en la red duplicada y exige que crezca como se espera.

Uso:
    python tests/verificar_motor.py            # todo
    python tests/verificar_motor.py auditoria  # solo la auditoría
"""
import ast
import os
import random
import shutil
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from motor import Red, simular_fila  # noqa: E402

CARPETA_MOTOR = os.path.join(RAIZ, "motor")
CARPETA_DATOS = os.path.join(RAIZ, "datos")

# ---------------------------------------------------------------------------
# 1. Auditoría con ast
# ---------------------------------------------------------------------------
MODULOS_PERMITIDOS = ("csv", "time", "random")
NOMBRES_PROHIBIDOS = ("dict", "set", "frozenset", "sorted", "min", "max",
                      "bisect", "heapq", "collections", "functools",
                      "vars", "globals", "locals")
METODOS_PROHIBIDOS = ("sort", "index", "count")


def auditar_archivo(ruta):
    """Devuelve una lista de textos 'archivo:línea: problema'."""
    with open(ruta, encoding="utf-8") as f:
        arbol = ast.parse(f.read(), filename=ruta)
    nombre = os.path.relpath(ruta, RAIZ)
    problemas = []

    def reportar(nodo, texto):
        problemas.append("%s:%d: %s" % (nombre, nodo.lineno, texto))

    for nodo in ast.walk(arbol):
        # Importaciones: solo csv, time, random y módulos del propio motor.
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                raiz = alias.name.split(".")[0]
                if raiz not in MODULOS_PERMITIDOS and raiz != "motor":
                    reportar(nodo, "import prohibido: %s" % alias.name)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level == 0:
                raiz = (nodo.module or "").split(".")[0]
                if raiz not in MODULOS_PERMITIDOS and raiz != "motor":
                    reportar(nodo, "import prohibido: %s" % nodo.module)
        # Literales y comprensiones de dict / set.
        elif isinstance(nodo, (ast.Dict, ast.DictComp)):
            reportar(nodo, "dict literal o comprensión de dict")
        elif isinstance(nodo, (ast.Set, ast.SetComp)):
            reportar(nodo, "set literal o comprensión de set")
        # dict, set, sorted, min, max... usados en cualquier lugar.
        elif isinstance(nodo, ast.Name) and nodo.id in NOMBRES_PROHIBIDOS:
            reportar(nodo, "uso prohibido de %s" % nodo.id)
        # x.sort(), x.index(...), x.count(...) y __dict__.
        elif isinstance(nodo, ast.Attribute):
            if nodo.attr in METODOS_PROHIBIDOS:
                reportar(nodo, "método prohibido .%s()" % nodo.attr)
            if nodo.attr == "__dict__":
                reportar(nodo, "uso de __dict__")
        # Operador "in" / "not in" para buscar (no confundir con for x in lista).
        elif isinstance(nodo, ast.Compare):
            for op in nodo.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    reportar(nodo, "operador 'in' para buscar")
        # **kwargs crea un dict.
        elif isinstance(nodo, ast.arguments) and nodo.kwarg is not None:
            reportar(nodo.kwarg, "**%s crea un dict" % nodo.kwarg.arg)
        elif isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if kw.arg is None:
                    reportar(nodo, "llamada con **dict")
    return problemas


def auditar_motor():
    problemas = []
    for carpeta, _, archivos in os.walk(CARPETA_MOTOR):
        for archivo in archivos:
            if archivo.endswith(".py"):
                problemas.extend(auditar_archivo(os.path.join(carpeta, archivo)))
    return problemas


class Auditoria(unittest.TestCase):
    def test_motor_sin_nada_prohibido(self):
        problemas = auditar_motor()
        self.assertEqual(problemas, [], "\n" + "\n".join(problemas))

    def test_el_auditor_detecta_trampas(self):
        codigo = (
            "import heapq\nfrom collections import deque\n"
            "a = {}\nb = {1, 2}\nc = sorted([3, 1])\nd = max([1, 2])\n"
            "x = [1]\nx.sort()\ny = x.index(1)\nz = 1 in x\n"
            "def f(**kw):\n    return dict(kw)\n"
        )
        ruta = os.path.join(tempfile.mkdtemp(), "trampa.py")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(codigo)
        problemas = " ".join(auditar_archivo(ruta))
        for esperado in ("heapq", "collections", "dict literal", "set literal",
                         "sorted", "max", ".sort", ".index", "'in'", "**kw"):
            self.assertIn(esperado, problemas)


# ---------------------------------------------------------------------------
# 2. Pruebas unitarias con una red hecha a mano
# ---------------------------------------------------------------------------
#  R1: A -> B -> C -> D
#  R2: CALLE 26 -> C -> E -> F
#  R3: A -> F
ESTACIONES = ["A", "B", "C", "D", "E", "F", "CALLE 26", "CALLE 45", "CALLE 80",
              "CALLE 100", "AGUAS"]
RUTAS = [("R1", 1, "A"), ("R1", 2, "B"), ("R1", 4, "D"), ("R1", 3, "C"),   # desordenado a propósito
         ("R2", 1, "CALLE 26"), ("R2", 2, "C"), ("R2", 3, "E"), ("R2", 4, "F"),
         ("R3", 1, "A"), ("R3", 2, "F")]
HORARIOS = [("R1", "A", "06:30"), ("R1", "A", "06:00"), ("R1", "A", "25:10"),
            ("R1", "B", "06:05"), ("R1", "C", "06:10"), ("R1", "D", "06:15"),
            ("R2", "C", "07:00"), ("R2", "C", "07:10"), ("R2", "C", "07:20"),
            ("R2", "E", "07:05"), ("R3", "A", "08:00"), ("R3", "F", "08:20")]


def escribir_red(carpeta, estaciones, rutas, horarios):
    os.makedirs(carpeta, exist_ok=True)
    with open(os.path.join(carpeta, "estaciones.csv"), "w", encoding="utf-8") as f:
        f.write("nombre\n" + "".join(e + "\n" for e in estaciones))
    with open(os.path.join(carpeta, "rutas.csv"), "w", encoding="utf-8") as f:
        f.write("ruta,orden,estacion\n" + "".join("%s,%d,%s\n" % r for r in rutas))
    with open(os.path.join(carpeta, "horarios.csv"), "w", encoding="utf-8") as f:
        f.write("ruta,estacion,hora\n" + "".join("%s,%s,%s\n" % h for h in horarios))


class RedPequena(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        escribir_red(self.dir, ESTACIONES, RUTAS, HORARIOS)
        self.red = Red(self.dir)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    # R1
    def test_r1_estado(self):
        r = self.red
        self.assertEqual(r.estado("A"), (True, True))
        self.assertEqual(r.estado("NO EXISTE"), (False, False))
        self.assertEqual(r.estado("  águas "), (True, True))   # mayúsculas/tildes
        r.cerrar("A")
        self.assertEqual(r.estado("A"), (True, False))

    # R2
    def test_r2_autocompletar(self):
        r = self.red
        self.assertEqual(r.autocompletar("CAL", 10), ["CALLE 100", "CALLE 26", "CALLE 45", "CALLE 80"])
        self.assertEqual(r.autocompletar("cal", 2), ["CALLE 100", "CALLE 26"])
        self.assertEqual(r.autocompletar("CAL", 0), [])
        self.assertEqual(r.autocompletar("ZZZ", 5), [])
        r.cerrar("CALLE 100")
        self.assertEqual(r.autocompletar("CAL", 2), ["CALLE 26", "CALLE 45"])
        self.assertEqual(r.autocompletar("", 3), ["A", "AGUAS", "B"])

    # R3
    def test_r3_rango(self):
        r = self.red
        self.assertEqual(r.rango("CALLE 26", "CALLE 80"), ["CALLE 26", "CALLE 45", "CALLE 80"])
        self.assertEqual(r.rango("CALLE 27", "CALLE 79"), ["CALLE 45"])   # extremos que no existen
        self.assertEqual(r.rango("CALLE 80", "CALLE 26"), [])
        r.cerrar("CALLE 45")
        self.assertEqual(r.rango("CALLE 26", "CALLE 80"), ["CALLE 26", "CALLE 80"])

    # R4
    def test_r4_proximo_bus(self):
        r = self.red
        self.assertEqual(r.proximo_bus("A", "R1", "06:00"), "06:00")   # justo a la hora cuenta
        self.assertEqual(r.proximo_bus("A", "R1", "06:01"), "06:30")
        self.assertEqual(r.proximo_bus("A", "R1", "00:00"), "01:10")   # 25:10 -> 01:10
        self.assertIsNone(r.proximo_bus("A", "R1", "06:31"))           # no hay más buses
        self.assertIsNone(r.proximo_bus("E", "R1", "06:00"))           # la ruta no pasa
        self.assertIsNone(r.proximo_bus("A", "R9", "06:00"))           # ruta no existe
        self.assertIsNone(r.proximo_bus("A", "R1", "hola"))            # hora inválida
        r.cerrar("A")
        self.assertIsNone(r.proximo_bus("A", "R1", "06:00"))           # cerrada

    # R5
    def test_r5_viaje(self):
        r = self.red
        self.assertEqual(r.viaje("A", "D"), [("R1", "A", "D")])
        self.assertEqual(r.viaje_con_paradas("A", "D")[0], 3)
        self.assertEqual(r.viaje("A", "E"), [("R1", "A", "C"), ("R2", "C", "E")])
        self.assertEqual(r.viaje("A", "F"), [("R3", "A", "F")])         # directo de 1 parada gana
        self.assertIsNone(r.viaje("D", "A"))                           # rutas en un solo sentido
        self.assertEqual(r.viaje("A", "A"), [])
        self.assertIsNone(r.viaje("A", "NO EXISTE"))
        r.cerrar("C")
        self.assertIsNone(r.viaje("A", "E"))                           # no se transborda en cerrada
        self.assertEqual(r.viaje_con_paradas("A", "D"), (2, [("R1", "A", "D")]))
        self.assertIsNone(r.viaje("A", "C"))

    def test_r5_necesita_dos_transbordos(self):
        # B -> CALLE 26 no tiene camino ni con un transbordo.
        self.assertIsNone(self.red.viaje("B", "CALLE 26"))

    # R6
    def test_r6_ranking(self):
        r = self.red
        self.assertEqual(r.ranking(3), [("A", 4), ("C", 4), ("B", 1)])  # empate en 1: alfabético
        r.cerrar("A")
        self.assertEqual(r.ranking(2), [("C", 4), ("B", 1)])
        r.deshacer()
        self.assertEqual(r.ranking(1), [("A", 4)])
        self.assertEqual(r.ranking(0), [])
        self.assertEqual(len(r.ranking(100)), len(ESTACIONES))
        r.quitar_parada("R2", "C")                                     # C pierde 3 buses
        self.assertEqual(r.ranking(2), [("A", 4), ("B", 1)])

    # R7
    def test_r7_editar_rutas(self):
        r = self.red
        self.assertEqual(r.recorrido("R1"), ["A", "B", "C", "D"])
        self.assertEqual(r.recorrido("R1", al_reves=True), ["D", "C", "B", "A"])
        self.assertTrue(r.agregar_parada("R1", "E", "B"))
        self.assertEqual(r.recorrido("R1"), ["A", "B", "E", "C", "D"])
        self.assertTrue(r.agregar_parada("R1", "F", "D"))              # al final
        self.assertTrue(r.agregar_parada("R1", "AGUAS", None))         # al inicio
        self.assertEqual(r.recorrido("R1"), ["AGUAS", "A", "B", "E", "C", "D", "F"])
        self.assertEqual(r.recorrido("R1", True), ["F", "D", "C", "E", "B", "A", "AGUAS"])
        self.assertFalse(r.agregar_parada("R1", "E", "A"))             # ya está
        self.assertFalse(r.agregar_parada("R1", "NO EXISTE", "A"))
        self.assertFalse(r.agregar_parada("R1", "CALLE 45", "CALLE 80"))   # despues_de no está
        self.assertFalse(r.agregar_parada("R9", "E", "A"))
        self.assertTrue(r.quitar_parada("R1", "A"))
        self.assertFalse(r.quitar_parada("R1", "A"))
        self.assertTrue(r.quitar_parada("R1", "AGUAS"))                # cabeza
        self.assertTrue(r.quitar_parada("R1", "F"))                    # cola
        self.assertEqual(r.recorrido("R1"), ["B", "E", "C", "D"])
        self.assertEqual(r.recorrido("R9"), [])
        self.assertIsNone(r.proximo_bus("A", "R1", "06:00"))          # ya no pasa
        self.assertEqual(r.viaje("B", "E"), [("R1", "B", "E")])        # el viaje usa la ruta editada

    # R8
    def test_r8_cerrar_reabrir(self):
        r = self.red
        self.assertTrue(r.cerrar("B"))
        self.assertFalse(r.cerrar("B"))
        self.assertFalse(r.cerrar("NO EXISTE"))
        self.assertEqual(r.autocompletar("B", 5), [])
        self.assertTrue(r.reabrir("B"))
        self.assertFalse(r.reabrir("B"))
        self.assertEqual(r.autocompletar("B", 5), ["B"])

    # R9
    def test_r9_deshacer_rehacer(self):
        r = self.red
        self.assertFalse(r.deshacer())
        self.assertFalse(r.rehacer())
        r.cerrar("A")
        r.quitar_parada("R1", "B")
        r.agregar_parada("R1", "E", "C")
        self.assertEqual(r.recorrido("R1"), ["A", "C", "E", "D"])
        self.assertTrue(r.deshacer())                                  # quita E
        self.assertEqual(r.recorrido("R1"), ["A", "C", "D"])
        self.assertTrue(r.deshacer())                                  # vuelve B en su sitio
        self.assertEqual(r.recorrido("R1"), ["A", "B", "C", "D"])
        self.assertTrue(r.deshacer())                                  # reabre A
        self.assertEqual(r.estado("A"), (True, True))
        self.assertFalse(r.deshacer())
        self.assertTrue(r.rehacer())                                   # cierra A
        self.assertEqual(r.estado("A"), (True, False))
        self.assertTrue(r.rehacer())                                   # quita B
        self.assertEqual(r.recorrido("R1"), ["A", "C", "D"])
        r.reabrir("A")                                                 # cambio nuevo
        self.assertFalse(r.rehacer())                                  # borró lo de rehacer
        self.assertTrue(r.deshacer())
        self.assertEqual(r.estado("A"), (True, False))

    def test_r9_no_registra_cambios_fallidos(self):
        r = self.red
        r.cerrar("A")
        r.cerrar("A")              # no cambió nada
        r.quitar_parada("R1", "Z")
        self.assertTrue(r.deshacer())
        self.assertFalse(r.deshacer())


class Fila(unittest.TestCase):
    def test_r10_basico(self):
        self.assertEqual(simular_fila([0, 1, 1, 2, 3, 10], 5, 2), [0, 5, 5, 10, 10, 15])

    def test_r10_bordes(self):
        self.assertEqual(simular_fila([], 5, 2), [])
        self.assertIsNone(simular_fila([1, 2], 0, 2))
        self.assertIsNone(simular_fila([1, 2], 5, 0))
        self.assertEqual(simular_fila([5], 5, 1), [5])                 # llega justo: sube
        self.assertEqual(simular_fila([1000], 5, 1), [1000])           # salta buses vacíos
        self.assertEqual(simular_fila([3, 0, 1], 2, 1), [4, 0, 2])     # llegadas desordenadas
        self.assertEqual(simular_fila([0, 0, 0], 1, 1), [0, 1, 2])     # empates: orden de entrada

    def test_r10_cientos_de_miles(self):
        rnd = random.Random(1)
        llegadas = [rnd.uniform(0, 3600) for _ in range(300_000)]
        llegadas.sort()
        salidas = simular_fila(llegadas, 2, 150)
        self.assertEqual(len(salidas), 300_000)
        for i in range(0, 300_000, 997):
            self.assertGreaterEqual(salidas[i], llegadas[i])
        for i in range(1, 300_000):
            self.assertGreaterEqual(salidas[i], salidas[i - 1])        # FIFO


class RedReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.red = Red(CARPETA_DATOS)

    def test_carga(self):
        est, rutas, pares = self.red.tamano()
        self.assertGreater(est, 100)
        self.assertGreater(rutas, 100)

    def test_consultas(self):
        r = self.red
        self.assertEqual(r.estado("RICAURTE"), (True, True))
        auto = r.autocompletar("CALLE", 5)
        self.assertEqual(len(auto), 5)
        for i in range(1, len(auto)):
            self.assertLess(auto[i - 1], auto[i])
        self.assertIsNotNone(r.viaje("PORTAL NORTE", "PORTAL SUR"))
        top = r.ranking(5)
        for i in range(1, len(top)):
            self.assertGreaterEqual(top[i - 1][1], top[i][1])


# ---------------------------------------------------------------------------
# 3. Duplicación n -> 2n
# ---------------------------------------------------------------------------
class Duplicacion(unittest.TestCase):
    """Corre cada operación en la red real (n) y en la duplicada (2n).
    Límites de la razón t(2n)/t(n): O(1) y O(log n) deberían dar ~1, O(n) ~2.
    Se deja margen por ruido: < 1.6 para sublineales y < 2.8 para lineales.
    Cada medida se repite 3 veces y se toma la menor (la menos ruidosa)."""

    @classmethod
    def setUpClass(cls):
        import rendimiento
        cls.rend = rendimiento
        cls.redes = [Red(rendimiento.crear_red_escalada(f)) for f in (1, 2)]

    def medir(self, preparar, funcion):
        tiempos = []
        for red in self.redes:
            argumentos = preparar(red, random.Random(3))
            tiempos.append(min_de(lambda: self.rend.cronometrar(funcion(red), argumentos), 3))
        return tiempos[1] / tiempos[0]

    def test_sublineales(self):
        casos = [
            ("R1", lambda red, rnd: [(e,) for e in muestra(red.nombres_estaciones(), rnd)],
             lambda red: red.estado),
            ("R2", lambda red, rnd: [(e[:3], 10) for e in muestra(red.nombres_estaciones(), rnd)],
             lambda red: red.autocompletar),
            ("R3", lambda red, rnd: rangos(red, rnd), lambda red: red.rango),
            ("R4", lambda red, rnd: buses(red, rnd), lambda red: red.proximo_bus),
            ("R6", lambda red, rnd: [(10,)] * 2000, lambda red: red.ranking),
            ("R7", lambda red, rnd: [(r,) for r in muestra(red.nombres_rutas(), rnd)],
             lambda red: red.recorrido),
            ("R8", lambda red, rnd: [(e,) for e in muestra(red.nombres_estaciones(), rnd)],
             lambda red: (lambda e: (red.cerrar(e), red.reabrir(e)))),
            ("R9", lambda red, rnd: preparar_pilas(red),
             lambda red: (lambda: (red.deshacer(), red.rehacer()))),
        ]
        fallos = []
        for nombre, preparar, funcion in casos:
            razon = self.medir(preparar, funcion)
            print("  %-3s t(2n)/t(n) = %.2f" % (nombre, razon))
            if razon > 1.6:
                fallos.append("%s creció %.2f veces" % (nombre, razon))
        self.assertEqual(fallos, [])

    def test_r10_lineal(self):
        rnd = random.Random(5)
        tiempos = []
        for n in (100_000, 200_000):
            llegadas = [rnd.uniform(0, 3600) for _ in range(n)]
            llegadas.sort()
            tiempos.append(min_de(lambda: self.rend.cronometrar(
                simular_fila, [(llegadas, 3, 100)], lotes=1), 3))
        razon = tiempos[1] / tiempos[0]
        print("  R10 t(2n)/t(n) = %.2f" % razon)
        self.assertLess(razon, 2.8)


def min_de(funcion, veces):
    mejor = None
    for _ in range(veces):
        t = funcion()
        if mejor is None or t < mejor:
            mejor = t
    return mejor


def muestra(arreglo, rnd, cantidad=2000):
    return [arreglo[rnd.randrange(len(arreglo))] for _ in range(cantidad)]


def rangos(red, rnd):
    nombres = red.nombres_estaciones()
    salida = []
    for _ in range(2000):
        i = rnd.randrange(len(nombres) - 10)
        salida.append((nombres[i], nombres[i + 9]))
    return salida


def buses(red, rnd):
    salida = []
    rutas = red.nombres_rutas()
    for _ in range(2000):
        ruta = rutas[rnd.randrange(len(rutas))]
        rec = red.recorrido(ruta)
        salida.append((rec[rnd.randrange(len(rec))], ruta, "%02d:%02d" % (rnd.randrange(24), rnd.randrange(60))))
    return salida


def preparar_pilas(red):
    red.cerrar(red.nombres_estaciones()[0])
    return [()] * 2000


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auditoria":
        problemas = auditar_motor()
        print("\n".join(problemas) if problemas else "Auditoría OK: motor/ no usa nada prohibido.")
        sys.exit(1 if problemas else 0)
    unittest.main(verbosity=2)
