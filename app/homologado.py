"""Respuesta de POST /pasaporte en el formato de la API de referencia (santander_ia).

Contrato: docs/HOMOLOGACION_PASAPORTE.md. Este módulo sólo TRADUCE el resultado interno del pipeline
(ResultadoPasaporte); el motor (OCR, VLM, MRZ, fusión) no cambia. Las comprobaciones de `validacion`
se recalculan con las reglas de la referencia a partir de `datos` y `mrz`; las comprobaciones propias
que no tienen equivalente van en `meta.validaciones_extra`.

Regla de la sección 8 (configurable con MRZ_MANDA):
  False (default): `datos` lleva la lectura impresa; si difiere de la MRZ es discrepancia (210).
  True: `datos` lleva lo que decidió la fusión (la MRZ manda si su dígito la respalda) y cada
        corrección queda como aviso (211).
"""

import re
from datetime import date
from typing import Any

from . import sello as sello_mod
from . import validators as v
from .config import Settings, get_settings
from .merge import _clean_name
from .schemas import ResultadoPasaporte

ESTADOS = {
    200: "PROCESADO", 210: "PROCESADO_CON_DISCREPANCIAS", 211: "PROCESADO_CON_AVISOS",
    212: "PROCESADO_INCOMPLETO", 221: "HOJA_EN_BLANCO", 222: "ARCHIVO_CORRUPTO", 223: "PDF_PROTEGIDO",
    224: "LIMITE_PAGINAS", 225: "NO_ES_PASAPORTE", 400: "ARCHIVO_NO_SOPORTADO", 422: "PETICION_INVALIDA",
    429: "CUOTA_EXCEDIDA", 500: "ERROR_INTERNO", 502: "ERROR_DOCUMENT_AI", 503: "SIN_CREDENCIALES",
    # Extensiones de este servicio (no existen en la referencia)
    401: "NO_AUTORIZADO", 404: "NO_ENCONTRADO", 405: "METODO_NO_PERMITIDO", 413: "ARCHIVO_DEMASIADO_GRANDE",
}
MENSAJES = {
    200: "El documento se procesó y todas las comprobaciones cuadraron.",
    210: "El documento se procesó, pero hay datos que se contradicen entre sí. Revisa 'validacion.discrepancias' "
         "antes de dar los datos por buenos.",
    211: "El documento se procesó y nada se contradijo, pero hay algo que requiere revisión humana. Revisa 'avisos'.",
    212: "El documento se procesó y nada se contradijo, pero quedaron comprobaciones sin poder realizarse. "
         "Revisa 'validacion.sin_verificar'.",
    221: "El documento viene en blanco o ilegible: no se leyó ningún texto.",
    222: "El archivo no se pudo abrir: está dañado, incompleto, o no es del tipo que dice ser.",
    223: "El PDF está protegido con contraseña. Quítasela y vuelve a enviarlo.",
    224: "El documento tiene más páginas de las que se pueden procesar en una sola llamada. "
         "Envía solo las páginas de la credencial.",
    225: "El documento no es un pasaporte. No se extrajo ningun dato.",
    400: "El tipo de archivo enviado no se acepta.",
    401: "Falta o no coincide el header X-API-Key.",
    404: "Ruta no encontrada.",
    405: "Método no permitido.",
    413: "El archivo excede el tamaño máximo.",
    422: "La petición no es válida. Se espera multipart/form-data con un campo 'file'.",
    500: "Error interno de la API.",
}


def sobre(codigo: int, mensaje: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"codigo": codigo, "estado": ESTADOS.get(codigo, "ERROR_INTERNO"),
            "mensaje": mensaje or MENSAJES.get(codigo, MENSAJES[500]), **extra}


# ---------------------------------------------------------------- utilidades


def _txt(s: Any) -> str | None:
    """Texto limpio: sin saltos de línea ni basura en los bordes. None si queda vacío."""
    if not isinstance(s, str):
        return None
    s = re.sub(r"\s+", " ", s.replace("\n", " ")).strip(" -,:;")
    return s or None


def _sin_vacios(d: dict) -> dict:
    return {k: val for k, val in d.items() if val is not None and val != ""}


def _split(apellidos: str | None) -> tuple[str | None, str | None]:
    """Regla provisional de la referencia: 1ª palabra = paterno, el resto = materno."""
    if not apellidos:
        return None, None
    partes = apellidos.split()
    return partes[0], (" ".join(partes[1:]) or None)


_SEXO = {"H": "M", "HOMBRE": "M", "MALE": "M", "MASCULINO": "M", "M": "M",
         "F": "F", "FEMALE": "F", "MUJER": "F", "FEMENINO": "F", "X": "X"}


