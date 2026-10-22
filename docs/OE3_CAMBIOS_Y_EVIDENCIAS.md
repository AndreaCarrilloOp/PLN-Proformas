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
