# OCR Pasaportes - Open Source

API en FastAPI que extrae los datos de la **página de datos de pasaportes de cualquier país**
(PDF escaneado; fotocopias en blanco y negro con sellos y, a menudo, otros documentos en el mismo
PDF) y devuelve un JSON estructurado con **confianza por campo** y **validaciones**.

Todo corre local y gratis: **PaddleOCR** + **Qwen3-VL 8B** (Ollama). Misma arquitectura que
`OCR-INE-OpenSource`, cambiando el ancla: aquí manda la **MRZ TD3** (ICAO 9303), que es igual en
todos los países y trae dígitos verificadores.

## Plan de atención (validación documental)

`POST /pasaporte` acepta, opcionales en el mismo formulario, los datos capturados en la solicitud:
`nombre` (o `apellido_paterno`, `apellido_materno`, `nombres`), `curp`, `fecha_nacimiento` y
`nacionalidad`. En formato homologado la respuesta agrega `validacion_plan` con las 8 validaciones de la
sección Pasaporte del plan (hoja en blanco, ilegible, es pasaporte, vigente, nombre, CURP, fecha de
nacimiento y nacionalidad), cada una con SI/NO, más `cumple`, `mensaje` y `motivos_rechazo`. Es el mismo
bloque que las APIs de forma migratoria INM. Lógica en [app/plan.py](app/plan.py); vigencia por año
(`REGLA_VIGENCIA=anio`) o por fecha (`fecha`). Si la hoja de datos se leyó distinto, el nombre y la fecha
de nacimiento también se aceptan cuando coinciden con la MRZ íntegra, y la vigencia usa la fecha de
vencimiento de la MRZ íntegra.

## Documentación para quien integra

- **Guía de integración (PDF):** [docs/Documentacion_API_OCR_Pasaporte.pdf](docs/Documentacion_API_OCR_Pasaporte.pdf):
  conexión, petición, estructura de la respuesta, códigos, ejemplos en Python, Node, C# y PHP, seguridad y
  precisión.
- **Prompt para generar el cliente con IA:** [docs/PROMPT_IA.md](docs/PROMPT_IA.md).
- **Swagger:** `http://172.10.30.17:18474/docs`, con los grupos Pasaporte (`POST /pasaporte`), Pruebas
  (`POST /extract`, alias) y Sistema (`GET /health`).

Para regenerar la guía después de un cambio (los ejemplos salen del código real con datos ficticios):

```bash
docker run --rm --entrypoint sh passport-ocr-api:latest -c "python -m scripts.generar_ejemplos /tmp/ej.json >/dev/null 2>&1 && cat /tmp/ej.json" > docs/ejemplos_respuesta.json
python docs/generar_documentacion.py . docs/Documentacion_API_OCR_Pasaporte.pdf
```

El segundo paso necesita `reportlab`.

## Cómo funciona

```
PDF ─► páginas (250 dpi)
    ─► PaddleOCR de la página ─► ubica la MRZ TD3 (2 renglones "P<...") ─► recorte de la página de datos
                               └─ si no la encuentra, prueba girar 90°/180°/270°; después el VLM la ubica
    ─► Qwen3-VL lee el recorte (JSON con esquema fijo: nombres, número, fechas, sexo, CURP, MRZ...)
    ─► MRZ: OCR con dígitos verificadores; si no cuadra, la lectura del VLM (y una 2ª pasada sobre la franja ampliada)
    ─► fusión + validaciones ─► JSON
```

**Fuentes que se cruzan para cada dato**

| Dato | Fuentes |
|---|---|
| Número de pasaporte | MRZ (dígito verificador) vs lectura visual |
| Fecha de nacimiento, vencimiento | MRZ (dígito verificador) vs lectura visual |
| Apellidos, nombres | MRZ (sin verificador) vs lectura visual (conserva Ñ y acentos) |
| Sexo, nacionalidad, país emisor | MRZ vs lectura visual |
| CURP (México) | estructura + dígito verificador + fecha/sexo de la MRZ |
| Lugar de nacimiento, expedición, autoridad | sólo lectura visual (expedición < vencimiento) |

**Confianza**: `alta` = dos fuentes coinciden o lo respalda un dígito verificador · `media` = una
fuente con estructura válida · `baja` = desacuerdo o ilegible. `estado = "revisar"` si un campo
crítico queda en `baja` o la MRZ no es íntegra.

Los otros documentos del PDF (p. ej. la tarjeta de residente del INM, que trae una MRZ TD1
`I<MEX...`) se detectan y se reportan en `meta.otros_documentos`, pero no se extraen.