def _sexo_codigo(impreso: str | None, pais: str | None) -> str | None:
    """Sexo impreso -> código internacional. "" = ambiguo (M en pasaporte mexicano): no se compara.
    None = no se reconoce."""
    if not impreso:
        return None
    t = v.strip_accents(impreso.upper()).strip(" .")
    partes = [p.strip(" .") for p in re.split(r"[/\s]+", t) if p.strip(" .")] or [t]
    cods = {_SEXO.get(p) for p in partes}
    if None in cods or len(cods) != 1:
        return None
    if partes and all(p == "M" for p in partes) and pais == "MEX":
        return ""
    return cods.pop()


def _norm_nombre(s: str | None) -> str:
    return v.norm_text(s)


# Transliteraciones ICAO 9303 que la MRZ puede usar en lugar de quitar el acento
_TRANSLIT = (("Ñ", "NXX"), ("Ü", "UE"), ("Ä", "AE"), ("Ö", "OE"), ("ß", "SS"), ("Å", "AA"), ("Ø", "OE"), ("Æ", "AE"))


def _formas(s: str | None, es_mrz: bool) -> set[str]:
    """Formas equivalentes de un nombre para compararlo con la MRZ: sin acentos (Ñ = N), con la
    transliteración ICAO, y sin espacios (guiones y apóstrofos se vuelven '<' u omiten en la MRZ)."""
    if not s:
        return set()
    base = {v.norm_text(s)}
    if es_mrz:
        base.add(v.norm_text(s.upper().replace("NXX", "N")))
    else:
        t = s.upper()
        for a, b in _TRANSLIT:
            t = t.replace(a, b)
        base.add(v.norm_text(t))
    return base | {x.replace(" ", "") for x in base}


def _nombres_iguales(a: str | None, b: str | None) -> bool:
    return bool(_formas(a, False) & _formas(b, True))


# ---------------------------------------------------------------- bloques


def _datos(r: ResultadoPasaporte, s: Settings) -> tuple[dict, list[str]]:
    d, imp = r.datos, r.lectura_impresa or {}
    avisos: list[str] = []

    def valor(campo: str, fusion: Any) -> Any:
        if s.mrz_manda:
            leido = imp.get(campo)
            if leido and fusion and _comparable(campo, leido) != _comparable(campo, fusion):
                avisos.append(f"datos.{campo} corregido con la MRZ: se leyó '{leido}' y quedó '{fusion}'")
            return fusion if fusion else leido
        return imp.get(campo)

    numero = valor("numero_pasaporte", d.numero_pasaporte)
    apellidos = valor("apellidos", d.apellidos)
    nombres = valor("nombres", d.nombres)
    nacimiento = valor("fecha_nacimiento", d.fecha_nacimiento)
    vencimiento = valor("fecha_vencimiento", d.fecha_vencimiento)
    sexo = _txt(imp.get("sexo")) or (d.sexo if s.mrz_manda else None)
    paterno, materno = _split(_txt(apellidos))

    for c in r.correcciones or []:
        if c.get("campo") == "curp":
            como = "con la MRZ y el dígito verificador" if c.get("fuente") == "mrz" else "con el OCR"
            avisos.append(f"datos.curp corregida {como}: se leyó '{c.get('leido')}' y quedó '{c.get('quedo')}'")

    vigente = None
    if vencimiento:  # misma regla que la validación "¿Está vigente?" del plan de atención
        f = date.fromisoformat(vencimiento)
        vigente = f >= date.today() if s.regla_vigencia == "fecha" else f.year >= date.today().year
    out = _sin_vacios({
        "tipo_documento": d.tipo_documento,
        "pais_emisor": d.pais_emisor,
        "numero_pasaporte": numero,
        "apellido_paterno": paterno,
        "apellido_materno": materno,
        "nombres": _txt(nombres),
        "nacionalidad": d.nacionalidad,
        "fecha_nacimiento": nacimiento,
        "lugar_nacimiento": _txt(d.lugar_nacimiento),
        "sexo": sexo,
        "curp": d.curp,
        "fecha_expedicion": d.fecha_expedicion,
        "fecha_vencimiento": vencimiento,
        "autoridad_expedidora": _txt(d.autoridad),
        # extensiones permitidas
        "nombre_completo": " ".join(x for x in (_txt(nombres), _txt(apellidos)) if x) or None,
        "pais_emisor_nombre": d.pais_emisor_nombre,
        "nacionalidad_impresa": _txt(d.nacionalidad_impresa),
        "vigente": vigente,
    })
    return out, avisos


def _comparable(campo: str, val: Any) -> str:
    if campo in ("apellidos", "nombres"):
        return _norm_nombre(val)
    return v.norm_code(str(val)) if campo == "numero_pasaporte" else str(val)


