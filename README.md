# Passport OCR API

API en FastAPI que extrae los datos de la **página de datos de pasaportes de cualquier país**
(PDF escaneado; fotocopias en blanco y negro con sellos y, a menudo, otros documentos en el mismo
PDF) y devuelve un JSON estructurado con **confianza por campo** y **validaciones**.

Todo corre local y gratis: **PaddleOCR** + **Qwen3-VL 8B** (Ollama). Misma arquitectura que
`OCR-INE-Santander`, cambiando el ancla: aquí manda la **MRZ TD3** (ICAO 9303), que es igual en
todos los países y trae dígitos verificadores.

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

En una GPU de 8 GB sólo cabe un modelo de 8B cargado: por eso en el servidor de pruebas la API
de pasaportes comparte el Ollama del proyecto de INE (mismo `qwen3-vl:8b-instruct`).

## Respuesta de `POST /pasaporte`

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
