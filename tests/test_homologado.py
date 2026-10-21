"""Formato homologado (docs/HOMOLOGACION_PASAPORTE.md). Todos los datos son ficticios."""

import sys
from pathlib import Path

from app import homologado, mrz_td3
from app.config import Settings
from app.merge import Merger
from app.schemas import Meta, ResultadoPasaporte

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validador_pasaporte import revisar  # noqa: E402

S = Settings(formato_respuesta="homologado", mrz_manda=False, _env_file=None)
S_MANDA = Settings(formato_respuesta="homologado", mrz_manda=True, _env_file=None)

# Ejemplo de la sección 1 del contrato
L1 = "P<MEXTORRES<VEGA<<ANA<LUCIA<<<<<<<<<<<<<<<<<"
L2 = "G123456786MEX9207086F3002131TOVA920708MDFR78"
VLM = {"tipo_documento": "P", "pais_emisor": "MEX", "numero_pasaporte": "G12345678", "apellidos": "TORRES VEGA",
       "nombres": "ANA LUCIA", "nacionalidad": "MEXICANA", "fecha_nacimiento": "1992-07-08", "sexo": "F",
       "sexo_impreso": "F", "lugar_nacimiento": "CIUDAD DE MEXICO", "fecha_expedicion": "2020-02-14",
       "fecha_vencimiento": "2030-02-13", "autoridad": "SRE", "curp": "TOVA920708MDFRGN02",
       "mrz_linea1": L1, "mrz_linea2": L2, "campos_ilegibles": []}
SELLO = {"presente": True, "fecha": "15/01/2026", "reviso": "Jorge Luis Medina Ortiz", "clave_revisor": "$318204"}


def _resultado(vlm=VLM, l1=L1, l2=L2, sello=None, origen="vlm", **kw) -> ResultadoPasaporte:
    m = mrz_td3.parse([l1, l2]) if l2 else None
    merger = Merger(dict(vlm), m)
    datos = merger.run()
    if datos.mrz is not None:
        datos.mrz.origen = origen
    return ResultadoPasaporte(
        archivo="x.pdf", estado="ok", datos=datos, confianza=merger.conf, validaciones=merger.checks,
        advertencias=merger.warnings, meta=Meta(tiempo_total_ms=1, caracteres_leidos=412, categoria="pasaporte"),
        lectura_impresa=merger.impreso, correcciones=merger.correcciones, sello_lectura=sello, **kw)


def _sin_errores(resp):
    errores, _ = revisar(resp)
    assert errores == [], errores


def test_ejemplo_de_la_referencia():
    r = homologado.construir(_resultado(sello=SELLO), S)
    _sin_errores(r)
    assert list(r)[:9] == ["codigo", "estado", "mensaje", "datos", "sello", "mrz", "validacion", "avisos",
                           "clasificacion"]
    assert r["codigo"] == 200 and r["estado"] == "PROCESADO"
    contrato = {k: r["datos"][k] for k in r["datos"] if k in homologado_datos()}
    assert contrato == {
        "tipo_documento": "P", "pais_emisor": "MEX", "numero_pasaporte": "G12345678", "apellido_paterno": "TORRES",
        "apellido_materno": "VEGA", "nombres": "ANA LUCIA", "nacionalidad": "MEX", "fecha_nacimiento": "1992-07-08",
        "lugar_nacimiento": "CIUDAD DE MEXICO", "sexo": "F", "curp": "TOVA920708MDFRGN02",
        "fecha_expedicion": "2020-02-14", "fecha_vencimiento": "2030-02-13", "autoridad_expedidora": "SRE"}
    assert r["sello"] == {"fecha": "2026-01-15", "reviso": "Jorge Luis Medina Ortiz", "clave_revisor": "S318204"}
    assert r["mrz"] == {
        "lineas": [L1, L2], "tipo_documento": "P", "pais_emisor": "MEX", "numero_pasaporte": "G12345678",
        "nacionalidad": "MEX", "numero_personal": "TOVA920708MDFR", "fecha_nacimiento": "1992-07-08", "sexo": "F",
        "fecha_vencimiento": "2030-02-13", "apellido_paterno": "TORRES", "apellido_materno": "VEGA",
        "nombres": "ANA LUCIA", "nombre_abreviado": False,
        "digitos_control": {"numero_pasaporte": True, "fecha_nacimiento": True, "fecha_vencimiento": True,
                            "numero_personal": True, "compuesto": True},
        "integra": True, "origen": "entidad"}
    assert r["validacion"] == {
        "ok": True, "completo": True,
        "coincidencias": ["MRZ (dígitos de control)", "numero_pasaporte (MRZ)", "fecha_nacimiento (MRZ)", "sexo (MRZ)",
                          "fecha_vencimiento (MRZ)", "nacionalidad (MRZ)", "apellido_paterno (MRZ)",
                          "apellido_materno (MRZ)", "nombres (MRZ)", "curp vs número personal (MRZ)",
                          "fecha_nacimiento (CURP)", "sexo (CURP)"],
        "discrepancias": [], "sin_verificar": []}
    assert r["avisos"] == []
    assert r["clasificacion"] == {"categoria": "pasaporte", "confianza": None, "caracteres_leidos": 412}