def _mrz(r: ResultadoPasaporte) -> dict:
    m = r.datos.mrz
    if m is None or not m.lineas or len(m.lineas) < 2:
        return {}
    l1, l2 = m.lineas[0], m.lineas[1]
    dc_int = m.digitos_control or {}
    personal_vacio = l2[28:42].strip("<") == ""
    dc = {
        "numero_pasaporte": bool(dc_int.get("numero")),
        "fecha_nacimiento": bool(dc_int.get("fecha_nacimiento")),
        "fecha_vencimiento": bool(dc_int.get("vencimiento")),
        "numero_personal": (bool(dc_int["opcional"]) if "opcional" in dc_int
                            else (personal_vacio and l2[42] in "0<")),
        "compuesto": bool(dc_int.get("compuesto")),
    }
    paterno, materno = _split(_clean_name(m.apellidos))
    origen = {"ocr": "texto", "vlm": "entidad"}.get(m.origen or (r.meta.mrz_fuente if r.meta else None) or "")
    return _sin_vacios({
        "lineas": [l1, l2],
        "tipo_documento": m.tipo_documento,
        "pais_emisor": m.pais_emisor,
        "numero_pasaporte": m.numero,
        "nacionalidad": m.nacionalidad,
        "numero_personal": m.opcional,
        "fecha_nacimiento": m.fecha_nacimiento,
        "sexo": m.sexo,
        "fecha_vencimiento": m.fecha_vencimiento,
        "apellido_paterno": paterno,
        "apellido_materno": materno,
        "nombres": _clean_name(m.nombres),
        "nombre_abreviado": not l1.endswith("<"),
        "digitos_control": dc,
        "integra": all(dc.values()),
        "origen": origen or "texto",
    })


def _validacion(datos: dict, mrz: dict) -> tuple[list[str], list[str], list[str]]:
    co: list[str] = []
    di: list[str] = []
    sv: list[str] = []

    def comparar(etiqueta: str, a: Any, b: Any, norm=lambda x: str(x).upper(), opcional=False,
                 abreviable=False, nombre=False) -> None:
        if a is None and b is None and opcional:
            return
        if a is None or b is None:
            if opcional:
                di.append(f"{etiqueta}: hoja de datos '{a or ''}' vs '{b or ''}'")
            else:
                sv.append(etiqueta)
            return
        na, nb = norm(a), norm(b)
        if na == nb or (nombre and _nombres_iguales(a, b)):
            co.append(etiqueta)
        elif abreviable and mrz.get("nombre_abreviado") and nb and na.startswith(nb):
            co.append(f"{etiqueta} (abreviado en la MRZ)")
        else:
            di.append(f"{etiqueta}: hoja de datos '{a}' vs '{b}'")

    if not mrz:
        sv.append("MRZ completa (no se extrajo)")
    elif not mrz.get("integra"):
        malos = ", ".join(k for k, ok in mrz["digitos_control"].items() if not ok)
        di.append(f"MRZ corrupta: fallan los dígitos de control de {malos}; "
                  "no se pudo contrastar la hoja de datos contra el reverso")
        sv.append("todas las comprobaciones contra la MRZ")
    else:
        co.append("MRZ (dígitos de control)")
        comparar("numero_pasaporte (MRZ)", datos.get("numero_pasaporte"), mrz.get("numero_pasaporte"),
                 norm=v.norm_code)
        comparar("fecha_nacimiento (MRZ)", datos.get("fecha_nacimiento"), mrz.get("fecha_nacimiento"))
        sx = _sexo_codigo(datos.get("sexo"), datos.get("pais_emisor"))
        if sx != "":  # "" = M en pasaporte mexicano: ambiguo, se calla
            if sx is None and datos.get("sexo") and mrz.get("sexo"):
                di.append(f"sexo (MRZ): hoja de datos '{datos['sexo']}' vs '{mrz['sexo']}'")
            elif sx is None or mrz.get("sexo") is None:
                sv.append("sexo (MRZ)")
            elif sx == mrz["sexo"]:
                co.append("sexo (MRZ)")
            else:
                di.append(f"sexo (MRZ): hoja de datos '{datos['sexo']}' vs '{mrz['sexo']}'")
        comparar("fecha_vencimiento (MRZ)", datos.get("fecha_vencimiento"), mrz.get("fecha_vencimiento"))
        comparar("nacionalidad (MRZ)", datos.get("nacionalidad"), mrz.get("nacionalidad"))
        ap_d = " ".join(x for x in (datos.get("apellido_paterno"), datos.get("apellido_materno")) if x)
        ap_m = " ".join(x for x in (mrz.get("apellido_paterno"), mrz.get("apellido_materno")) if x)
        if ap_d and ap_m and _nombres_iguales(ap_d, ap_m):
            # Los apellidos completos coinciden aunque la división en paterno/materno no (guion,
            # apóstrofo, apellido compuesto): no se reporta una discrepancia falsa (sección 9.2).
            co.append("apellido_paterno (MRZ)")
            if datos.get("apellido_materno") or mrz.get("apellido_materno"):
                co.append("apellido_materno (MRZ)")
        else:
            if datos.get("apellido_paterno") or mrz.get("apellido_paterno"):
                comparar("apellido_paterno (MRZ)", datos.get("apellido_paterno"), mrz.get("apellido_paterno"),
                         norm=_norm_nombre, abreviable=True, nombre=True)
            comparar("apellido_materno (MRZ)", datos.get("apellido_materno"), mrz.get("apellido_materno"),
                     norm=_norm_nombre, opcional=True, abreviable=True, nombre=True)
        comparar("nombres (MRZ)", datos.get("nombres"), mrz.get("nombres"), norm=_norm_nombre, abreviable=True,
                 nombre=True)

    curp = datos.get("curp")
    if curp:
        if not v.CURP_RE.match(curp):
            sv.append(f"CURP (formato inválido: '{curp}')")
        else:
            personal = mrz.get("numero_personal") if mrz.get("integra") else None
            if personal:
                if curp.startswith(personal) or personal.startswith(curp):
                    co.append("curp vs número personal (MRZ)")
                else:
                    di.append(f"curp: '{curp}' no corresponde al número personal de la MRZ '{personal}'")
            # Posiciones 5 a 10 de la CURP = AAMMDD. El siglo lo da la posición 17, que es la que más
            # se lee mal; se compara sólo AAMMDD y la fecha de la CURP se muestra con el siglo impreso.
            fn = datos.get("fecha_nacimiento")
            if fn and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fn):
                aammdd = fn[2:4] + fn[5:7] + fn[8:10]
                if aammdd == curp[4:10]:
                    co.append("fecha_nacimiento (CURP)")
                else:
                    de_curp = f"{fn[:2]}{curp[4:6]}-{curp[6:8]}-{curp[8:10]}"
                    di.append(f"fecha_nacimiento (CURP): hoja de datos '{fn}' vs '{de_curp}'")
            else:
                sv.append("fecha_nacimiento (CURP)")
            sx = _sexo_codigo(datos.get("sexo"), datos.get("pais_emisor"))
            curp_sx = {"H": "M", "M": "F"}.get(curp[10])
            if sx != "":
                if sx is None or curp_sx is None:
                    sv.append("sexo (CURP)")
                elif sx == curp_sx:
                    co.append("sexo (CURP)")
                else:
                    di.append(f"sexo (CURP): hoja de datos '{datos.get('sexo')}' vs '{curp[10]}'")
    return co, di, sv


