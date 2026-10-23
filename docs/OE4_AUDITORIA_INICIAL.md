# OE4 — Auditoría técnica inicial

**Fuente examinada:** commit `f90c8aa94ba187fa3f04abee395661d9863c0858` de `feat/oe3-solicitudes`.  
**Alcance literal del OE4:** Implementar un módulo de administración del catálogo relacional y extracción básica de información desde documentos relacionados con solicitudes y proformas.  
**Producto literal:** Módulo para administrar el catálogo centralizado de proveedores y realizar carga y extracción básica de información desde documentos PDF relacionados con proformas.

## Inventario contrastado con código

| Componente | Verificado en fuente | Pendiente de implementar o acreditar |
|---|---|---|
| Catálogos | GET de resumen y listados de 8 tipos en `app/api/routes/catalog.py` | CRUD administrativo individual: alta, consulta de detalle, edición, baja controlada; operaciones y permisos por entidad |
| Importador | POST CSV/XLSX de 11 tipos, acceso `ADMIN_GLOBAL`; servicio `import_service.py` | Pruebas por tipo, consistencia por lote, rollback, duplicados, hojas vacías, columnas y referencias inválidas; límites de XLSX |
| Proveedores | Entidad `proveedor`, relación `proveedor_producto_servicio`, importador y consultas | CRUD y actualización de asociaciones, baja lógica, pruebas de cobertura y catálogo |
| PDF | POST de proforma, extensión, tamaño, cabecera `%PDF`, extracción con `pdfplumber` | Rechazar PDF sin texto seleccionable antes de persistir, validar PDFs dañados y cifrados; ensayar múltiples plantillas |
| Extracción | `PDFService._extract_details` usa búsqueda de nombres y patrones de número/precio | Manejar formatos numéricos y monedas ambiguas, repetición de artículos, asociación precio-cantidad, subtotal/total, evaluación de falsos positivos |
| Persistencia de proforma | `proforma` y `proforma_detalle`, revisión humana y estado `VALIDADA` | Verificar coherencia entre solicitud, proveedor, artículos, campos revisados y proforma; escenarios negativos y aislamiento entre usuarios |
| Comparación | Consulta básica de detalles de proformas validadas | Casos comparables y no comparables; moneda y unidad explícitas; no asumir normalización monetaria |
| UI | Pantallas de catálogo, carga múltiple y revisión de proformas | Verificar funciones administrativas editables y accesibilidad; evidencias de navegador reales de OE4 |

## Hallazgos concretos

1. **C1 (alta):** `app/api/routes/catalog.py` expone GET y POST /importar; no hay rutas CRUD individuales de edición/eliminación. La importación no equivale a CRUD completo.
2. **P1 (alta):** `PDFService.process_upload` persiste `Quote(status="PRELIMINAR")` aun si `_extract_text` retorna cadena vacía. El alcance del TFG excluye OCR; para PDF sin texto debe documentarse/rechazarse o tratarse como caso no procesable sin afirmar extracción.
3. **P2 (alta):** `_extract_details` toma la primera línea coincidente por producto y el último precio detectado. No está acreditada una extracción fiable de documentos heterogéneos, ni varias líneas de un mismo producto.
4. **P3 (media):** La comprobación `%PDF` solo examina los primeros bytes; además la extensión no prueba que el documento sea legible. Se debe mantener tratamiento seguro de PDFs corruptos.
5. **I1 (alta):** `Quote` almacena `request_id` y `provider_id`; no valida correspondencia entre el proveedor indicado y la solicitud por proveedor compatible antes de persistir.
6. **V1 (media):** `validate` reemplaza todos los detalles y marca `VALIDADA` sin exigir como mínimo una línea ni contrastar cálculos. Las decisiones humanas deben quedar documentadas.
7. **T1 (alta):** Las 35 pruebas de aplicación del workflow OE3 y las 2 PostgreSQL no constituyen por sí solas un expediente de pruebas específico del OE4. Faltan pruebas automáticas de PDF, CRUD y catálogo.
8. **S1 (seguimiento):** Las credenciales SMTP externas y la migración de datos originales de OE3 siguen pendientes fuera del alcance funcional de esta rama; no incluir como capacidades acreditadas de OE4.

## Plan por dependencias

1. Añadir pruebas de referencia y controles de seguridad para catálogos, importadores y PDFs; sin datos reales ni OCR.
2. Completar CRUD y asociaciones de proveedores/productos para `ADMIN_GLOBAL`, conservando lectura autorizada de `USUARIO_FINAL`.
3. Fortalecer validación de importación y transacciones sin comprometer datos existentes.
4. Endurecer carga PDF (texto seleccionable, manejo de error, exclusión OCR); mejorar extracción básica y validación humana.
5. Ejecutar casos positivos/negativos, pruebas de permisos y persistencia PostgreSQL; obtener capturas reales y relacionar con requerimientos OE2.
6. Sólo entonces redactar resultados 4.4 y conclusiones/recomendaciones OE4 para Capítulo V sobre copia acumulativa, sin alterar secciones aprobadas.

## Condiciones de integración

- Rama `feat/oe4-catalogo-pdf` creada desde OE3; no fusionar contra `main` mientras OE3 esté en borrador.
- PR OE4 dirigido inicialmente a `feat/oe3-solicitudes` para que muestre solo los cambios de OE4; retarget a `main` tras integrar OE3.
- Mantener objetivos/productos DOC-06 literales.
- No afirmar pruebas ni funcionalidad que todavía no se ejecutaron.
