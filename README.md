# Planeador de viajes TransMilenio

App web para buscar estaciones, planear viajes y saber a qué hora pasa el bus, sobre la red troncal real de TransMilenio (GTFS de julio de 2021). Toda la lógica vive en el paquete `motor/`, escrito con estructuras de datos básicas hechas a mano.

## Arrancar la app (comando único)

```powershell
python app.py
```

Abre `http://localhost:8000` en el navegador. Solo usa la librería estándar de Python 3.10 o superior, así que no hay que instalar nada. Con `PUERTO=9000` se cambia el puerto y con `--sin-navegador` no se abre el navegador.

Otros comandos:

| Qué | Comando |
|---|---|
| Pruebas + auditoría de reglas + prueba n → 2n | `python tests/verificar_motor.py` |
| Solo la auditoría de cosas prohibidas en `motor/` | `python tests/verificar_motor.py auditoria` |
| Benchmarks por consola (los mismos del panel R11) | `python rendimiento.py` |
| Regenerar los CSV desde el GTFS (necesita `pandas`) | `python convertir_gtfs.py gtfs/GTFS-2021-07-14.zip datos` |

## Estructura del repositorio

```
motor/                 ← el motor (reglas estrictas: solo list, str, csv, time, random)
  __init__.py          from motor import Red, simular_fila
  estructuras.py       TablaHash, merge_sort, búsqueda binaria, ListaDoble, Pila, Cola
  red.py               Red: carga de CSV y requisitos R1 a R9
  simulacion.py        simular_fila (R10)
datos/                 estaciones.csv, rutas.csv, horarios.csv (generados)
convertir_gtfs.py      GTFS (.zip) → 3 CSV  (aquí sí se usa pandas)
app.py                 servidor web (http.server de la librería estándar), solo llama al motor
web/                   index.html, estilos.css, app.js (front, gráficas SVG propias)
rendimiento.py         benchmarks del panel R11 (redes n, 2n, 4n, …)
tests/verificar_motor.py   auditoría con ast + pruebas unitarias + duplicación
gtfs/                  el zip del GTFS (no se sube a git: pesa 54 MB)
```

---

## Los datos: del GTFS a tres CSV

**Fuente:** `GTFS-2021-07-14.zip` (54 MiB), del bucket público `storage.googleapis.com/gtfs-estaticos/`, enlazado desde el catálogo de datos del Banco Mundial. Para reproducirlo:

```powershell
curl.exe -L -o gtfs/GTFS-2021-07-14.zip https://storage.googleapis.com/gtfs-estaticos/GTFS-2021-07-14.zip
```

```powershell
python convertir_gtfs.py
```

**Resultado:** 147 estaciones, 264 rutas (2.599 filas ruta–orden–estación) y 140.138 horarios.

### Decisiones de la conversión

1. **Solo el componente troncal.** Se toman las rutas con `route_desc = TRONCAL`, que son las estaciones de TransMilenio. Los alimentadores y el SITP urbano tienen miles de paraderos que no son estaciones.
2. **Un día hábil típico.** Solo los viajes cuyo servicio opera los miércoles en `calendar.txt`. Así "buses al día" (R6) cuenta un día real y no suma sábados y domingos.
3. **De vagón a estación.** En el GTFS cada estación tiene varios vagones o plataformas, por ejemplo `Ricaurte A - 1 ó 5` o `Portal Sur T9`. El nombre de la estación es el de la parada sin ese sufijo, que se quita con dos expresiones regulares.
4. **Nombres limpios.** Todo va en MAYÚSCULAS, sin tildes (normalización Unicode NFD), sin caracteres raros (`1º` pasa a `1`), con espacios colapsados y sin repetidos.
5. **Cada ruta va en un solo sentido.** Un mismo `route_short_name` (por ejemplo `1`) tiene viajes con distintos patrones de paradas: los dos sentidos y algunas variantes. Cada patrón distinto es una ruta del CSV. Si solo hay un patrón se conserva el nombre (`A51`). Si hay varios se numeran `1-1`, `1-2`, …, de más viajes a menos.
6. **Una estación por ruta.** Dentro de un patrón, dos vagones seguidos de la misma estación se fusionan. Si una estación reaparece más adelante, se ignora la repetición. Así el par (ruta, estación) es único, que es lo que necesitan R4 y R7.
7. **Horas en `HH:MM`.** Se truncan los segundos y se eliminan los horarios exactamente repetidos.

### Horas ≥ 24:00

El GTFS escribe los viajes que siguen después de medianoche como `24:xx`, `25:10`, etc., porque pertenecen al "día de servicio" anterior. **Decisión: se resta 24, así que `25:10` se guarda como `01:10`.**