def construir(r: ResultadoPasaporte, s: Settings | None = None) -> dict[str, Any]:
    s = s or get_settings()
    meta = r.meta
    caracteres = meta.caracteres_leidos if meta else 0

    if r.estado == "error":
        codigo = r.error_codigo if r.error_codigo in ESTADOS else 500
        return sobre(codigo)
    if r.estado == "rechazado":
        blanco = bool(meta and meta.categoria == "hoja_en_blanco")
        return sobre(221 if blanco else 225, clasificacion={
            "categoria": "hoja_en_blanco" if blanco else "otro", "confianza": None, "caracteres_leidos": caracteres})

    datos, avisos = _datos(r, s)
    mrz = _mrz(r)
    co, di, sv = _validacion(datos, mrz)

    sel = sello_mod.interpretar(r.sello_lectura)
    sv += [f"sello.{c} (ausente)" for c in sel.ausentes]
    avisos = sel.avisos + avisos
    if r.pasaportes_detectados > 1:
        avisos.append(f"el PDF contiene {r.pasaportes_detectados} bloques 'pasaporte': se conservó el primero, "
                      "revisa que el documento no traiga más de una identidad")

    codigo = 210 if di else 211 if avisos else 212 if sv else 200
    extra = [c.model_dump() for c in r.validaciones]
    meta_out = meta.model_dump() if meta else {}
    meta_out["validaciones_extra"] = extra
    meta_out["advertencias"] = list(r.advertencias)
    return {
        **sobre(codigo),
        "datos": datos,
        "sello": sel.campos,
        "mrz": mrz,
        "validacion": {"ok": not di, "completo": not sv, "coincidencias": co, "discrepancias": di,
                       "sin_verificar": sv},
        "avisos": avisos,
        "clasificacion": {"categoria": "pasaporte", "confianza": None, "caracteres_leidos": caracteres},
        # extensiones (no son parte del contrato)
        "confianza": r.confianza,
        "meta": meta_out,
        **({"recortes": r.recortes} if r.recortes else {}),
    }
