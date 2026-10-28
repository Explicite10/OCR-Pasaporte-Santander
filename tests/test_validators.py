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


def test_curp_homoclave_o_por_cero():
    # Nacido en 1986: la posición 17 debe ser dígito. La O se leyó por 0 y ambas cuadran con el verificador.
    assert v.curp_homoclave("BASS860620HNLRMRO2", date(1986, 6, 20)) == "BASS860620HNLRMR02"
    assert v.curp_homoclave("BASS860620HNLRMR02", date(1986, 6, 20)) == "BASS860620HNLRMR02"
    # Nacido en 2001: debe ser letra; un 0 se vuelve O si cuadra
    c = "GALJ010312HJCRPNO"
    curp = c + v.curp_check_digit(c)
    assert v.curp_homoclave(curp[:16] + "0" + curp[17:], date(2001, 3, 12)) == curp
    assert v.curp_homoclave(None, date(1986, 6, 20)) is None
