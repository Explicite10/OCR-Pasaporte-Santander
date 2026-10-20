# Resumen del lote (503 documentos) · VLM: qwen3-vl:8b-instruct

## Estados
- ok: 455 (90.5%)
- revisar: 26 (5.2%)
- rechazado: 21 (4.2%)
- error: 1 (0.2%)

## Código de la API
- 200: 378 (75.1%)
- 210: 48 (9.5%)
- 211: 55 (10.9%)
- 220: 21 (4.2%)
- 224: 1 (0.2%)

## MRZ íntegra (todos los dígitos verificadores): 461 (91.7%)
- fuente: {'ocr': 434, 'vlm': 57, None: 12}
- recorte: {'ancla': 472, 'pagina_completa': 13, 'localizador': 17, None: 1}

## Países emisores
- MEX: 158
- COL: 56
- VEN: 45
- ARG: 27
- None: 22
- ESP: 21
- CUB: 18
- BRA: 14
- KOR: 14
- CHL: 14
- PER: 13
- ITA: 11
- USA: 10
- HND: 8
- CAN: 7
- ECU: 6
- FRA: 6
- CRI: 5
- SLV: 5
- HTI: 5
- CHN: 4
- D: 4
- ISR: 3
- BOL: 3
- URY: 3
- GTM: 2
- PRT: 2
- POL: 2
- JPN: 2
- DEU: 2
- GBR: 2
- SVK: 1
- PAN: 1
- GBS: 1
- NGA: 1
- SVN: 1
- IND: 1
- NIC: 1
- PRY: 1
- ISL: 1

## Confianza por campo (alta / media / baja / vacío)
- numero_pasaporte: 469 / 7 / 5 / 22
- apellidos: 464 / 6 / 11 / 22
- nombres: 469 / 3 / 9 / 22
- fecha_nacimiento: 473 / 4 / 4 / 22
- fecha_vencimiento: 469 / 7 / 5 / 22
- sexo: 469 / 8 / 4 / 22
- pais_emisor: 465 / 14 / 2 / 22
- nacionalidad: 461 / 16 / 4 / 22
- fecha_expedicion: 474 / 0 / 2 / 27
- lugar_nacimiento: 0 / 463 / 0 / 40
- autoridad: 0 / 403 / 0 / 100
- curp: 137 / 0 / 21 / 345

## Validaciones que más fallan
- mrz_compuesto: 20
- curp_vs_fecha_nacimiento: 18
- numero_pasaporte_mrz_vs_impreso: 10
- curp_estructura_y_digito: 9
- curp_vs_sexo: 9
- mrz_opcional: 9
- apellidos_mrz_vs_impreso: 9
- mrz_vencimiento: 8
- mrz_numero: 7
- mrz_fecha_nacimiento: 6
- nombres_mrz_vs_impreso: 5
- fecha_nacimiento_mrz_vs_impresa: 2
- fecha_vencimiento_mrz_vs_impresa: 2
- fecha_expedicion_antes_de_vencimiento: 2

## Tiempos
- mediana por documento: 15.5 s
- promedio: 26.1 s · máximo: 252.9 s
- ocr_y_recorte: 17.9 s/doc
- vlm_pasaporte: 6.7 s/doc
- localizacion_vlm: 0.8 s/doc
- vlm_mrz: 0.3 s/doc
- render: 0.3 s/doc

## Errores y rechazos
- 4876365.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4885788.pdf: No se reconoció un pasaporte: sin MRZ válida y sin número de pasaporte ni nombre legibles
- 4891242.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4899485.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4904094.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4910218.pdf: No se reconoció un pasaporte: sin MRZ válida y sin número de pasaporte ni nombre legibles
- 4918040.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4920776.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4922215.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4931477.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4968405.pdf: El documento trae 87 páginas; el máximo por llamada es 30
- 4977342.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4991853.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4995308.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 4998941.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5001579.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5016009.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5028336.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5040030.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5049473.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5052725.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
- 5056616.pdf: No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) pero no la página de datos de un pasaporte
