from datetime import date

from app import mrz_td3
from app.mrz_td3 import check_digit, parse

# Ejemplo oficial del ICAO 9303 (pasaporte de muestra UTOPIA)
L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"


def test_check_digit_icao():
    assert check_digit("L898902C3") == 6
    assert check_digit("740812") == 2
    assert check_digit("120415") == 9


def test_parse_limpio():
    r = parse([L1, L2])
    assert r is not None
    assert r.pais_emisor == "UTO"
    assert r.apellidos == "ERIKSSON"
    assert r.nombres == "ANNA MARIA"
    assert r.numero == "L898902C3"
    assert r.nacionalidad == "UTO"
    assert r.fecha_nacimiento == date(1974, 8, 12)
    assert r.sexo == "F"
    assert r.fecha_vencimiento == date(2012, 4, 15)
    assert r.opcional == "ZE184226B"
    assert r.integra and r.valido and not r.corregido


def test_errores_tipicos_de_ocr():
    # O por 0 en la fecha, « por <<, K por < en el relleno, espacios
    l1 = "P<UTOERIKSSON«ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
    l2 = "L898902C36UTO74O8122F12O4159ZE184226B<KKK<10"
    r = parse([l1, l2])
    assert r.nombres == "ANNA MARIA"
    assert r.fecha_nacimiento == date(1974, 8, 12)
    assert r.fecha_vencimiento == date(2012, 4, 15)
    assert r.integra


def test_reparacion_con_digito_verificador():
    # 740812 leído como 740813: el dígito verificador (2) permite corregirlo
    l2 = "L898902C36UTO7408132F1204159ZE184226B<<<<<10"
    r = parse([L1, l2])
    assert r.fecha_nacimiento == date(1974, 8, 12)
    assert r.corregido
    assert any(c.nombre == "mrz_fecha_nacimiento" and c.valido and c.corregido for c in r.checks)


def test_opcional_vacio_no_cuenta():
    base = "L898902C36UTO7408122F1204159<<<<<<<<<<<<<<0"
    l2 = base + str(check_digit(base[0:10] + base[13:20] + base[21:43]))
    r = parse([L1, l2])
    assert r.opcional is None
    assert "mrz_opcional" not in {c.nombre for c in r.checks}
    assert r.integra


def test_deteccion_de_lineas():
    assert mrz_td3.looks_like_line1("P<MEXGARCIA<LOPEZ<<JUAN<CARLOS<<<<<<<<<<<<<<")
    assert mrz_td3.looks_like_line2("G123456784MEX8503129M3012317<<<<<<<<<<<<<<02")
    assert not mrz_td3.looks_like_line1("PASAPORTE PASSPORT")
    assert mrz_td3.looks_like_td1("I<MEX1234567890<<<<<<<<<<<<<<<")
    assert not mrz_td3.looks_like_td1("P<MEXGARCIA<LOPEZ<<JUAN<CARLOS<<<<<<<<<<<<<<")


def test_best_prefiere_mas_validos():
    bueno = parse([L1, L2])
    malo = parse([L1, "L898902C36UTO7408122F1204159ZE184226B<<<<<11"])
    assert mrz_td3.best(malo, bueno) is bueno


def test_pais_con_filler_perdido():
    r = parse(["PSVKNOVAK<<JANA<<<<<<<<<<<<<<<<<<<<<<<<<<<<<", "AB1234567<SVK7307064F3001011<<<<<<<<<<<<<<04"])
    assert r.pais_emisor == "SVK"
    assert r.apellidos == "NOVAK"


def test_linea2_con_un_caracter_de_menos():
    # Se perdió un '<' del relleno: con 43 caracteres las posiciones se corren; el parser lo repone
    l2 = "L898902C36UTO7408122F1204159ZE184226B<<<<10"
    r = parse([L1, l2])
    assert r.numero == "L898902C3"
    assert r.fecha_vencimiento == date(2012, 4, 15)
    assert r.integra


def test_linea1_exige_pais_icao():
    assert not mrz_td3.looks_like_line1("PERMISOPARATRABAJAR<<<<<<<<<<<<<<<")
    assert mrz_td3.looks_like_line1("PCHLBRAVO<VALLADARES<<FRANCISCO<<<<<<<<<<<<")
    assert mrz_td3.line1_country("P<MEXGARCIA<<JUAN<<<<<<<<<<<<<<<<<<<<<<<<<<<") == "MEX"
    assert mrz_td3.line1_country("PI<MEXIZASS9BA<A<<<<<<<<<<<<<<<<<<<<<<<<<<<<") is None
