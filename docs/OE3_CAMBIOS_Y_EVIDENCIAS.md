# OE3 — control de discrepancias y evidencias

**Estado**: rama de propuesta, no aprobada ni fusionada. No equivale a pruebas ejecutadas.

## Cambios aplicados
- Identificación del usuario y rol (`USUARIO_FINAL` / `ADMIN_GLOBAL`).
- Relación `solicitud.owner_user_id`, consultas de solicitudes y de solicitudes-proveedor filtradas por propietario.
- Protección de autorizaciones y lecturas de correo mediante la titularidad de la solicitud.
- Restricción administrativa del importador del catálogo.
- Registro de unidad de medida por artículo (`unidad` en nuevas solicitudes, pendiente de escenarios específicos).
- Esquema de cuenta SMTP por usuario cifrada: pendiente de ruta segura y flujo efectivo de envío.
- Migración manual para copias de PostgreSQL con datos preexistentes. No se autoasignan dueños a solicitudes históricas.

## Bloqueos para fusionar
1. Completar SMTP por usuario con cifrado y no permitir credenciales globales para envíos de varios usuarios.
2. Proteger lectura/edición de proformas, comparación y todas las rutas de consulta asociadas a solicitud.
3. Comprobar rol y restricciones de catálogo sobre cada operación administrativa.
4. Resolver variantes «compus portátiles», respuestas que llenan varios campos y asociar las unidades reales.
5. Aplicar migración en copia, ejecutar pruebas automatizadas e integración con dos cuentas y registrar salidas reproducibles.

## Evidencias mínimas
| ID | Insumo | Resultado esperado | Evidencia reproducible |
|---|---|---|---|
| E03-01 | dos usuarios y solicitudes distintas | B no lee ni altera solicitud A | respuestas HTTP 404/403, test y log sin datos personales |
| E03-02 | usuario final y administrador | importación prohibida a final, permitida a administrador | respuestas HTTP 403/2xx, export CSV ficticio |
| E03-03 | «ocupo cinco compus portátiles Dell con 16 GB RAM» | un artículo laptop, cantidad 5, marca Dell, RAM 16 GB | JSON completo + comparación esperado/observado |
| E03-04 | «ocupo cinco compus con 16 GB RAM» | ambigüedad explícita hasta aclaración | preguntas y estados antes/después |
| E03-05 | «ocupo el puesto de administrador» | no crea una compra válida | JSON, prueba negativa |
| E03-06 | «2 laptops y 3 monitores» | dos artículos, cantidades asociadas sin mezcla | JSON de extracción y persistencia |
| E03-07 | petición con RAM y SSD faltantes; respuesta «16 GB RAM y 512 GB SSD» | resolución de dos atributos sin duplicar preguntas | estado inicial/final y prueba de regresión |
| E03-08 | 3 monitores (unidad), cotización por proveedor compatible | unidad coherente y solo artículos ofrecidos | tablas SQL, salida API |
| E03-09 | correo borrador, rechazo, autorización y envío simulado | no envío sin autorización; usuario B no puede autorizar de A | test con SMTP falso y sin credenciales |
| E03-10 | cuentas SMTP A y B | envío A usa exclusivamente cuenta A cifrada | configuración oculta, registro de SMTP falso |
| E03-11 | migración en PostgreSQL de prueba | FKs, roles, índice, usuarios históricos sin asignar | psql -f, esquema antes/después |
| E03-12 | casos funcionales previstos en Capítulo III | registrar esperado, obtenido, estado, versión y fecha | matriz firmada con capturas y logs |

**Control**: NO describir estas pruebas como exitosas antes de ejecutarlas. El DOC-06 es la fuente literal de OE3 y Producto 3. Capturas de interfaz son evidencia de visualización, no sustituyen respuestas HTTP, registros de BD y pruebas.


## Estado real de CI — 22 de octubre de 2026
Se registraron tres ejecuciones fallidas de GitHub Actions:
- https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39734513653
- https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39734586056
- https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39735962870

Las consultas a `actions/runs/{id}/jobs` mostraron **0 jobs**. No hay logs de `pytest`: no atribuir el fallo a tests funcionales. Revisar GitHub Actions → Actions permissions, disponibilidad de runners y validación de workflow. La rama NO está aprobada.

### Ejecución reproducible en entorno de desarrollo (sin datos reales)
```bash
python -m venv .venv
# Activar .venv para el SO correspondiente
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_oe3_regresion.py
```
Guardar consola completa, versión Python, versiones de dependencias, SHA del commit y fecha.
La suite aislada utiliza SQLite para comprobar lógica ORM básica; NO sustituye la migración PostgreSQL ni las pruebas HTTP, de correo SMTP o de permisos entre dos sesiones.

### Migración PostgreSQL
1. Respaldar la BD y utilizar copia local de pruebas; detener escrituras.
2. Ejecutar `migrations/manual_oe3_20261022.sql` con cuenta autorizada.
3. Inspeccionar los registros históricos cuyo `owner_user_id` sea nulo; asignar titulares únicamente con fuente administrativa verificada.
4. Probar acceso cruzado como dos usuarios distintos. Registrar resultados; luego decidir el endurecimiento NOT NULL de `solicitud.owner_user_id`.
5. Mantener la rama aislada hasta que todos los puntos anteriores sean satisfactorios.


## Registro CI confirmado — 2026-10-22
- Causa de bloqueo anterior: `DATABASE_URL: sqlite+pysqlite:///:memory:` sin comillas causaba error al analizar YAML; se corrigió con comillas.
- Evidencia de 4 casos: https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39736451566 — log: `4 passed in 1.48s`.
- Evidencia de 5 casos: https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39736635421 — log: `5 passed in 1.79s`. Incluye SMTP falso con autorización previa y cuenta del propietario, sin enviar correos reales.
- Estos resultados SOLO acreditan las regresiones incluidas en `tests/test_oe3_regresion.py` con SQLite, no los 12 escenarios completos ni migración PostgreSQL.
- Pendientes: controles HTTP de extremo a extremo con dos sesiones; migración en PostgreSQL real de prueba; cuenta SMTP configurada desde interfaz; simulación completa de flujo por proveedor; caso negativo no comercial; evaluación de unidad de medida específica y de los escenarios metodológicos del Capítulo III.

## Ejecución integrada verificada — 2026-10-22
GitHub Actions https://github.com/AndreaCarrilloOp/PLN-Proformas/actions/runs/39737738563 (commit `6ea8678612f46a1a345b683b9f721c016cd66ab7`):
- `oe3`: **8 passed, 1 warning** — regresión ORM/PLN, aislamiento mediante tres sesiones TestClient, respuestas multiatributo, catálogo por rol, SMTP falso y flujo de solicitud/proveedor/correo.
- `postgres-migration`: **1 passed** — PostgreSQL 16 real en CI, migración `manual_oe3_20261022.sql`, presencia de columna de propietario, roles, tabla SMTP y prueba negativa de clave foránea. El error FK registrado es esperado.
- **No** se aplicó migración a BD productiva o local persistente. Se ensayó en esquema temporal `oe3_audit` y fue eliminado.
- La verificación de SMTP usó servidor falso: no hubo correos reales ni contraseñas reales.
- Sigue pendiente documentar ejecuciones completas S01–S20 del diseño metodológico, además de la revisión visual de interfaz final y evidencia del despliegue local. El 100 % de los indicadores del OE5 no se desprende de estas nueve pruebas técnicas.
