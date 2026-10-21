# Homologación de `POST /pasaporte`

> **Para el agente que va a implementar estos cambios.** Léelo completo antes de tocar código.
> El objetivo es que tu API de pasaportes (`OCR-Pasaporte-Santander`) entregue **el mismo JSON
> que la API de referencia** (`santander_ia`) para el mismo documento, sin importar cómo lo
> obtengas. La referencia manda; tu sistema se ajusta a ella.

## 0. Reglas de trabajo

1. **Este documento manda sobre tu README.** Donde difieran, gana este.
2. **No inventes.** Si un caso no está cubierto aquí, no lo resuelvas por tu cuenta: déjalo como
   está y anótalo en una sección «Dudas» de tu reporte final. La sección 9 lista lo que la
   referencia todavía no cubre.
3. **Cambia la salida, no el motor.** PaddleOCR, el VLM, el recorte por ancla, la reparación de la
   MRZ y de la CURP con dígitos verificadores, y la detección de otros documentos en el PDF
   **se quedan**. Lo que cambia es la forma de la respuesta y, en un caso (sección 8), una regla de
   decisión.
4. **Verifica con el validador de la sección 10** sobre al menos 20 documentos de tu lote. Debe dar
   **0 ERROR** en todos.
5. **Sin datos personales** en tests, commits ni logs. Usa datos ficticios.

## 1. Resultado esperado

Respuesta de la referencia para un pasaporte mexicano con sello de cotejo. **Datos ficticios**;
se generó ejecutando el código de la referencia, así que es exactamente lo que ella devolvería.

```json
{
  "codigo": 200,
  "estado": "PROCESADO",
  "mensaje": "El documento se procesó y todas las comprobaciones cuadraron.",
  "datos": {
    "tipo_documento": "P",
    "pais_emisor": "MEX",
    "numero_pasaporte": "G12345678",
    "apellido_paterno": "TORRES",
    "apellido_materno": "VEGA",
    "nombres": "ANA LUCIA",
    "nacionalidad": "MEX",
    "fecha_nacimiento": "1992-07-08",
    "lugar_nacimiento": "CIUDAD DE MEXICO",
    "sexo": "F",
    "curp": "TOVA920708MDFRGN02",
    "fecha_expedicion": "2020-02-14",
    "fecha_vencimiento": "2030-02-13",
    "autoridad_expedidora": "SRE"
  },
  "sello": {
    "fecha": "2026-01-15",
    "reviso": "Jorge Luis Medina Ortiz",
    "clave_revisor": "S318204"
  },
  "mrz": {
    "lineas": [
      "P<MEXTORRES<VEGA<<ANA<LUCIA<<<<<<<<<<<<<<<<<",
      "G123456786MEX9207086F3002131TOVA920708MDFR78"
    ],
    "tipo_documento": "P",
    "pais_emisor": "MEX",
    "numero_pasaporte": "G12345678",
    "nacionalidad": "MEX",
    "numero_personal": "TOVA920708MDFR",
    "fecha_nacimiento": "1992-07-08",
    "sexo": "F",
    "fecha_vencimiento": "2030-02-13",
    "apellido_paterno": "TORRES",
    "apellido_materno": "VEGA",
    "nombres": "ANA LUCIA",
    "nombre_abreviado": false,
    "digitos_control": {
      "numero_pasaporte": true,
      "fecha_nacimiento": true,
      "fecha_vencimiento": true,
      "numero_personal": true,
      "compuesto": true
    },
    "integra": true,
    "origen": "entidad"
  },
  "validacion": {
    "ok": true,
    "completo": true,
    "coincidencias": [
      "MRZ (dígitos de control)",
      "numero_pasaporte (MRZ)",
      "fecha_nacimiento (MRZ)",
      "sexo (MRZ)",
      "fecha_vencimiento (MRZ)",
      "nacionalidad (MRZ)",
      "apellido_paterno (MRZ)",
      "apellido_materno (MRZ)",
      "nombres (MRZ)",
      "curp vs número personal (MRZ)",
      "fecha_nacimiento (CURP)",
      "sexo (CURP)"
    ],
    "discrepancias": [],
    "sin_verificar": []
  },
  "avisos": [],
  "clasificacion": {
    "categoria": "pasaporte",
    "confianza": 0.9998,
    "caracteres_leidos": 412
  }
}
```

