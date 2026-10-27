# Prompt para implementar el cliente de la API OCR de pasaportes

Copia todo el bloque en un asistente de IA y cambia el lenguaje y framework en la primera línea.

```text
Actúa como desarrollador senior. Implementa en [LENGUAJE / FRAMEWORK] un cliente para la API
"OCR de Pasaportes" siguiendo EXACTAMENTE este contrato. Entrega: módulo cliente, modelos tipados
de la respuesta, manejo de errores y reintentos, y un ejemplo de uso.

== QUÉ HACE LA API ==
Recibe un expediente escaneado en PDF y devuelve en JSON los datos de la página de datos del
pasaporte (de cualquier país), validados contra su zona MRZ. Ignora cualquier otro documento del
archivo (tarjeta de residente del INM, credencial INE, solicitudes, etc.). Si no hay pasaporte
responde el código 225.

== PETICIÓN ==
POST http://172.10.30.17:18474/pasaporte
Header obligatorio: X-API-Key: <clave>   (leerla de una variable de entorno OCR_PASAPORTE_API_KEY;
                                           nunca escribirla en el código)
Body: multipart/form-data con UN archivo PDF en el campo "file" (content-type application/pdf).
Solo se aceptan PDF. Tamaño máximo 25 MB. Máximo 30 páginas por archivo; la página de datos del
pasaporte debe estar en las primeras 4 y debe incluir las 2 líneas MRZ del pie.
Timeout del cliente: 120 s. La API tarda de 10 a 25 s por documento y procesa hasta 2 a la vez;
las demás esperan turno. En cargas masivas, enviar como máximo 2 peticiones en paralelo.
POST /extract es un alias para pruebas que responde igual. GET /health (sin API key) devuelve
{"status":"ok",...} para monitoreo.

== RESPUESTA: SIEMPRE ESTE SOBRE JSON ==
{
  "codigo": int,          // decide con ESTE campo, no con el estado HTTP
  "estado": str,          // nombre fijo del código
  "mensaje": str,         // texto para humanos
  "datos": {...},         // solo códigos 200, 210, 211, 212
  "sello": {...},         // solo 200-212; puede ser {} si el PDF no trae sello de cotejo
  "mrz": {...},           // solo 200-212; {} si no se pudo leer la MRZ
  "validacion": {"ok": bool, "completo": bool, "coincidencias": [str],
                 "discrepancias": [str], "sin_verificar": [str]},   // solo 200-212
  "avisos": [str],        // solo 200-212
  "clasificacion": {"categoria": "pasaporte"|"otro"|"hoja_en_blanco",
                    "confianza": null, "caracteres_leidos": int},   // 200-212, 221 y 225
  "confianza": {"<campo>": "alta"|"media"|"baja"},   // solo 200-212 (extensión)
  "meta": {...}           // solo 200-212 (extensión, informativo)
}
REGLA: si un dato no se pudo leer, la LLAVE NO APARECE (no viene null ni ""). Todos los campos de
"datos", "sello", "mrz", "confianza" y "meta" deben modelarse como OPCIONALES.

== CAMPOS DE "datos" ==
tipo_documento (str, normalmente "P") · pais_emisor (str, código ICAO de 3 letras: "MEX")
numero_pasaporte (str) · apellido_paterno (str: primera palabra de los apellidos)
apellido_materno (str: el resto de los apellidos; NO aparece si el pasaporte trae un solo apellido)
nombres (str) · nacionalidad (str, código de 3 letras: "MEX")
fecha_nacimiento ("AAAA-MM-DD") · lugar_nacimiento (str)
sexo (str, TAL COMO ESTÁ IMPRESO: "F", "M", "H"...; en pasaportes mexicanos "M" puede ser mujer)
curp (str, 18 chars, solo pasaportes mexicanos) · fecha_expedicion ("AAAA-MM-DD")
fecha_vencimiento ("AAAA-MM-DD") · autoridad_expedidora (str)
Extensiones: nombre_completo (str) · pais_emisor_nombre (str) · nacionalidad_impresa (str) · vigente (bool)

== CAMPOS DE "sello" (sello "COTEJADO CONTRA ORIGINAL" del banco) ==
fecha ("AAAA-MM-DD") · reviso (str, nombre de quien revisó) · clave_revisor (str: una letra + 5 a 7 dígitos)

== CAMPOS DE "mrz" ==
lineas ([str] x2, 44 caracteres cada una), tipo_documento, pais_emisor, numero_pasaporte,
nacionalidad, numero_personal (opcional), fecha_nacimiento, sexo ("M" | "F" | "X" -- convención
internacional), fecha_vencimiento, apellido_paterno, apellido_materno, nombres,
nombre_abreviado (bool), digitos_control {numero_pasaporte, fecha_nacimiento, fecha_vencimiento,
numero_personal, compuesto: bool}, integra (bool: true solo si los cinco cuadran),
origen ("texto" | "entidad").

== CÓDIGOS Y ACCIÓN ==
Viajan con HTTP 200 (la petición fue válida):
 200 PROCESADO                    -> ACEPTAR: usar datos directo.
 211 PROCESADO_CON_AVISOS         -> ACEPTAR_CON_REVISION: mostrar "avisos".
 212 PROCESADO_INCOMPLETO         -> ACEPTAR_CON_REVISION: mostrar validacion.sin_verificar.
 210 PROCESADO_CON_DISCREPANCIAS  -> REVISION_OBLIGATORIA: mostrar validacion.discrepancias;
                                     no usar los datos sin revisión humana.
 225 NO_ES_PASAPORTE              -> DOCUMENTO_INCORRECTO (sin datos).
 221 HOJA_EN_BLANCO               -> DOCUMENTO_INCORRECTO (reescanear).
 222 ARCHIVO_CORRUPTO             -> ARCHIVO_INVALIDO.
 223 PDF_PROTEGIDO                -> ARCHIVO_INVALIDO (quitar contraseña).
 224 LIMITE_PAGINAS               -> ARCHIVO_INVALIDO (más de 30 páginas).
Viajan con su mismo estado HTTP:
 400 ARCHIVO_NO_SOPORTADO, 413 ARCHIVO_DEMASIADO_GRANDE, 422 PETICION_INVALIDA -> ARCHIVO_INVALIDO
 401 NO_AUTORIZADO, 404 NO_ENCONTRADO, 405 METODO_NO_PERMITIDO               -> ERROR_CONFIGURACION
 500 ERROR_INTERNO                                                            -> REINTENTAR
 429, 502, 503: reservados por homologación (hoy no se emiten)                -> REINTENTAR
Cualquier código desconocido -> tratar como REINTENTAR y registrarlo.
OJO: 220 NO se usa en esta API (es "no es INE" en la API de credenciales).

== REINTENTOS ==
Reintentar SOLO 500, 502, 503, errores de conexión y timeouts: máximo 3 intentos con espera
de 2 s, 4 s y 8 s. Nunca reintentar 4xx ni 210-225.

== REQUISITOS DE IMPLEMENTACIÓN ==
1. Función principal: extraer(archivo) -> resultado tipado con: codigo, estado, mensaje,
   accion (enum de las acciones de arriba), datos (opcional), sello (opcional), avisos,
   discrepancias, sin_verificar y el JSON crudo completo.
2. Leer SIEMPRE el JSON aunque el HTTP sea 4xx/5xx (también trae el sobre).
3. Si la respuesta no es JSON (caída del servidor, proxy), devolver accion=REINTENTAR.
4. No registrar en logs nombres, número de pasaporte, CURP ni el contenido de "datos" (datos personales).
5. API key, URL y timeout configurables por variables de entorno.
6. Incluir pruebas unitarias con respuestas simuladas para 200, 210, 212, 225, 401 y 500.

== EJEMPLO DE RESPUESTA 200 (datos ficticios, extracto) ==
{"codigo":200,"estado":"PROCESADO","mensaje":"El documento se procesó y todas las comprobaciones cuadraron.",
 "datos":{"tipo_documento":"P","pais_emisor":"MEX","numero_pasaporte":"G12345678","apellido_paterno":"TORRES",
  "apellido_materno":"VEGA","nombres":"ANA LUCIA","nacionalidad":"MEX","fecha_nacimiento":"1992-07-08",
  "lugar_nacimiento":"CIUDAD DE MEXICO","sexo":"F","curp":"TOVA920708MDFRGN02","fecha_expedicion":"2020-02-14",
  "fecha_vencimiento":"2030-02-13","autoridad_expedidora":"SRE"},
 "sello":{"fecha":"2026-01-15","reviso":"Jorge Luis Medina Ortiz","clave_revisor":"S318204"},
 "validacion":{"ok":true,"completo":true,"coincidencias":["MRZ (dígitos de control)","numero_pasaporte (MRZ)"],
  "discrepancias":[],"sin_verificar":[]},
 "avisos":[],"clasificacion":{"categoria":"pasaporte","confianza":null,"caracteres_leidos":412}}
```