Por qué: el horario de un día hábil se repite todos los días, así que el bus de las "25:10" del lunes es exactamente el que un usuario ve pasar el martes a la 01:10. Una hora como `25:10` no es una hora de reloj válida y rompería el formato `HH:MM` que pide el enunciado. Además, así todas las horas quedan en 0…1439 minutos y el arreglo de R4 se ordena como un día normal.

Consecuencia en R4: `proximo_bus(..., "00:00")` puede devolver `01:10` (un bus nocturno). Si se consulta a las 23:50 y ya no hay más buses ese día, devuelve `None`: no se pasa al día siguiente. El motor también aplica esta regla si recibe `25:10` como hora de consulta.

---

## Contrato del motor y retornos

No teníamos el enunciado detallado, así que los retornos se definieron así (también están en las docstrings de `motor/red.py`). Todos los nombres de estación que recibe el motor se normalizan (mayúsculas, sin tildes, sin espacios sobrantes). Los nombres de ruta se comparan exactos.

| Llamada | Devuelve |
|---|---|
| `Red(carpeta)` | Carga `estaciones.csv`, `rutas.csv` y `horarios.csv` de `carpeta`. |
| `red.estado(nombre)` | `(existe, abierta)`: `(False, False)` si no existe, `(True, True)` si está abierta, `(True, False)` si está cerrada. |
| `red.autocompletar(prefijo, k)` | Lista de hasta `k` nombres de estaciones **abiertas** que empiezan por `prefijo`, en orden alfabético. Con `k <= 0` devuelve `[]`. |
| `red.rango(desde, hasta)` | Lista alfabética de las estaciones **abiertas** con `desde <= nombre <= hasta` (ambos incluidos, no tienen que existir). Si `desde > hasta` devuelve `[]`. |
| `red.proximo_bus(estacion, ruta, hora)` | `"HH:MM"` del primer bus a esa hora o después (si pasa justo a esa hora, cuenta). Devuelve `None` si la estación no existe o está cerrada, si la ruta no existe o no pasa por ahí, si la hora es inválida o si no hay más buses ese día. |
| `red.viaje(origen, destino)` | Lista de tramos `(ruta, sube, baja)`: un tramo si es directo y dos con transbordo, `[(r1, origen, cambio), (r2, cambio, destino)]`. Devuelve `[]` si origen = destino y `None` si alguna no existe, está cerrada o no hay viaje con máximo un transbordo. `red.viaje_con_paradas` devuelve además el número de paradas. |
| `red.ranking(k)` | Lista de hasta `k` pares `(nombre, buses_al_día)` de estaciones abiertas, de más a menos buses. Los empates van en orden alfabético. |
| `red.agregar_parada(ruta, nueva, despues_de)` | `True` si insertó `nueva` justo después de `despues_de` (`None` o `""` la pone al inicio). Devuelve `False` si la ruta o la estación no existen, si `despues_de` no está en la ruta o si `nueva` ya está. |
| `red.quitar_parada(ruta, estacion)` | `True` si la quitó. `False` si la ruta no existe o no pasa por esa estación. |
| `red.recorrido(ruta, al_reves=False)` | Lista de nombres de las paradas en orden o al revés, incluidas las cerradas (la ruta pasa por ahí aunque no pare). Si la ruta no existe devuelve `[]`. |
| `red.cerrar(nombre)` / `red.reabrir(nombre)` | `True` si cambió el estado. `False` si no existe o ya estaba en ese estado, y en ese caso no se registra para deshacer. |
| `red.deshacer()` / `red.rehacer()` | `True` si deshizo o rehizo algo. `False` si la pila estaba vacía. |
| `simular_fila(llegadas, frecuencia, capacidad)` | Lista `salidas` del mismo tamaño y en el mismo orden que `llegadas`: `salidas[i]` es la hora a la que sale el bus del pasajero `i`. Los buses salen en 0, f, 2f, … Quien llega justo a la salida alcanza a subir. Devuelve `None` si `frecuencia <= 0` o `capacidad <= 0`, y `[]` si no hay pasajeros. |

**Reglas de R8 dentro de otros requisitos.** Una estación cerrada no aparece en R1 (dice "cerrada"), R2, R3 ni R6. En R4 no se toma el bus ahí. En R5 nadie sube, baja ni transborda ahí: el bus pasa sin parar y esa estación no cuenta como parada.

**Paradas en R5.** Se cuentan las estaciones abiertas donde para el bus después de subir, incluida la de bajada. Por ejemplo, A → B → C → D es un viaje de 3 paradas. Si hay empate en paradas, gana el directo y luego el orden alfabético de (ruta, estación de cambio).

