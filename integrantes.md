# Integrantes

| Integrante | Partes a cargo |
|---|---|
| Santiago Montaño | Conversión GTFS (`convertir_gtfs.py`, `datos/`), estructuras base (`motor/estructuras.py`), app web (`app.py`, `web/`) |
| Camilo Romero | R1, R2, R3: `estado`, `autocompletar`, `rango` |
| Simón Troncoso | R4, R5, R6: `proximo_bus`, `viaje`, `ranking` |
| Mariam Ruiz | R7, R8, R9: `agregar_parada`, `quitar_parada`, `recorrido`, `cerrar`, `reabrir`, `deshacer`, `rehacer` |
| Samuel Rueda | R10, R11, R12: `motor/simulacion.py`, `rendimiento.py`, pruebas (`tests/`) y README |

## Dónde está cada parte

| Parte | Archivos |
|---|---|
| Conversión GTFS | `convertir_gtfs.py`, `datos/` |
| Estructuras base | `motor/estructuras.py` (`TablaHash`, `merge_sort`, `primer_mayor_igual`, `ListaDoble`, `Pila`, `Cola`) |
| R1–R3 | `Red.estado`, `Red.autocompletar`, `Red.rango` en `motor/red.py` |
| R4–R6 | `Red.proximo_bus`, `Red.viaje` / `viaje_con_paradas`, `Red.ranking` |
| R7–R9 | `Red.agregar_parada`, `quitar_parada`, `recorrido`, `cerrar`, `reabrir`, `deshacer`, `rehacer` |
| R10 | `motor/simulacion.py` |
| R11 | `rendimiento.py`, pestaña Rendimiento de `web/` |
| App | `app.py`, `web/` |
| Pruebas | `tests/verificar_motor.py` |
