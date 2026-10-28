# Evaluación inicial (lote Santander, 20-oct-2026)

## El lote

- 503 PDFs únicos (los dos zips de OneDrive se traslapan: el segundo, de 249, está contenido en el primero).
- Todos escaneados (sólo 3 traen capa de texto), 1-2 páginas en el 90 % (hasta 87 en un caso), carta/A4.
- Fotocopias en blanco y negro con sello "cotejado contra original" encima; giros de 90°/180° frecuentes.
- Pasaportes de ~45 países: MEX 159, COL 56, VEN 45, ARG 27, ESP 20, CUB 16, KOR 14, CHL 13, PER 13, BRA 12...
- En 245 PDFs (49 %) viene además la **tarjeta de residente del INM** (MRZ TD1 `I<MEX...`), y en
  ~25 PDFs (5 %) **no hay pasaporte**: sólo la tarjeta del INM, recibos de CFE o constancias del SAT.
- Barrido con PaddleOCR sin giros: la MRZ TD3 aparece legible en 445 docs (88 %); el resto son
  pasaportes girados (los resuelve el pipeline con giros y el localizador) o PDFs sin pasaporte.

## Lote completo, versión 1 (PaddleOCR + Qwen3-VL 8B) — 503 docs

| | |
|---|---|
| ok / revisar / rechazado / error | 443 (88 %) / 47 (9 %) / 11 / 2 |
| Código 200 (todo cuadra) | 371 (74 %) |
| Código 210 (alguna discrepancia) | 105 (21 %) |
| MRZ íntegra (todos los dígitos verificadores) | 453 (90 %) · 429 leídas por OCR, 63 rescatadas por el VLM |
| Recorte por ancla MRZ / localizador VLM / página completa | 477 / 13 / 11 |
| Confianza alta: número / apellidos / nombres / nacimiento / vencimiento / sexo | 447 / 457 / 462 / 455 / 456 / 461 (de 490 con datos) |
| CURP (sólo MEX, 159): alta / baja / vacía | 128 / 35 (VLM la lee mal) |
| Tiempo (3 en paralelo, CPU para OCR, GPU 8 GB para VLM) | mediana 15.6 s/doc; ~8.8 s/doc de rendimiento |

Qué causaba los 105 códigos 210 (y se corrige en la v2):
- 35: el VLM lee mal el número impreso (F/P, dígitos pegados del ID nacional) aunque la MRZ cuadra con
  su dígito verificador → ahora la MRZ manda y queda como aviso.
- 23 + 21 + 11: CURP mal leída por el VLM → ahora se busca también en el OCR y se repara con la fecha y
  sexo de la MRZ.
- 23 + 14: apellidos/nombres con palabras de más o de menos (apellidos compuestos, "HUANG, HAIXIN",
  "MARC0") → tolerancia por palabras y limpieza de dígitos.
- 12: país emisor ilegible en la MRZ (RAS, HLB, GOI... no existen) → se usa el impreso o la nacionalidad.
- ~15 PDFs con sólo la tarjeta del INM salían con un "pasaporte" inventado por el VLM → ahora se rechazan
  como `NO_ES_PASAPORTE` con `documento_detectado = tarjeta_residente_inm`.
- 2 PDFs de 19 y 87 páginas rechazados por el límite de 15 → límite 30.

## Comparación de modelos de visión (mismos 60 docs, mismo pipeline v1)

| Modelo | ok / revisar | MRZ íntegra | Conf. alta: número · apellidos · nombres · CURP | VLM s/doc |
|---|---|---|---|---|
| **qwen3-vl:8b-instruct** (6.2 GB) | **59 / 1** | 59 | 57 · 60 · 60 · 20 | 6.8 |
| qwen3.5:9b (6.6 GB, think off) | 58 / 2 | 59 | 59 · 59 · 59 · 22 | 9.1 |
| glm-ocr (0.9B, 2.7 GB) | 46 / 14 | 56 | 56 · 49 · 51 · 3 | ~5 |