- Las llaves de primer nivel de una respuesta **procesada** (códigos 200, 210, 211 y 212) son
  siempre esas nueve y en ese orden. Puedes agregar extensiones (sección 7), nunca quitar ni
  renombrar estas.
- `sello` va siempre, aunque sea `{}`. `mrz` va siempre, aunque sea `{}` cuando no se encontró.

## 2. Lista de cambios

| # | Cambio | Sección |
|--:|---|:-:|
| 1 | El código para «no es pasaporte» es **225**, no 220. Agregar el sobre de errores común | 3 |
| 2 | Renombrar `pasaporte` → `datos` y ajustar sus campos | 4 |
| 3 | Separar `apellidos` en `apellido_paterno` y `apellido_materno` | 4 |
| 4 | `datos.sexo` se entrega **sin traducir** | 4 |
| 5 | **Agregar `sello`** (no existe hoy) | 5 |
| 6 | Renombrar campos de `mrz` y completar sus cinco dígitos de control | 6 |
| 7 | `validacion`: listas de **cadenas** (no objetos) con las etiquetas de la referencia | 7 |
| 8 | `avisos`: quitar los que no son de la referencia | 7 |
| 9 | Agregar `clasificacion` | 7 |
| 10 | Reglas de valores: sin vacíos, fechas ISO, texto limpio | 4 |

## 3. Sobre y códigos

`codigo` y `estado` son el contrato y nunca cambian de significado. `mensaje` es texto para
humanos y **no se compara**: puedes escribir el tuyo.

| `codigo` | `estado` | HTTP | `mensaje` de referencia |
|---:|---|---:|---|
| 200 | `PROCESADO` | 200 | El documento se procesó y todas las comprobaciones cuadraron. |
| 210 | `PROCESADO_CON_DISCREPANCIAS` | 200 | El documento se procesó, pero hay datos que se contradicen entre sí. Revisa 'validacion.discrepancias' antes de dar los datos por buenos. |
| 211 | `PROCESADO_CON_AVISOS` | 200 | El documento se procesó y nada se contradijo, pero hay algo que requiere revisión humana. Revisa 'avisos'. |
| 212 | `PROCESADO_INCOMPLETO` | 200 | El documento se procesó y nada se contradijo, pero quedaron comprobaciones sin poder realizarse. Revisa 'validacion.sin_verificar'. |
| 221 | `HOJA_EN_BLANCO` | 200 | El documento viene en blanco o ilegible: no se leyó ningún texto. |
| 222 | `ARCHIVO_CORRUPTO` | 200 | El archivo no se pudo abrir: está dañado, incompleto, o no es del tipo que dice ser. |
| 223 | `PDF_PROTEGIDO` | 200 | El PDF está protegido con contraseña. Quítasela y vuelve a enviarlo. |
| 224 | `LIMITE_PAGINAS` | 200 | El documento tiene más páginas de las que se pueden procesar en una sola llamada. Envía solo las páginas de la credencial. |
| 225 | `NO_ES_PASAPORTE` | 200 | El documento no es un pasaporte. No se extrajo ningun dato. |
| 400 | `ARCHIVO_NO_SOPORTADO` | 400 | El tipo de archivo enviado no se acepta. |
| 422 | `PETICION_INVALIDA` | 422 | La petición no es válida. Se espera multipart/form-data con un campo 'file'. |
| 429 | `CUOTA_EXCEDIDA` | 429 | Se alcanzó el límite de páginas por minuto del servicio de OCR. Espera un momento y vuelve a intentar. |
| 500 | `ERROR_INTERNO` | 500 | Error interno de la API. |
| 502 | `ERROR_DOCUMENT_AI` | 502 | El servicio de Document AI falló o respondió algo no interpretable. |
| 503 | `SIN_CREDENCIALES` | 503 | El servidor no pudo obtener las credenciales de Google Cloud. |

Reglas:

- Todo el grupo `2xx` responde **HTTP 200**. Las fallas (`4xx`, `5xx`) usan como HTTP el mismo número
  que `codigo`.
- **`220` NO se usa en `/pasaporte`.** Es `NO_ES_INE`, del endpoint de INE. Tu `NO_ES_PASAPORTE` hoy
  usa 220: cámbialo a **225**. Así, quien consuma las dos APIs lee `220` como «esto no es una INE»
  y `225` como «esto no es un pasaporte».
