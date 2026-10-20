from app import mrz_td3
from app import validators as v
from app.merge import Merger, _clean_name

L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def _vlm(**kw):
    base = {"tipo_documento": "P", "pais_emisor": "UTO", "numero_pasaporte": "L898902C3", "apellidos": "ERIKSSON",
            "nombres": "ANNA MARIA", "nacionalidad": "UTOPIAN", "fecha_nacimiento": "1974-08-12", "sexo": "F",
            "lugar_nacimiento": "ZENITH", "fecha_expedicion": "2002-04-15", "fecha_vencimiento": "2012-04-15",
            "autoridad": "", "curp": "", "mrz_linea1": L1, "mrz_linea2": L2, "campos_ilegibles": []}
    base.update(kw)
    return base


def test_todo_cuadra():
    m = Merger(_vlm(), mrz_td3.parse([L1, L2]))
    d = m.run()
    assert d.numero_pasaporte == "L898902C3" and d.fecha_nacimiento == "1974-08-12" and d.sexo == "F"
    assert all(c.resultado != "falla" for c in m.checks)
    assert m.conf["numero_pasaporte"] == "alta" and m.conf["apellidos"] == "alta"


def test_vlm_lee_mal_el_numero_pero_la_mrz_cuadra():
    m = Merger(_vlm(numero_pasaporte="L898902C8"), mrz_td3.parse([L1, L2]))
    d = m.run()
    assert d.numero_pasaporte == "L898902C3"
    assert m.conf["numero_pasaporte"] == "alta"
    assert not [c for c in m.checks if c.resultado == "falla"]
    assert any("L898902C8" in w for w in m.warnings)


def test_apellido_con_palabras_de_mas():
    m = Merger(_vlm(apellidos="ERIKSSON, HAIXIN"), mrz_td3.parse([L1, L2]))
    d = m.run()
    assert d.apellidos in ("ERIKSSON", "ERIKSSON HAIXIN")
    assert m.conf["apellidos"] in ("alta", "media")
    assert not [c for c in m.checks if c.resultado == "falla"]


def test_pais_ilegible_en_mrz():
    l1 = "P<RASERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
    m = Merger(_vlm(), mrz_td3.parse([l1, L2]))
    d = m.run()
    assert d.pais_emisor == "UTO"


def test_curp_del_ocr():
    c = "GALJ850312HJCRPN0"
    curp = c + v.curp_check_digit(c)
    m = Merger(_vlm(pais_emisor="MEX", curp="GALJ85O312HJCRPN0X"), mrz_td3.parse([L1, L2]), ["CURP " + curp])
    d = m.run()
    assert d.curp == curp


def test_clean_name():
    assert _clean_name("JULIO CESAR C C C") == "JULIO CESAR"
    assert _clean_name("MARC0") == "MARCO"
    assert _clean_name("HUANG, HAIXIN") == "HUANG HAIXIN"