def homologado_datos():
    return {"tipo_documento", "pais_emisor", "numero_pasaporte", "apellido_paterno", "apellido_materno", "nombres",
            "nacionalidad", "fecha_nacimiento", "lugar_nacimiento", "sexo", "curp", "fecha_expedicion",
            "fecha_vencimiento", "autoridad_expedidora"}


def test_sin_sello_es_200():
    r = homologado.construir(_resultado(sello=None), S)
    _sin_errores(r)
    assert r["codigo"] == 200 and r["sello"] == {}


def test_sello_a_medias_y_clave_sin_forma():
    r = homologado.construir(_resultado(sello={"presente": True, "fecha": "", "reviso": "",
                                               "clave_revisor": "B-6823"}), S)
    _sin_errores(r)
    assert r["sello"] == {}
    assert r["validacion"]["sin_verificar"] == ["sello.fecha (ausente)", "sello.reviso (ausente)"]
    assert r["avisos"] == ["sello.clave_revisor sin forma de clave: se leyó 'B-6823'"]
    assert r["codigo"] == 211


# Pasaporte de EE.UU., un solo apellido (ICAO 9303, datos de muestra)
US1 = "P<USABURTON<<MARY<ANNE<<<<<<<<<<<<<<<<<<<<<<"


def _us_l2():
    base = "A01234567" + "<USA5612271F3203086" + "<" * 14
    l2 = base[:9] + str(mrz_td3.check_digit(base[:9])) + base[10:]
    l2 = l2[:19] + str(mrz_td3.check_digit(l2[13:19])) + l2[20:]
    l2 = l2[:27] + str(mrz_td3.check_digit(l2[21:27])) + l2[28:]
    l2 = l2[:42] + "0"
    return l2 + str(mrz_td3.check_digit(l2[0:10] + l2[13:20] + l2[21:43]))


US_VLM = {"tipo_documento": "P", "pais_emisor": "USA", "numero_pasaporte": "A01234567", "apellidos": "BURTON",
          "nombres": "MARY ANNE", "nacionalidad": "UNITED STATES OF AMERICA", "fecha_nacimiento": "27 DEC 1956",
          "sexo": "F", "sexo_impreso": "F", "lugar_nacimiento": "NEW YORK, U.S.A.", "fecha_expedicion": "09 MAR 2022",
          "fecha_vencimiento": "08 MAR 2032", "autoridad": "UNITED STATES DEPARTMENT OF STATE", "curp": "",
          "mrz_linea1": US1, "campos_ilegibles": []}


def test_eeuu_un_solo_apellido_es_200():
    l2 = _us_l2()
    r = homologado.construir(_resultado(vlm={**US_VLM, "mrz_linea2": l2}, l1=US1, l2=l2), S)
    _sin_errores(r)
    assert r["codigo"] == 200, r["validacion"]
    assert "apellido_materno" not in r["datos"] and "apellido_materno" not in r["mrz"]
    assert "apellido_materno (MRZ)" not in r["validacion"]["coincidencias"] + r["validacion"]["sin_verificar"]


def test_acentos_y_enie_coinciden_con_la_mrz():
    l1 = "P<MEXNUNEZ<GARCIA<<JOSE<LUIS<<<<<<<<<<<<<<<<<"
    vlm = {**VLM, "apellidos": "NÚÑEZ GARCÍA", "nombres": "JOSÉ LUIS", "curp": "", "mrz_linea1": l1}
    r = homologado.construir(_resultado(vlm=vlm, l1=l1), S)
    _sin_errores(r)
    assert r["datos"]["apellido_paterno"] == "NÚÑEZ" and r["datos"]["nombres"] == "JOSÉ LUIS"
    assert {"apellido_paterno (MRZ)", "apellido_materno (MRZ)", "nombres (MRZ)"} <= set(r["validacion"]["coincidencias"])


def test_m_en_pasaporte_mexicano_se_calla():
    l2 = L2[:20] + "M" + L2[21:]
    l2 = l2[:43] + str(mrz_td3.check_digit(l2[0:10] + l2[13:20] + l2[21:43]))
    vlm = {**VLM, "sexo_impreso": "M", "sexo": "F", "curp": "", "mrz_linea2": l2}
    r = homologado.construir(_resultado(vlm=vlm, l2=l2), S)
    _sin_errores(r)
    todo = r["validacion"]["coincidencias"] + r["validacion"]["discrepancias"] + r["validacion"]["sin_verificar"]
    assert not any(x.startswith("sexo") for x in todo)