- Tus códigos `401`, `404`, `405` y `413` no existen en la referencia. Puedes conservarlos como
  extensiones de tu servicio.
- Una respuesta que no es procesada (221, 222, 223, 224, 225, 4xx, 5xx) trae solo `codigo`,
  `estado` y `mensaje`. **225 y 221 traen además `clasificacion`.** El `422` trae también `errores`.

**Cómo se decide el código de una respuesta procesada**, en este orden:

1. Hay alguna `discrepancia` → **210**
2. Si no, hay algún `aviso` → **211**
3. Si no, `completo` es `false` → **212**
4. Si no → **200**

`ok` es `true` cuando no hay discrepancias. `completo` es `true` cuando no hay `sin_verificar`.

## 4. `datos`

Renombra `pasaporte` → `datos` y ajusta estos campos:

| Tu campo | Campo de la referencia |
|---|---|
| `tipo_documento` | igual |
| `pais_emisor` | igual (código ICAO de 3 letras) |
| `numero_pasaporte` | igual |
| `apellidos` | **`apellido_paterno`** y **`apellido_materno`** (ver abajo) |
| `nombres` | igual |
| `nacionalidad` | igual |
| `fecha_nacimiento` | igual (ISO `AAAA-MM-DD`) |
| `lugar_nacimiento` | igual |
| `sexo` | igual de nombre, **distinto de valor** (ver abajo) |
| `curp` | igual (solo pasaportes mexicanos) |
| `fecha_expedicion` | igual (ISO) |
| `fecha_vencimiento` | igual (ISO) |
| `autoridad` | **`autoridad_expedidora`** |
| `nombre_completo`, `pais_emisor_nombre`, `nacionalidad_impresa`, `vigente` | extensiones tuyas, permitidas |

**Apellidos (regla provisional).** La referencia tiene dos campos y tú una cadena. Mientras no se
decida otra cosa, aplica **la misma regla que la MRZ**: la primera palabra va a
`apellido_paterno` y las demás, unidas con espacio, a `apellido_materno`. Si `apellidos` trae una
sola palabra, no escribas `apellido_materno`. Es una simplificación conocida (sección 9).

**Sexo.** `datos.sexo` es **lo que dice la hoja de datos, sin traducir**. Tú hoy lo conviertes al
código de la MRZ; deja esa conversión solo para comparar internamente. Hay una trampa: la letra `M`
significa *male* en el estándar internacional y *mujer* en español. En la MRZ (`mrz.sexo`) siempre
es el código internacional `M` / `F` / `X`.

**Reglas de valores** (aplican a `datos`, `sello` y `mrz`):

- **Una llave sin dato se omite.** Nunca `""` ni `null`.
- Fechas en ISO `AAAA-MM-DD`.
- Texto como viene impreso, sin saltos de línea y sin basura pegada a los bordes (`-`, `,`, `:`).
- Conserva acentos y `Ñ` en `datos`: es lo impreso. La MRZ no los tiene; ver sección 7.

## 5. `sello`: agregar

Los PDFs de pasaporte a veces traen el sello de cotejo de Santander («COTEJADO CONTRA ORIGINAL»,
con FECHA, REVISO y clave del revisor). Hoy no lo lees. Pídele al VLM que lo lea y entrégalo así:

| Campo | Regla |
|---|---|
| `fecha` | ISO `AAAA-MM-DD`. Si lo leído no se puede interpretar como fecha real, **omite el campo** y agrega el aviso `sello.fecha ilegible: se leyó '...'` |
| `reviso` | Nombre de quien revisó, tal como se lee |
| `clave_revisor` | Una letra + 5 a 7 dígitos (`S318204`). El OCR confunde la `S` inicial con `$` o `5`: corrígela. Si no tiene esa forma, **omite el campo** y agrega el aviso `sello.clave_revisor sin forma de clave: se leyó '...'` |

**El sello es opcional en el pasaporte** (a diferencia de la INE):

- Si el PDF **no trae sello**, `sello` es `{}` y **no se agrega nada a `sin_verificar`**. Su ausencia
  total no es una falta.
- Si el sello apareció **a medias**, por cada campo que falta agrega a `sin_verificar` la cadena
  `sello.fecha (ausente)`, `sello.reviso (ausente)` o `sello.clave_revisor (ausente)`.

