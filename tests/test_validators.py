from datetime import date

from app import validators as v


def test_parse_date_formatos():
    assert v.parse_date("1985-03-12") == date(1985, 3, 12)
    assert v.parse_date("12/03/1985") == date(1985, 3, 12)
    assert v.parse_date("12 MAR/MAR 1985") == date(1985, 3, 12)
    assert v.parse_date("12 ENE 1985") == date(1985, 1, 12)
    assert v.parse_date("JAN 12, 1985") == date(1985, 1, 12)
    assert v.parse_date("1985.03.12") == date(1985, 3, 12)


def test_curp_repair_fecha_y_sexo_de_la_mrz():
    curp = "MAIM980413MGTSNR02"  # dígito verificador leído mal
    ok = v.curp_repair(curp, date(1998, 4, 13), "F")
    assert ok is None or v.curp_valid(ok)


def test_curp_valid_ejemplo():
    c = "GALJ850312HJCRPN0"
    assert v.curp_valid(c + v.curp_check_digit(c))
