# Integrantes

Grupo de 3 o 4 personas. En la sustentación cada persona responde sobre un requisito que **no** hizo, así que esta tabla tiene que ser exacta.

| Integrante | Código | Correo | Requisitos que hizo |
|---|---|---|---|
| _Nombre 1_ | _código_ | _correo_ | _p. ej. R1, R2, R3 + conversión GTFS_ |
| _Nombre 2_ | _código_ | _correo_ | _p. ej. R4, R5, R6_ |
| _Nombre 3_ | _código_ | _correo_ | _p. ej. R7, R8, R9_ |
| _Nombre 4 (opcional)_ | _código_ | _correo_ | _p. ej. R10, R11, R12 (README)_ |

## Reparto sugerido por archivos

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