## 6. `mrz`

| Tu campo | Campo de la referencia |
|---|---|
| `lineas` | igual: lista de **2** renglones de **44** caracteres |
| `tipo_documento`, `pais_emisor`, `nacionalidad` | igual |
| `numero` | **`numero_pasaporte`** |
| `fecha_nacimiento`, `fecha_vencimiento` | igual (ISO) |
| `sexo` | igual: `M` / `F` / `X` |
| `apellidos` | **`apellido_paterno`** (primera palabra) y **`apellido_materno`** (las demás; omítelo si hay una sola) |
| `nombres` | igual (palabras unidas con espacio) |
| `opcional` | **`numero_personal`** (**omítelo si está vacío**) |
| `digitos_control` | ver abajo |
| `integra` | ver abajo |
| `origen` | `ocr` → **`texto`**; `vlm` → **`entidad`** |
| (no existe) | **`nombre_abreviado`**: booleano, **siempre presente**. `true` si el renglón 1 no termina en `<` (el nombre llenó los 44 caracteres y vino abreviado) |

**`digitos_control`** lleva **siempre las cinco llaves**, todas booleanas:
`numero_pasaporte`, `fecha_nacimiento`, `fecha_vencimiento`, `numero_personal`, `compuesto`.
`numero_personal` es `true` también cuando el campo va vacío y su dígito es `0` o `<`.

**`integra`** es `true` **solo si los cinco cuadran**. Tu versión exige cuatro; la referencia es
más estricta.

La reparación que haces al **leer** la MRZ (tipado por posición, una sustitución confusable
validada con el dígito verificador) es válida y se queda: el contrato solo pide el resultado.

## 7. `validacion`, `avisos` y `clasificacion`

### Forma

`validacion` tiene exactamente estas cinco llaves: `ok`, `completo`, `coincidencias`,
`discrepancias`, `sin_verificar`. Las tres listas son **listas de cadenas**. Tus `discrepancias`
hoy son objetos `{regla, detalle}`: conviértelas a cadenas.

### Qué escribir en cada lista

Cuando la MRZ es íntegra, escribe **una** coincidencia `MRZ (dígitos de control)` y compara la hoja
contra ella con las reglas de abajo. Cuando **no** es íntegra:

- `discrepancias` ← `MRZ corrupta: fallan los dígitos de control de A, B; no se pudo contrastar la hoja de datos contra el reverso` (A, B = las llaves de `digitos_control` en `false`)
- `sin_verificar` ← `todas las comprobaciones contra la MRZ`
- **No agregues** además el aviso «La MRZ no cuadró...» que hoy generas: la MRZ corrupta ya es una discrepancia.

Si no se encontró ninguna MRZ, `sin_verificar` ← `MRZ completa (no se extrajo)`.

Etiquetas de comparación contra la MRZ (se comparan en mayúsculas):

| Etiqueta | Compara |
|---|---|
| `numero_pasaporte (MRZ)` | `datos.numero_pasaporte` con `mrz.numero_pasaporte` |
| `fecha_nacimiento (MRZ)` | las fechas ISO |
| `sexo (MRZ)` | el sexo impreso (traducido, ver abajo) con `mrz.sexo` |
| `fecha_vencimiento (MRZ)` | las fechas ISO |
| `nacionalidad (MRZ)` | `datos.nacionalidad` con `mrz.nacionalidad` |
| `apellido_paterno (MRZ)` | solo **si alguna de las dos fuentes lo trae** |
| `apellido_materno (MRZ)` | solo **si alguna de las dos fuentes lo trae** (un pasaporte de un solo apellido no lo compara y **no** va a `sin_verificar`) |
| `nombres (MRZ)` | `datos.nombres` con `mrz.nombres` |

- Una comparación que coincide → su etiqueta en `coincidencias`.
- Una que difiere → `discrepancias`: `{etiqueta}: hoja de datos '{valor de datos}' vs '{valor de la MRZ}'`.
- Si falta el valor de **alguno de los dos lados** → la etiqueta en `sin_verificar` (excepto
  `apellido_materno`, ver arriba).
- **Nombres:** se comparan **sin acentos y con `Ñ` = `N`**, porque la MRZ no puede llevarlos
  (`GARCÍA` contra `GARCIA` coincide). `datos` conserva lo impreso.
