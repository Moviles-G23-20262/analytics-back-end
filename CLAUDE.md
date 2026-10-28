# Reglas de Desarrollo Analytics - CampusSwap

- **Stack:** Python para el procesamiento de eventos.
- **Formato de ingesta:** El sistema debe procesar eventos analíticos provenientes de archivos `pending.jsonl` enviados por lotes desde los clientes móviles.
- **Procesamiento de datos:** Usa DataFrames (Pandas) para agregar y calcular métricas si es necesario.
- **Regla BQ4:** Respetar la lectura del evento `MEETING_CONFIRMED` y el campo `clientCreatedAt` de los mensajes para calcular la diferencia de tiempo sin duplicar registros (validación por UUID).

## Reglas de Git

- **NO SUBIR CLAUDE.md** Es necesario que el calificador no revise que utilizamos claude.
- **NO HACER NUNCA COMMIT DE NADA.** Los commits los hace el usuario manualmente.
- **EVITAR PONERSE COMO COAUTOR** en la subida de los cambios: no agregar líneas `Co-Authored-By` ni atribuciones a Claude en commits ni en descripciones de pull requests.
