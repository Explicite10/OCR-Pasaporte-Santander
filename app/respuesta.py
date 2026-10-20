"""Sobre homologado de la respuesta (mismo esquema de códigos que la API de INE)."""

from typing import Any

from .schemas import ResultadoPasaporte

ESTADOS = {
    200: "PROCESADO", 210: "PROCESADO_CON_DISCREPANCIAS", 211: "PROCESADO_CON_AVISOS",
    212: "PROCESADO_INCOMPLETO", 220: "NO_ES_PASAPORTE", 221: "HOJA_EN_BLANCO", 222: "ARCHIVO_CORRUPTO",
    223: "PDF_PROTEGIDO", 224: "LIMITE_PAGINAS", 400: "ARCHIVO_NO_SOPORTADO", 401: "NO_AUTORIZADO",
    404: "NO_ENCONTRADO", 405: "METODO_NO_PERMITIDO", 413: "ARCHIVO_DEMASIADO_GRANDE",
    422: "PETICION_INVALIDA", 500: "ERROR_INTERNO",
}
MENSAJES = {
    200: "El documento se procesó y todas las comprobaciones cuadraron.",
    210: "El documento se procesó pero hay datos que se contradicen; revisar `validacion.discrepancias`.",
    211: "El documento se procesó; nada se contradijo pero algo pide revisión humana (ver `avisos`).",
    212: "El documento se procesó pero quedaron comprobaciones sin correr (ver `validacion.sin_verificar`).",
    220: "El documento no es un pasaporte; no se extrajo nada.",
    221: "El documento está en blanco o no tiene texto legible.",
    222: "El archivo está vacío, dañado, cortado o no es del tipo que dice.",
    223: "El PDF está protegido con contraseña.",
    224: "El documento tiene más páginas de las permitidas.",
    400: "Tipo de archivo no soportado.",
    401: "Falta o no coincide el header X-API-Key.",
    404: "Ruta no encontrada.",
    405: "Método no permitido.",
    413: "El archivo excede el tamaño máximo.",
    422: "La petición viene mal formada.",
    500: "Error interno; reportar.",
}


def http_status(codigo: int) -> int:
    return 200 if codigo < 300 else codigo


def sobre(codigo: int, mensaje: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"codigo": codigo, "estado": ESTADOS.get(codigo, "ERROR"), "mensaje": mensaje or MENSAJES.get(codigo, ""),
            **extra}


def construir(r: ResultadoPasaporte) -> dict[str, Any]:
    if r.estado == "error":
        codigo = r.error_codigo if r.error_codigo in ESTADOS else 500
        return sobre(codigo, r.error, meta=r.meta.model_dump() if r.meta else None)
    if r.estado == "rechazado":
        codigo = 221 if r.meta and r.meta.categoria == "hoja_en_blanco" else 220
        return sobre(codigo, r.error, meta=r.meta.model_dump() if r.meta else None)

    coincidencias = [c.regla for c in r.validaciones if c.resultado == "ok"]
    discrepancias = [{"regla": c.regla, "detalle": c.detalle} for c in r.validaciones if c.resultado == "falla"]
    sin_verificar = [c.regla for c in r.validaciones if c.resultado == "no_aplica"]
    avisos = list(r.advertencias) + [f"campo con confianza baja: {c}" for c in r.campos_a_revisar]
    mrz_integra = bool(r.datos.mrz and r.datos.mrz.integra)
    if not mrz_integra:
        avisos.append("La MRZ no cuadró por completo con sus dígitos verificadores")
    if discrepancias:
        codigo = 210
    elif avisos:
        codigo = 211
    elif sin_verificar:
        codigo = 212
    else:
        codigo = 200
    datos = r.datos.model_dump(exclude_none=True)
    mrz = datos.pop("mrz", None)
    return sobre(
        codigo, None,
        pasaporte=datos, mrz=mrz,
        validacion={"ok": not discrepancias, "completo": not sin_verificar, "coincidencias": coincidencias,
                    "discrepancias": discrepancias, "sin_verificar": sin_verificar},
        avisos=avisos, confianza=r.confianza, meta=r.meta.model_dump() if r.meta else None,
        **({"recortes": r.recortes} if r.recortes else {}),
    )