- **Nombre abreviado:** si `mrz.nombre_abreviado` es `true`, que el valor de la MRZ sea prefijo
  del de la hoja cuenta como coincidencia, con la etiqueta terminada en ` (abreviado en la MRZ)`.
- **Sexo:** `H`, `HOMBRE`, `MALE`, `MASCULINO` → `M`; `F`, `FEMALE`, `MUJER`, `FEMENINO` → `F`;
  `X` → `X`. La `M` suelta es *male* en cualquier país **excepto México**; en un pasaporte
  mexicano es ambigua y **se calla** (ni coincidencia, ni discrepancia, ni `sin_verificar`).

Contra la CURP (solo si `datos.curp` tiene estructura de CURP; si no, `sin_verificar` ←
`CURP (formato inválido: '...')`):

| Etiqueta | Compara |
|---|---|
| `fecha_nacimiento (CURP)` | `datos.fecha_nacimiento` con la fecha de las posiciones 5 a 10 de la CURP |
| `sexo (CURP)` | el sexo impreso con la posición 11 de la CURP (`H` = `M`, `M` = `F`) |
| `curp vs número personal (MRZ)` | `datos.curp` y `mrz.numero_personal`: coincide si una empieza con la otra. Si no: `curp: '{curp}' no corresponde al número personal de la MRZ '{numero_personal}'` |

**Tus comprobaciones sin equivalente** (`pais_emisor_mrz_vs_impreso`,
`fecha_expedicion_antes_de_vencimiento`, el dígito verificador de la CURP) **no van en estas tres
listas** ni afectan el código. Si quieres conservarlas, devuélvelas dentro de
`meta.validaciones_extra`.

### `avisos`

Lista de cadenas, **vacía en el caso normal**. Solo estos tipos:

- `sello.fecha ilegible: se leyó '...'` y `sello.clave_revisor sin forma de clave: se leyó '...'`
- si corriges un dato (por ejemplo una CURP reparada), un aviso que diga qué leíste y en qué se
  convirtió: `datos.curp corregida con la MRZ y el dígito verificador: se leyó 'X' y quedó 'Y'`
- el PDF trae más de un pasaporte: `el PDF contiene N bloques '...': se conservó el primero,
  revisa que el documento no traiga más de una identidad`

**Quita** los avisos `campo con confianza baja: ...` y `La MRZ no cuadró por completo...`: no son de
la referencia y cada aviso convierte un `200` en `211`. Tu `confianza` por campo puede seguir
existiendo como extensión.

### `clasificacion`

```json
"clasificacion": { "categoria": "pasaporte", "confianza": null, "caracteres_leidos": 412 }
```

`categoria` es `pasaporte`, `otro` o `hoja_en_blanco`. `confianza` es un número de 0 a 1 o `null`
(si tu clasificador es por reglas, `null` es aceptable). `caracteres_leidos` es entero. Tu
`meta.categoria` y `meta.caracteres_leidos` alimentan esto.

### Extensiones permitidas

Estas llaves **no son parte del contrato**; puedes conservarlas y nadie debe depender de ellas:
`id`, `confianza` (por campo), `meta`, `recortes`, `datos.nombre_completo`,
`datos.pais_emisor_nombre`, `datos.nacionalidad_impresa`, `datos.vigente`.

## 8. Una regla de decisión que cambia

Hoy, cuando la lectura impresa y la MRZ difieren y el dígito verificador respalda a la MRZ, **tomas
el valor de la MRZ** y dejas un aviso. Es una buena idea y puede que la referencia la adopte, pero
**hoy la referencia no lo hace**:

- `datos.<campo>` conserva **la lectura impresa**.
- La diferencia se reporta como **discrepancia** (`210`), no como aviso (`211`).

Hasta que este documento diga otra cosa, **sigue la referencia**. Si ya tienes la lógica de «la MRZ
manda», déjala escrita pero desactivada detrás de una variable de configuración.

## 9. Lo que la referencia todavía no cubre

Para estos puntos **no resuelvas por tu cuenta** ni asumas que la referencia hace algo concreto:

1. **Apellidos.** Separar en paterno y materno no es natural en pasaportes de países con un solo
   apellido o con apellidos compuestos (`VAN DER BERG`). La regla de la sección 4 es provisional.