## Uso

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --port 8000
curl -X POST localhost:8000/pasaporte -F "file=@pasaporte.pdf;type=application/pdf"
```

**Lote** (reanudable; `--modelo` para comparar VLMs):

```bash
python -m scripts.procesar_lote lote/pdfs --salida lote/resultados --concurrencia 2 --recortes
python -m scripts.procesar_lote lote/pdfs --salida lote/res_glm --modelo glm-ocr --formato plantilla
python -m scripts.comparar_lotes lote/resultados/resultados.csv lote/res_glm/resultados.csv
```

Genera `json/*.json`, `resultados.csv` (datos completos; no sacar del servidor), `diagnostico.csv`
(sin datos personales) y `resumen.md`.

**Pruebas**: `python -m pytest -q`

## Servidor (Docker)

```bash
cp .env.example .env
# a) Ollama propio (GPU):            docker compose --profile ollama up -d --build
# b) compartir el Ollama de ine-ocr: VLM_BASE_URL=http://ollama:11434, OLLAMA_NETWORK=ine-ocr_default,
#    OLLAMA_NETWORK_EXTERNAL=true en .env y:   docker compose up -d --build
docker compose run --rm lote lote/pdfs --salida lote/resultados --concurrencia 2
```

**API key**: con `API_KEY` definida en `.env` (así está en el servidor), `POST /pasaporte` exige el header
`X-API-Key`; sin él o con otro valor responde `401 NO_AUTORIZADO`. `/health` no la pide. En `/docs`, el
botón Authorize la captura una vez para todas las llamadas.

En una GPU de 8 GB sólo cabe un modelo de 8B cargado: por eso en el servidor de pruebas la API
de pasaportes comparte el Ollama del proyecto de INE (mismo `qwen3-vl:8b-instruct`).

## Formato homologado (respaldo de la API de referencia)

Con `FORMATO_RESPUESTA=homologado`, `POST /pasaporte` responde con el contrato de la API de referencia
(`santander_ia`), definido en [docs/HOMOLOGACION_PASAPORTE.md](docs/HOMOLOGACION_PASAPORTE.md): mismas
llaves (`datos`, `sello`, `mrz`, `validacion`, `avisos`, `clasificacion`), mismos códigos (225 = no es
pasaporte) y mismas etiquetas de validación. Así se puede usar como respaldo cambiando sólo el dominio.

- El motor no cambia: [app/homologado.py](app/homologado.py) sólo traduce el resultado interno.
- En modo homologado se agregan dos lecturas cortas del VLM: el sexo tal como está impreso (~1.3 s)
  y el sello de cotejo, que se ubica con el OCR (~2 s). La lectura principal no se toca.
- `MRZ_MANDA=false` (default) sigue la regla de la referencia; `true` conserva la regla de este servicio.
- Verificación: `python -m scripts.validar_respuestas <carpeta>` corre el validador del contrato;
  `python -m scripts.procesar_lote ... --homologado` guarda las respuestas en `respuestas/`, y
  `python -m scripts.rehacer_respuestas <lote>` las vuelve a armar sin repetir OCR ni VLM.
- Resultados y dudas abiertas: [docs/HOMOLOGACION_REPORTE.md](docs/HOMOLOGACION_REPORTE.md).

## Respuesta de `POST /pasaporte` (formato propio)

Mismo sobre que la API de INE: `codigo` / `estado` / `mensaje` + `pasaporte`, `mrz`, `validacion`,
`avisos`, `confianza`, `meta`.

| `codigo` | `estado` |
|---:|---|
| 200 | `PROCESADO` |
| 210 | `PROCESADO_CON_DISCREPANCIAS` (ver `validacion.discrepancias`) |
| 211 | `PROCESADO_CON_AVISOS` (ver `avisos`) |
| 212 | `PROCESADO_INCOMPLETO` (ver `validacion.sin_verificar`) |
| 220 | `NO_ES_PASAPORTE` · 221 `HOJA_EN_BLANCO` · 222 `ARCHIVO_CORRUPTO` · 223 `PDF_PROTEGIDO` · 224 `LIMITE_PAGINAS` |
| 400 / 401 / 413 / 422 / 500 | archivo no soportado / sin API key / muy grande / petición inválida / error |

```json
{
  "codigo": 200, "estado": "PROCESADO", "mensaje": "...",
  "pasaporte": {
    "tipo_documento": "P", "pais_emisor": "MEX", "pais_emisor_nombre": "MEXICO",
    "numero_pasaporte": "G12345678", "apellidos": "GARCÍA LÓPEZ", "nombres": "JUAN CARLOS",
    "nacionalidad": "MEX", "fecha_nacimiento": "1985-03-12", "sexo": "M",
    "lugar_nacimiento": "JALISCO, MEX", "fecha_expedicion": "2020-12-31", "fecha_vencimiento": "2030-12-31",
    "vigente": true, "autoridad": "SRE", "curp": "GALJ850312HJCRPN09"
  },
  "mrz": {"lineas": ["P<MEXGARCIA<LOPEZ<<JUAN<CARLOS<<<<<<<<<<<<<<", "G12345678<4MEX8503129M3012317<<<<<<<<<<<<<<02"],
          "digitos_control": {"numero": true, "fecha_nacimiento": true, "vencimiento": true, "compuesto": true},
          "integra": true, "origen": "ocr"},
  "validacion": {"ok": true, "completo": true, "coincidencias": ["mrz_numero", "numero_pasaporte_mrz_vs_impreso", "..."],
                 "discrepancias": [], "sin_verificar": []},
  "avisos": [], "confianza": {"numero_pasaporte": "alta", "apellidos": "alta", "...": "..."},
  "meta": {"tiempo_total_ms": 9000, "pagina_pasaporte": 1, "recorte": "ancla", "mrz_fuente": "ocr",
           "otros_documentos": ["tarjeta_td1"]}
}
```

## Privacidad

Los pasaportes son datos personales. Todo se procesa localmente; los logs sólo registran estado y
tiempos. `lote/`, `samples/`, `resultados/` y `*.pdf` están en `.gitignore`.
