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