Conclusión: Qwen3-VL 8B instruct sigue siendo la mejor opción open source para este trabajo en una GPU de
8 GB; qwen3.5:9b empata en calidad pero es 35 % más lento y requiere apagar el razonamiento; glm-ocr es
rápido y chico pero mucho menos preciso en campos impresos y CURP. Como además es el mismo modelo que usa
la API de INE, ambos servicios pueden compartir un solo Ollama.

## Lote completo, versión 2 (mismo modelo, con los ajustes anteriores) — 503 docs

| | v1 | v2 |
|---|---|---|
| ok / revisar | 443 / 47 | **455 / 26** |
| rechazado (no es pasaporte) / error | 11 / 2 | 21 (todos con `tarjeta_residente_inm` o sin pasaporte) / 1 (PDF de 87 páginas) |
| Código 200 (todo cuadra) | 371 (74 %) | **378 (75 %)** |
| Código 210 (discrepancia real) | 105 (21 %) | **48 (10 %)** |
| Código 211 (avisos: la MRZ mandó sobre la lectura visual, nombres con palabras de más, etc.) | 14 | 55 |
| MRZ íntegra | 453 | **461 (92 %)** |
| Confianza alta: número / apellidos / nombres / nacimiento / vencimiento / sexo | 447 / 457 / 462 / 455 / 456 / 461 | **469 / 464 / 469 / 473 / 469 / 469** (de 481 pasaportes) |
| CURP alta / baja (pasaportes MEX) | 128 / 35 | **137 / 21** |
| Mediana por doc | 15.6 s | 15.5 s (~6.6 s/doc de rendimiento con 3 en paralelo) |

Sobre los 481 PDFs que sí traen pasaporte: **94.6 % salen `ok`** y en el 97-98 % los campos con dígito
verificador (número, nacimiento, vencimiento) quedan en confianza alta, es decir, respaldados por la MRZ.

Lo que queda en `revisar` / 210 (48 docs) es sobre todo: MRZ parcialmente ilegible en copias muy tenues
(20 con compuesto roto), CURP que el VLM y el OCR no logran leer (18) y apellidos que no cuadran con la
MRZ (9). Son los candidatos a revisión humana, que es justo lo que el código 210 señala.

## Siguientes pasos sugeridos

1. **Verdad de terreno**: capturar a mano ~50 documentos (`scripts/evaluar.py` como en INE) para medir la
   exactitud real por campo y confirmar que `alta` ≈ 100 %.
2. **Tarjeta de residente del INM** como segundo tipo de documento (MRZ TD1 `I<MEX`, 49 % de los PDFs la
   traen y 4 % sólo traen esa): mismo pipeline con el parser TD1 del proyecto de INE.
3. **Velocidad**: PaddleOCR en GPU o 200 dpi para bajar los ~9 s de OCR por documento.
4. Base de datos / historial y endpoint de revisión humana, copiados de `OCR-INE-OpenSource`.

## Plan de atención (validacion_plan), 27-oct-2026

Prueba de punta a punta contra la API desplegada (`scripts/probar_plan.py`): los 42 PDFs de la
verificación de homologación, cada uno con una solicitud armada con los datos del lote v2.

| | Resultado |
|---|---|
| Pasaportes que cumplen el plan con la solicitud correcta | **36 de 38** |
| No pasaportes (tarjeta INM y otros) rechazados con `es_pasaporte = NO` | 4 de 4 |
| Solicitudes alteradas rechazadas: otra fecha / otra nacionalidad | 38 de 38 / 38 de 38 |
| Solicitudes alteradas rechazadas: nombre con una palabra menos | 37 de 38 |
| ERROR del contrato homologado en las 42 respuestas | 0 |

- Los 2 pasaportes que no cumplen y la solicitud alterada aceptada vienen de los datos de prueba, no del
  plan: la "solicitud correcta" se tomó de una corrida anterior que en esos documentos traía una MRZ mal
  leída (fecha 1929 y nacionalidad `OGF`), un apellido con la Ñ transliterada (`NXX`) o un nombre con una
  palabra repetida.