def test_regla_8_lectura_impresa_vs_mrz_manda():
    vlm = {**VLM, "numero_pasaporte": "G12345673"}  # el VLM leyó mal el último dígito
    r = homologado.construir(_resultado(vlm=vlm), S)
    _sin_errores(r)
    assert r["datos"]["numero_pasaporte"] == "G12345673"
    assert r["codigo"] == 210
    assert r["validacion"]["discrepancias"] == ["numero_pasaporte (MRZ): hoja de datos 'G12345673' vs 'G12345678'"]

    r = homologado.construir(_resultado(vlm=vlm), S_MANDA)
    _sin_errores(r)
    assert r["datos"]["numero_pasaporte"] == "G12345678"
    assert r["codigo"] == 211
    assert r["avisos"] == ["datos.numero_pasaporte corregido con la MRZ: se leyó 'G12345673' y quedó 'G12345678'"]


def test_mrz_corrupta():
    l2 = L2[:43] + "0"  # compuesto roto
    r = homologado.construir(_resultado(l2=l2, vlm={**VLM, "mrz_linea2": l2}), S)
    _sin_errores(r)
    assert r["codigo"] == 210
    assert r["validacion"]["discrepancias"][0].startswith("MRZ corrupta: fallan los dígitos de control de compuesto")
    assert "todas las comprobaciones contra la MRZ" in r["validacion"]["sin_verificar"]


def test_sin_mrz():
    r = homologado.construir(_resultado(l2=None), S)
    _sin_errores(r)
    assert r["mrz"] == {} and "MRZ completa (no se extrajo)" in r["validacion"]["sin_verificar"]


def test_no_es_pasaporte_y_hoja_en_blanco():
    meta = Meta(tiempo_total_ms=1, caracteres_leidos=640, categoria="otro")
    r = homologado.construir(ResultadoPasaporte(estado="rechazado", error="x", meta=meta), S)
    _sin_errores(r)
    assert r == {"codigo": 225, "estado": "NO_ES_PASAPORTE", "mensaje": homologado.MENSAJES[225],
                 "clasificacion": {"categoria": "otro", "confianza": None, "caracteres_leidos": 640}}
    meta = Meta(tiempo_total_ms=1, caracteres_leidos=0, categoria="hoja_en_blanco")
    r = homologado.construir(ResultadoPasaporte(estado="rechazado", error="x", meta=meta), S)
    _sin_errores(r)
    assert r["codigo"] == 221 and r["clasificacion"]["categoria"] == "hoja_en_blanco"


def test_errores_de_archivo():
    for cod in (222, 223, 224):
        r = homologado.construir(ResultadoPasaporte(estado="error", error="x", error_codigo=cod), S)
        _sin_errores(r)
        assert set(r) == {"codigo", "estado", "mensaje"}


def test_curp_corregida_es_aviso():
    vlm = {**VLM, "curp": "TOVA920708MDFRGN07"}  # dígito verificador mal leído
    r = homologado.construir(_resultado(vlm=vlm), S)
    _sin_errores(r)
    assert r["datos"]["curp"] == "TOVA920708MDFRGN02"
    assert r["avisos"] == ["datos.curp corregida con la MRZ y el dígito verificador: "
                           "se leyó 'TOVA920708MDFRGN07' y quedó 'TOVA920708MDFRGN02'"]


def _con_l1(l1, **vlm_kw):
    vlm = {**VLM, "curp": "", "mrz_linea1": l1, **vlm_kw}
    return homologado.construir(_resultado(vlm=vlm, l1=l1), S)


def test_apellido_con_guion_no_es_discrepancia():
    r = _con_l1("P<MEXTORRES<VEGA<<ANA<LUCIA<<<<<<<<<<<<<<<<<", apellidos="TORRES-VEGA")
    _sin_errores(r)
    assert r["datos"]["apellido_paterno"] == "TORRES-VEGA"
    assert r["validacion"]["discrepancias"] == []
    assert {"apellido_paterno (MRZ)", "apellido_materno (MRZ)"} <= set(r["validacion"]["coincidencias"])


def test_enie_transliterada_nxx():
    r = _con_l1("P<MEXMUNXXOZ<VEGA<<ANA<LUCIA<<<<<<<<<<<<<<<<", apellidos="MUÑOZ VEGA")
    _sin_errores(r)
    assert r["validacion"]["discrepancias"] == []


def test_curp_fecha_compara_aammdd():
    vlm = {**VLM, "curp": "TOVA920708MDFRGNA2"}  # posición 17 leída como letra (siglo 2000)
    r = homologado.construir(_resultado(vlm=vlm), S)
    _sin_errores(r)
    assert "fecha_nacimiento (CURP)" in r["validacion"]["coincidencias"]


def test_fechas_del_sello():
    from datetime import date
    from app.sello import parse_clave, parse_fecha
    assert parse_fecha("30032026") == date(2026, 3, 30)
    assert parse_fecha("2 4 JUL 2026") == date(2026, 7, 24)
    assert parse_fecha("22-07-2026") == date(2026, 7, 22)
    assert parse_fecha("14.04.2022") == date(2022, 4, 14)
    assert parse_fecha("13 MAY 2026") == date(2026, 5, 13)
    assert parse_fecha("0202026") is None
    assert parse_fecha("20/6 -06- 11 2") is None
    assert parse_clave("$318204") == "S318204"
    assert parse_clave("5402399") == "S402399"
    assert parse_clave("B 25954") == "B25954"
    assert parse_clave("S0405") is None
