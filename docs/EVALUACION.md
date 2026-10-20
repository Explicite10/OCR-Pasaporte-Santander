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
4. Base de datos / historial y endpoint de revisión humana, copiados de `OCR-INE-Santander`.