---

## R12 · Decisiones por requisito

En toda la tabla, **n** es el número de estaciones de la red. Los otros símbolos se definen en cada fila.

| Req. | Estructura y algoritmo | Complejidad | Otra opción considerada y por qué se descartó |
|---|---|---|---|
| **Carga** | Una pasada por cada CSV insertando en tablas hash. Cada ruta se arma como lista doble. Merge sort solo si algo viene desordenado (antes se revisa en O(F) si ya están ordenados). | O(F) con F = filas de los CSV. Si los horarios vienen desordenados, O(F log h). | Ordenar siempre: es O(F log F) aunque los datos ya vengan ordenados, como los nuestros. |
| **R1** `estado` | **Tabla hash con encadenamiento** (`TablaHash`): un arreglo de cubetas, cada una una lista de pares `[clave, valor]`, con índice `hash(nombre) % capacidad`. Cuando el factor de carga pasa de 0,75 se duplica el arreglo. Devuelve el objeto `Estacion` con el booleano `abierta`. | **O(1) promedio**. El rehash cuesta O(n), pero repartido entre las inserciones da O(1) amortizado. | **Búsqueda binaria en el arreglo ordenado** (que igual existe para R2): O(log n). Es la consulta más usada de la app, así que preferimos O(1). |
| **R2** `autocompletar` | **Arreglo de estaciones ordenado alfabéticamente** (merge sort propio al cargar) + **búsqueda binaria** (*lower bound*) del primer nombre ≥ prefijo. Desde ahí se avanza mientras el nombre empiece por el prefijo y se juntan hasta k abiertas. | **O(log n + k + c)**, con k = resultados y c = estaciones cerradas que se saltan en el camino (normalmente 0). | **Trie**: O(|prefijo| + k), pero más complejo de programar y de explicar, y no ayuda en R3. **Recorrer todo el arreglo**: O(n). |
| **R3** `rango` | El **mismo arreglo ordenado** + **búsqueda binaria** de `desde`, y recorrido secuencial hasta pasar `hasta`, saltando las cerradas. | **O(log n + m)**, con m = estaciones dentro del rango. | **Árbol de búsqueda balanceado (AVL / rojo-negro)**: mismo O(log n + m), pero mucho más código. Como las estaciones casi nunca se crean, un arreglo ordenado basta. |
| **R4** `proximo_bus` | Tabla hash `(ruta, estación) → arreglo ordenado de minutos` (hora → `h*60+m`) + **búsqueda binaria** del primer minuto ≥ hora. | **O(log h)**, con h = buses de esa ruta en esa estación (cientos en las troncales). Hallar el arreglo es O(1). | **Recorrer el arreglo**: O(h). **Montículo**: sirve para sacar el mínimo, no para buscar "el primero ≥ x". |
| **R5** `viaje` | **Listas de adyacencia**: cada ruta es una lista doble y cada estación guarda una tabla hash con las rutas que pasan por ella. (1) Desde el origen se recorre hacia adelante cada ruta que pasa por él, guardando en una tabla hash `estación → (paradas, ruta)` el mejor valor y detectando los directos. (2) Desde el destino se recorre hacia atrás cada ruta que llega a él, guardando `estación → (paradas hasta destino, ruta)`. (3) Cada estación que está en las dos tablas, con rutas distintas, es un posible transbordo. Se elige el mínimo con un recorrido lineal. | **O(R·p)**, con R = rutas que pasan por el origen o el destino y p = paradas por ruta. No depende de n. (El enunciado excluye R5 de la prueba de rendimiento.) | **BFS o Dijkstra sobre todo el grafo**: recorre toda la red y no limita naturalmente a "máximo un transbordo". **Probar todo par de rutas (r1, r2)**: O(R²·p). |
| **R6** `ranking` | **Arreglo de estaciones abiertas ordenado por (−buses, nombre)** con merge sort, y una **bandera `sucio`**. Cerrar, reabrir, agregar o quitar parada ponen `sucio = True`. La siguiente consulta reordena una sola vez y luego cada consulta lee los primeros k. Los buses por estación se mantienen al día en O(1) en cada edición. | **O(k)** por consulta sin cambios. **O(n log n)** una sola vez después de un cambio. | **Montículo de máximos**: cada consulta saca k elementos, O(k log n), y hay que reconstruirlo. El enunciado dice "se consulta muy seguido y cambia poco", así que conviene pagar al cambiar y no al consultar. **Ordenar en cada consulta**: O(n log n) siempre. |
| **R7** editar rutas | **Lista doblemente enlazada** por ruta (`NodoParada` con `anterior` y `siguiente`) + **tabla hash `(ruta, estación) → nodo`**. Agregar = buscar el nodo de `despues_de` en O(1) y cambiar 4 punteros. Quitar = buscar el nodo y unir el anterior con el siguiente. `recorrido` sigue `siguiente` (o `anterior` si es al revés desde la cola). | `agregar_parada` y `quitar_parada` **O(1)**. `recorrido` **O(p)**, con p = paradas de la ruta. | **Arreglo por ruta**: insertar o quitar en medio desplaza elementos, O(p), y buscar la posición es O(p). **Lista simple**: no puede recorrer al revés en O(p) ni quitar sin conocer el anterior. |
| **R8** cerrar / reabrir | La misma **tabla hash** de R1 + el booleano `estacion.abierta`. Los demás requisitos revisan el booleano y R6 se marca `sucio`. | **O(1)** promedio. | **Sacar la estación del arreglo ordenado y de las rutas**: O(n) y obliga a reconstruir para reabrir. Con el booleano no se pierde nada. |
| **R9** deshacer / rehacer | **Dos pilas** (`Pila`, arreglo con `append`/`pop` al final). Cada cambio exitoso apila una tupla con lo necesario para invertirlo: `("CERRAR", nombre)`, `("REABRIR", nombre)`, `("AGREGAR", ruta, nueva, despues_de)`, `("QUITAR", ruta, estación, anterior)`. Deshacer saca de una pila, aplica la inversa y apila en la otra. Un cambio nuevo vacía la pila de rehacer. | **O(1)** por operación (más el O(1) de la operación que se invierte). | **Guardar copias de toda la red**: O(n) por cambio. **Una sola lista con un índice**: equivale a dos pilas, pero es más fácil equivocarse al "borrar el futuro". |
| **R10** `simular_fila` | **Cola FIFO** (`Cola`) sobre un arreglo con un índice `frente`: encolar es `append` y desencolar es leer `datos[frente]` y sumar 1. Nunca se usa `pop(0)`, que es O(n). Se compacta cuando lo ya atendido es más de la mitad. Los buses vacíos no se simulan: si la fila está vacía, se salta al primer bus después de la próxima llegada. | **O(N + B)**, con N = pasajeros y B = buses que salen con gente. Es O(1) amortizado por pasajero. Si las llegadas vienen desordenadas se suma un merge sort, O(N log N). | **`list.pop(0)`**: O(N) por pasajero, O(N²) en total, y con cientos de miles de pasajeros no termina a tiempo. **Simular minuto a minuto**: depende de la duración y no del número de pasajeros. |