2. **Apellidos compuestos en pasaporte.** La referencia ya los compara por palabras en la INE, pero
   en el pasaporte compara campo por campo, así que `DE LA CRUZ` / `PEREZ` puede dar discrepancias
   falsas. Si tu sistema las evita, no repliques el defecto.
3. **Dígito verificador de la CURP.** La referencia lo valida en la INE (`curp (dígito verificador)`)
   pero **todavía no en el pasaporte**. No lo agregues a `coincidencias` con otra etiqueta.
4. **`M` en pasaportes mexicanos.** No se sabe qué convención imprimen; por eso se calla.
5. **La regla de la sección 8.**

## 10. Validador y aceptación

Guarda esto como `validador_pasaporte.py`. Recibe un JSON de respuesta y lista lo que no cumple el
contrato. **ERROR** = hay que corregirlo; **AVISO** = una extensión tuya.

```bash
python validador_pasaporte.py respuesta.json
```

```python
"""Revisa que una respuesta de POST /pasaporte cumpla el contrato de la referencia.

Uso:   python validador_pasaporte.py respuesta.json
Salida: ERROR = hay que corregirlo para homologar; AVISO = extension tuya o dato a confirmar.
Codigo de salida: 0 si no hay ERROR, 1 si los hay.
"""
import json
import re
import sys

CODIGOS = {
    200: "PROCESADO", 210: "PROCESADO_CON_DISCREPANCIAS", 211: "PROCESADO_CON_AVISOS",
    212: "PROCESADO_INCOMPLETO", 221: "HOJA_EN_BLANCO", 222: "ARCHIVO_CORRUPTO", 223: "PDF_PROTEGIDO",
    224: "LIMITE_PAGINAS", 225: "NO_ES_PASAPORTE", 400: "ARCHIVO_NO_SOPORTADO", 422: "PETICION_INVALIDA",
    429: "CUOTA_EXCEDIDA", 500: "ERROR_INTERNO", 502: "ERROR_DOCUMENT_AI", 503: "SIN_CREDENCIALES",
}
PROCESADOS = (200, 210, 211, 212)
PRIMER_NIVEL = ["codigo", "estado", "mensaje", "datos", "sello", "mrz", "validacion", "avisos", "clasificacion"]
DATOS = {"tipo_documento", "pais_emisor", "numero_pasaporte", "apellido_paterno", "apellido_materno", "nombres",
         "nacionalidad", "fecha_nacimiento", "lugar_nacimiento", "sexo", "curp", "fecha_expedicion",
         "fecha_vencimiento", "autoridad_expedidora"}
DATOS_EXTENSION = {"nombre_completo", "pais_emisor_nombre", "nacionalidad_impresa", "vigente"}
RENOMBRADOS = {"apellidos": "apellido_paterno / apellido_materno", "autoridad": "autoridad_expedidora"}
MRZ = {"lineas", "tipo_documento", "pais_emisor", "numero_pasaporte", "nacionalidad", "numero_personal",
       "fecha_nacimiento", "sexo", "fecha_vencimiento", "apellido_paterno", "apellido_materno", "nombres",
       "nombre_abreviado", "digitos_control", "integra", "origen"}
MRZ_RENOMBRADOS = {"numero": "numero_pasaporte", "opcional": "numero_personal", "apellidos": "apellido_paterno / apellido_materno"}
DIGITOS = {"numero_pasaporte", "fecha_nacimiento", "fecha_vencimiento", "numero_personal", "compuesto"}
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CAMPOS_MRZ = r"(numero_pasaporte|fecha_nacimiento|sexo|fecha_vencimiento|nacionalidad|apellido_paterno|apellido_materno|nombres) \(MRZ\)"
CAMPOS_CURP = r"(fecha_nacimiento|sexo) \(CURP\)"
RE_COINCIDENCIA = re.compile(r"^(MRZ \(dígitos de control\)|" + CAMPOS_MRZ + r"( \(abreviado en la MRZ\))?|"
                             r"curp vs número personal \(MRZ\)|" + CAMPOS_CURP + r")$")
RE_DISCREPANCIA = re.compile(r"^((" + CAMPOS_MRZ + r")|(" + CAMPOS_CURP + r")): hoja de datos '.*' vs '.*'$|"
                             r"^MRZ corrupta: fallan los dígitos de control de .+; no se pudo contrastar la hoja de datos contra el reverso$|"
                             r"^curp: '.*' no corresponde al número personal de la MRZ '.*'$")
RE_SIN_VERIFICAR = re.compile(r"^(" + CAMPOS_MRZ + r"|" + CAMPOS_CURP + r"|MRZ completa \(.+\)|"
                              r"todas las comprobaciones contra la MRZ|CURP \(formato inválido: '.*'\)|"
                              r"sello\.(fecha|reviso|clave_revisor) \(ausente\))$")


def revisar(r):
    err, av = [], []
    if not isinstance(r, dict):
        return ["la respuesta no es un objeto JSON"], av
    cod, estado = r.get("codigo"), r.get("estado")
    if cod == 220:
        err.append("codigo 220 es NO_ES_INE (del endpoint /ine). Para /pasaporte el codigo es 225 NO_ES_PASAPORTE")
    elif cod not in CODIGOS:
        err.append("codigo %r no existe en la tabla de desenlaces" % (cod,))
    elif CODIGOS[cod] != estado:
        err.append("codigo %s debe llevar estado %s, trae %r" % (cod, CODIGOS[cod], estado))
    if not isinstance(r.get("mensaje"), str) or not r.get("mensaje"):
        err.append("mensaje debe ser texto no vacio")

    if cod not in PROCESADOS:
        permitidas = {"codigo", "estado", "mensaje"} | ({"clasificacion"} if cod in (221, 225) else set())
        for k in r:
            if k not in permitidas:
                av.append("respuesta de %s trae la llave extra %r (la referencia solo trae %s)"
                          % (cod, k, sorted(permitidas)))
        return err, av

    faltan = [k for k in PRIMER_NIVEL if k not in r]
    if faltan:
        err.append("faltan llaves de primer nivel: %s" % faltan)
    for k in r:
        if k not in PRIMER_NIVEL:
            av.append("llave de primer nivel extra %r: es una extension, no parte del contrato" % k)
    if "pasaporte" in r:
        err.append("la llave 'pasaporte' debe llamarse 'datos'")

    def sin_vacios(nombre, d):
        for k, v in (d or {}).items():
            if v is None or v == "":
                err.append("%s.%s esta vacio: una llave sin dato se OMITE" % (nombre, k))

    # Si todavia se llama 'pasaporte', se revisan igual sus campos para listar todos
    # los cambios de una vez.
    datos, sello, mrz = r.get("datos") or r.get("pasaporte") or {}, r.get("sello") or {}, r.get("mrz") or {}
    for nombre, d in (("datos", datos), ("sello", sello), ("mrz", mrz)):
        sin_vacios(nombre, d)

    for k in datos:
        if k in RENOMBRADOS:
            err.append("datos.%s debe llamarse %s" % (k, RENOMBRADOS[k]))
        elif k not in DATOS:
            (av if k in DATOS_EXTENSION else err).append(
                "datos.%s %s" % (k, "es una extension permitida" if k in DATOS_EXTENSION else "no existe en el contrato"))
    for k in ("fecha_nacimiento", "fecha_expedicion", "fecha_vencimiento"):
        if k in datos and not ISO.match(str(datos[k])):
            err.append("datos.%s debe ser ISO AAAA-MM-DD, trae %r" % (k, datos[k]))
    for k in sello:
        if k not in ("fecha", "reviso", "clave_revisor"):
            err.append("sello.%s no existe en el contrato" % k)
    if "fecha" in sello and not ISO.match(str(sello["fecha"])):
        err.append("sello.fecha debe ser ISO, trae %r" % sello["fecha"])
    if "clave_revisor" in sello and not re.match(r"^[A-Z]\d{5,7}$", str(sello["clave_revisor"])):
        err.append("sello.clave_revisor debe ser una letra + 5 a 7 digitos, trae %r" % sello["clave_revisor"])

    if mrz:
        for k in mrz:
            if k in MRZ_RENOMBRADOS:
                err.append("mrz.%s debe llamarse %s" % (k, MRZ_RENOMBRADOS[k]))
            elif k not in MRZ:
                err.append("mrz.%s no existe en el contrato" % k)
        lineas = mrz.get("lineas")
        if not (isinstance(lineas, list) and len(lineas) == 2 and all(isinstance(x, str) and len(x) == 44 for x in lineas)):
            err.append("mrz.lineas debe ser una lista de 2 renglones de 44 caracteres")
        dc = mrz.get("digitos_control")
        if not isinstance(dc, dict) or set(dc) != DIGITOS:
            err.append("mrz.digitos_control debe tener exactamente las llaves %s" % sorted(DIGITOS))
        elif mrz.get("integra") != all(dc.values()):
            err.append("mrz.integra debe ser true solo si los CINCO digitos de control cuadran")
        if mrz.get("origen") not in ("entidad", "texto"):
            err.append("mrz.origen debe ser 'entidad' o 'texto', trae %r" % mrz.get("origen"))
        if not isinstance(mrz.get("nombre_abreviado"), bool):
            err.append("mrz.nombre_abreviado debe estar siempre presente y ser booleano")
        for k in ("fecha_nacimiento", "fecha_vencimiento"):
            if k in mrz and not ISO.match(str(mrz[k])):
                err.append("mrz.%s debe ser ISO, trae %r" % (k, mrz[k]))
        if mrz.get("sexo") not in (None, "M", "F", "X"):
            err.append("mrz.sexo debe ser M, F o X (codigo internacional)")

    v = r.get("validacion") or {}
    if set(v) != {"ok", "completo", "coincidencias", "discrepancias", "sin_verificar"}:
        err.append("validacion debe tener exactamente: ok, completo, coincidencias, discrepancias, sin_verificar")
    else:
        for lista, rx in (("coincidencias", RE_COINCIDENCIA), ("discrepancias", RE_DISCREPANCIA),
                          ("sin_verificar", RE_SIN_VERIFICAR)):
            for x in v[lista]:
                if not isinstance(x, str):
                    err.append("validacion.%s debe ser lista de CADENAS, trae %r" % (lista, x))
                elif not rx.match(x):
                    err.append("validacion.%s: %r no es una etiqueta/formato del contrato" % (lista, x))
        if v["ok"] != (not v["discrepancias"]):
            err.append("validacion.ok debe ser true si y solo si no hay discrepancias")
        if v["completo"] != (not v["sin_verificar"]):
            err.append("validacion.completo debe ser true si y solo si no hay sin_verificar")
    if not isinstance(r.get("avisos"), list) or not all(isinstance(x, str) for x in r.get("avisos") or []):
        err.append("avisos debe ser una lista de cadenas")

    c = r.get("clasificacion") or {}
    if c.get("categoria") != "pasaporte":
        err.append("clasificacion.categoria debe ser 'pasaporte' cuando se procesa, trae %r" % c.get("categoria"))
    if c.get("confianza") is not None and not isinstance(c.get("confianza"), (int, float)):
        err.append("clasificacion.confianza debe ser numero de 0 a 1 o null")
    if not isinstance(c.get("caracteres_leidos"), int):
        err.append("clasificacion.caracteres_leidos debe ser un entero")

    disc, sv, avisos = v.get("discrepancias") or [], v.get("sin_verificar") or [], r.get("avisos") or []
    esperado = 210 if disc else 211 if avisos else 212 if sv else 200
    if cod != esperado:
        err.append("por su contenido el codigo debe ser %d (discrepancias=%d, avisos=%d, sin_verificar=%d) y trae %s"
                   % (esperado, len(disc), len(avisos), len(sv), cod))
    return err, av


if __name__ == "__main__":
    errores, avisos = revisar(json.load(open(sys.argv[1], encoding="utf-8")))
    for a in avisos:
        print("AVISO  " + a)
    for e in errores:
        print("ERROR  " + e)
    print("\n%d errores, %d avisos" % (len(errores), len(avisos)))
    sys.exit(1 if errores else 0)
```

**Criterio de aceptación**

1. Procesa **al menos 20 PDFs** de tu lote (incluye uno sin sello, uno de un solo apellido, uno
   mexicano con CURP, uno con acentos o `Ñ`, uno que no sea pasaporte y uno en blanco).
2. Corre el validador sobre cada respuesta: **0 ERROR**.
3. Para un pasaporte correcto y **sin sello**, el código es **200**, no 212.
4. Para un pasaporte estadounidense de un solo apellido y todo correcto, el código es **200**.
5. Un documento que no es pasaporte responde **225** (no 220) con `clasificacion`.
6. Reporta: cuántos documentos, cuántos ERROR, y tus **Dudas** de la sección 0.