- La primera corrida marcó como vencidos 2 pasaportes haitianos: la hoja se leyó con vencimiento 2023 y la
  MRZ íntegra dice 2028. Desde entonces la vigencia usa la fecha de la MRZ cuando es íntegra.

## Precisión contra verdad de terreno (27-oct-2026)

Método: 50 PDFs del lote elegidos para cubrir casos difíciles (8 `revisar`, 10 mexicanos con CURP, 6 de
un apellido, 6 con acentos o Ñ, 5 girados o sin ancla, 15 al azar; 19 países). Un segundo lector (modelo
de visión independiente del motor) transcribió la página de datos **sin ver la respuesta de la API**;
`scripts/comparar_verdad.py` comparó campo por campo. Las discrepancias con valores quedaron en
`lote/verdad/discrepancias.csv` en el servidor (datos personales; no se versiona) para revisión humana.

| Campo | Homologado (`datos` = lectura impresa) | Interno (la MRZ manda) |
|---|---:|---:|
| País emisor, nacionalidad, sexo, expedición | 100 % | 100 % |
| Fecha de nacimiento | 98.0 % | **100 %** |
| Fecha de vencimiento | 95.9 % | **100 %** |
| Número de pasaporte | 91.8 % | **98.0 %** |
| Apellidos / nombres | 98.0 % / 98.0 % | 98.0 % / 100 % |
| Lugar de nacimiento | 98.0 % (+1 parcial) | 98.0 % (+1 parcial) |
| CURP (19 mexicanos) | 84.2 % | 84.2 % |
| Autoridad (40 con dato) | 72.5 % | 72.5 % |
| **Total, 549 campos** | **95.6 %** | **96.9 %** |
| Documentos con todos los campos correctos | 30 de 49 (61 %) | 33 de 49 (67 %) |
| Sin contar autoridad (campo sin definición clara) | 97.4 % | 98.8 % |

Lectura de los resultados:

- **Los campos con dígito verificador salen perfectos cuando la MRZ manda** (número, nacimiento,
  vencimiento: 100 % salvo un número con MRZ cortada en la copia). Con la regla de la referencia, `datos`
  lleva lo impreso y hereda los errores de lectura del modelo (4 números, 2 vencimientos, 1 nacimiento,
  1 par apellidos/nombres invertido); **todos ellos salieron con código 210**, es decir, la API sí los
  señaló como discrepancia.
- **Autoridad** es el campo débil y en buena parte por definición: en pasaportes mexicanos el campo trae
  nombre del funcionario y oficina, y la API devuelve uno u otro; en Bolivia y Costa Rica no hay
  autoridad impresa, solo lugar de expedición. De las 11 diferencias, 5 son de definición, 3 lecturas
  parciales y 3 errores reales en copias tenues.
- **CURP**: 3 fallas de 19, todas marcadas con confianza `baja`: dos CURP tapadas por sello o foto
  fantasma (ilegibles también para el lector humano) y una `O` por `0` en la homoclave.
- **Un documento de 50 no se detectó bien**: traía la tarjeta INM en la página 1 y el pasaporte
  (libanés) girado 90° en la página 2; el localizador tomó la tarjeta y devolvió un pasaporte inventado
  con código 210. En otro caso parecido (pasaporte cubano en la página 2) sí lo encontró.

Mejoras que salen de esta medición, pendientes:

1. Si el recorte del localizador no produce una MRZ TD3 válida, seguir con la siguiente página en vez de
   quedarse con ese recorte (caso del pasaporte libanés).
2. Al tomar nombres de la MRZ, convertir la transliteración ICAO (`NXX` → Ñ) antes de entregarlos.
3. Reparar la CURP cuando la única diferencia es `O`/`0` en la homoclave (el dígito verificador lo
   confirma).
4. Definir con el consumidor qué debe llevar `autoridad_expedidora` en pasaportes mexicanos (oficina o
   funcionario).