### Estructuras básicas (`motor/estructuras.py`)

| Estructura | Operaciones | Dónde se usa |
|---|---|---|
| `TablaHash` | `poner`, `obtener`, `contiene`, `eliminar`: O(1) promedio | R1, R4, R5, R7, R8, carga |
| `merge_sort(arreglo, clave)` | O(n log n), estable | R2/R3 (al cargar), R6, horarios desordenados |
| `primer_mayor_igual` | búsqueda binaria, O(log n) | R2, R3, R4 |
| `ListaDoble` + `NodoParada` | insertar después / quitar: O(1); recorrer: O(p) | R7, R5 |
| `Pila` | apilar / desapilar: O(1) | R9 |
| `Cola` | encolar / desencolar: O(1) amortizado | R10 |

### Reglas del motor y cómo se verifican

Dentro de `motor/` no se usan `dict`, `set`, `sorted`, `.sort()`, `min`/`max` sobre colecciones, `x in lista`, `.index()`, `.count()`, `bisect`, `heapq`, `collections`, `functools` ni librerías externas. Tampoco `os` (las rutas de archivo se arman con `+ "/"`), y los CSV se leen con `csv.reader`, no con `csv.DictReader`, porque este crea `dict`.

`tests/verificar_motor.py` lo comprueba con el módulo `ast`. Recorre el árbol sintáctico de cada archivo y falla si encuentra imports fuera de `csv`/`time`/`random`, literales o comprensiones de dict y set, los nombres prohibidos, los métodos `.sort`/`.index`/`.count`, el operador `in`/`not in` en comparaciones, `**kwargs` o `__dict__`. Otra prueba confirma que el auditor detecta un archivo con trampas.

---

## R11 · Panel de rendimiento

Está en la pestaña **Rendimiento** de la app (código en `rendimiento.py`). Funciona así:

1. **Cómo crece la red.** La red real se copia 1, 2, 4, 8 (y opcionalmente 16) veces. En cada copia se renombran las estaciones (`AGUAS #2`) y las rutas (`1-1#2`), así que n, las rutas y los horarios crecen exactamente por ese factor. Es el mismo método del script del profesor: duplicar n y mirar.
2. **Medición.** Se corren 2.000 consultas aleatorias por operación, en 5 lotes, y se toma la **mediana** del tiempo por llamada. Como hace `timeit`, el recolector de basura de Python se apaga mientras se mide: sus recolecciones recorren todos los objetos vivos, y con una red grande hacían parecer más lenta una operación O(1) que no cambió.
3. **Gráfica.** En cada operación, la línea sólida es el tiempo medido y la punteada es la complejidad esperada c·f(n), anclada en la primera medición.
4. **Veredicto.** Se compara la mediana de las razones t(2n)/t(n) con la razón teórica f(2n)/f(n), con 50 % de tolerancia. La razón teórica es 1 para O(1), ≈1,1 para O(log n), 2 para O(n) y ≈2,2 para O(n log n).
5. **Explicaciones en el panel.** Cada gráfica trae una explicación. Las más importantes:
   - **R1 sube un poco con la red x8.** No es la tabla hash (la cubeta más llena tiene ~4 pares). Medimos la red x1 sola (1,55 µs) y con la red x8 cargada en memoria (2,01 µs): es la caché del procesador.
   - **R4, R7 (`recorrido`) y R5 son planos.** Al duplicar la red, h (buses por ruta-estación), p (paradas por ruta) y las rutas de cada estación no cambian. Por eso hay una segunda gráfica, **R4 contra h**, que sí hace crecer h y muestra el log h.
   - **R6** se muestra dos veces: la consulta sin cambios (O(k), plana) y la consulta justo después de un cierre (O(n log n)), para que se vea por qué solo se reordena con la bandera `sucio`.

Resultado típico en este equipo:

| Operación | t(2n)/t(n) medido | Esperado |
|---|---|---|
| Carga | 2,16 · 2,03 · 2,02 | 2 (O(n)) |
| R1 estado | 1,45 · 0,81 · 1,03 | 1 |
| R2 autocompletar | 1,19 · 1,17 · 1,12 | ≈1,1 |
| R3 rango (m = 10) | 1,16 · 1,09 · 1,01 | ≈1,1 |
| R4 próximo bus | 1,08 · 1,06 · 1,07 | 1 (h fijo) |
| R6 ranking | 1,04 · 1,03 · 0,97 | 1 |
| R6 tras un cierre | 2,23 · 2,16 · 2,13 | ≈2,2 (O(n log n)) |
| R7 agregar + quitar | 1,04 · 1,09 · 1,06 | 1 |
| R8 cerrar + reabrir | 1,13 · 1,11 · 0,97 | 1 |
| R9 deshacer + rehacer | 1,07 · 1,10 · 0,87 | 1 |
| R10 fila | 2,03 · 2,34 · 2,14 | 2 (O(n)) |

---

## Pruebas (`tests/verificar_motor.py`)

- **Auditoría AST** de `motor/`, y una prueba de que el auditor sí detecta trampas.
- **Red pequeña hecha a mano**, con casos borde de R1 a R9: nombres con tildes y minúsculas, prefijo vacío, `k = 0`, rango invertido, extremos que no existen, horas `25:10`, una hora exacta que coincide con un bus, el último bus, rutas de un solo sentido, transbordos en estaciones cerradas, inserción al inicio y al final, quitar la cabeza y la cola, deshacer/rehacer en orden y "un cambio nuevo borra el rehacer".
- **R10**: entradas vacías o inválidas, llegadas desordenadas, empates y 300.000 pasajeros.
- **Red real** de `datos/`.
- **Duplicación n → 2n**: cada operación menos R5 debe crecer menos de 1,6× (O(1) y O(log n)). R10, con 2N pasajeros, debe crecer menos de 2,8× (O(n)).

```
Ran 20 tests ... OK
  R1 1.11  R2 1.15  R3 1.12  R4 1.04  R6 1.07  R7 1.03  R8 1.09  R9 1.04  R10 2.34
```

## Cómo agregar un requisito nuevo (para el cambio sorpresa)

1. Decidir la estructura: casi siempre basta combinar las que ya existen en `estructuras.py`, por ejemplo una `TablaHash` nueva, un arreglo ordenado con `merge_sort` y `primer_mayor_igual`, o una `Pila`/`Cola`.
2. Agregar el método a `Red` en `motor/red.py`. Si el método cambia la red, que use `_registrar(...)` para que funcione deshacer, y que ponga `self._sucio = True` si afecta el ranking.
3. Correr `python tests/verificar_motor.py auditoria` antes de entregar.
