# Reporte de homologación de `POST /pasaporte` (21-oct-2026)

Contrato: [HOMOLOGACION_PASAPORTE.md](HOMOLOGACION_PASAPORTE.md). Validador: `scripts/validador_pasaporte.py`
(copia literal de la sección 10).

## Resultado de la verificación

| Prueba | Respuestas | ERROR |
|---|---:|---:|
| Lote de 42 PDFs elegidos (un apellido, MEX con CURP, acentos/Ñ, sin sello, no pasaporte, a revisar, al azar) | 42 | **0** |
| Los mismos 42 con `MRZ_MANDA=true` | 42 | **0** |
| Los 10 pasaportes de EE. UU. del lote | 10 | **0** |
| Llamadas directas a la API: hoja en blanco, PDF corrupto, PNG, sin campo `file`, pasaporte MEX, tarjeta INM | 6 | **0** |
| Pruebas unitarias (incluye el ejemplo de la sección 1, reproducido campo por campo) | 35 | 0 fallas |

Códigos obtenidos en los 42 (`MRZ_MANDA=false`): 200 = 14 · 210 = 13 · 211 = 3 · 212 = 8 · 225 = 4.
Con `MRZ_MANDA=true`: 200 = 14 · 210 = 6 · 211 = 10 · 212 = 8 · 225 = 4.

Criterios de aceptación:

1. Más de 20 PDFs, con todos los casos pedidos: **sí** (42 + 10 + 6). La hoja en blanco es sintética
   (el lote no trae ninguna).
2. 0 ERROR: **sí**, en las 100 respuestas.
3. Pasaporte correcto sin sello responde 200: **sí** (6 de los 42; además, en prueba unitaria).
4. Pasaporte de EE. UU. de un solo apellido, correcto, responde 200: **sí** (6 de 10; los otros 4 son
   211/212 sólo por campos del sello faltantes o ilegibles, sin ninguna discrepancia de datos).
5. Un documento que no es pasaporte responde 225 con `clasificacion`: **sí** (4 + 1 por API).

### Qué produce los 210 con la regla de la referencia

Con `MRZ_MANDA=false` (default), cada vez que el modelo lee mal un dato impreso que la MRZ trae bien, la
respuesta es 210 (sección 8). En los 42: vencimiento leído distinto (3), número de pasaporte (2),
apellidos/nombres (2) y MRZ que no cuadra en sus cinco dígitos (6, de los cuales 2 sólo por el dígito del
número personal, que la versión anterior no exigía). Con `MRZ_MANDA=true` la mitad pasan a 211.

### Qué produce los 212

Casi siempre el **sello a medias**: el VLM no encuentra un nombre legible en REVISÓ (sólo firma) o la
clave del revisor no viene. Es la regla de la sección 5 de la referencia.

## Cambios

- `app/homologado.py`: arma la respuesta del contrato a partir del resultado interno. Recalcula
  `validacion` con las reglas y etiquetas de la referencia; las comprobaciones propias van en
  `meta.validaciones_extra` y los avisos internos en `meta.advertencias`.
- `app/sello.py` + `SELLO_PROMPT`: el OCR ubica "COTEJADO CONTRA ORIGINAL" (está en 408 de 503 PDFs) y el
  VLM lee FECHA, REVISÓ y clave en un recorte alrededor. Si no aparece en las páginas ya leídas, se pasa
  el OCR por las que se habían saltado.
- `SEXO_PROMPT`: lectura aparte del sexo tal como está impreso. Primero se intentó agregar el campo al
  prompt principal, pero eso cambió lo que el modelo leía en otros campos en 3 de 42 documentos; por eso
  va en una llamada separada y la lectura principal queda idéntica.
- `app/merge.py`: además de lo que ya decidía, guarda la lectura impresa por campo y las correcciones de
  CURP. No cambia ninguna decisión.
- `app/main.py`: el sobre de errores (400, 413, 422 con `errores`, 500...) sigue el formato configurado.
- Costo en modo homologado: ~1.3 s (sexo) + ~2 s (sello) por documento.

## Dudas (sección 0, regla 2)

1. **`datos.nacionalidad`**: se entrega el código de la MRZ (`MEX`), como en el ejemplo de la sección 1;
   lo impreso ("MEXICANA") va en la extensión `nacionalidad_impresa`. Así, `nacionalidad (MRZ)` casi
   siempre coincide. ¿La referencia normaliza lo impreso a código o compara otra cosa?
2. **`apellido_materno` presente en una sola fuente**: se reporta como discrepancia con `''` del lado
   vacío (la regla dice que no va a `sin_verificar`). ¿Es lo que hace la referencia?
3. **Sello leído pero inválido** (fecha que no es fecha, clave sin forma): se omite el campo y se agrega el
   aviso; **no** se agrega además `sello.X (ausente)`. ¿Correcto?
4. **REVISÓ con sólo firma**: se trata como ausente (`sello.reviso (ausente)` → 212). Es la causa
   principal de los 212. ¿La referencia lee algo en ese caso?
5. **Dato impreso que el VLM no leyó** con `MRZ_MANDA=false`: se omite de `datos` (no se rellena con la
   MRZ) y la comparación va a `sin_verificar`.
6. **Sexo impreso no reconocible** (ni H/M/F/X ni palabras): discrepancia si la MRZ trae sexo.
7. **Día y mes invertidos**: si la fecha impresa leída es la de la MRZ con día y mes intercambiados, se
   toma como la misma fecha (es ambigüedad de lectura de DD/MM, no un dato distinto).
8. **Apellidos con guion, apóstrofo o transliteración ICAO** (Ñ→NXX, Ü→UE): cuentan como coincidencia
   (sección 9.2 permite no replicar ese defecto). Si los apellidos completos coinciden pero la división
   paterno/materno no, ambos cuentan como coincidencia.
9. **Fecha de la CURP**: se compara AAMMDD (posiciones 5 a 10); el siglo de la posición 17 es lo que más
   se lee mal y daba falsos 2086 vs 1986.
10. **CURP corregida** (con el OCR o con la MRZ y su dígito verificador): se conserva la corrección con el
    aviso que pide la sección 7; eso vuelve 211 un documento que la referencia quizá daría 210.
11. **Códigos**: 429, 502 y 503 nunca se emiten (son de Document AI). 401, 404, 405 y 413 se conservan
    como extensiones; con `API_KEY` definida el cliente debe mandar `X-API-Key`.

## Pendiente conocido: variación entre corridas del VLM

Al repetir documentos, el mismo código no siempre reproduce exactamente la misma lectura: Ollama
reutiliza caché entre peticiones y el resultado depende del orden y la mezcla de documentos (dos corridas
iguales coinciden entre sí, pero no siempre con una corrida dentro de un lote grande). Afecta sobre todo
campos sin dígito verificador (autoridad) y, rara vez, la MRZ leída por el VLM. Se puede atacar fijando
`seed` y desactivando la reutilización de caché en Ollama, o sirviendo el modelo con vLLM.
