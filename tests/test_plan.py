"""Validaciones del plan de atención, sección Pasaporte. Datos ficticios."""

from datetime import date

from app import plan
from app.plan import Solicitud, evaluar, pais_iso3, vigencia

DATOS = {"tipo_documento": "P", "pais_emisor": "MEX", "numero_pasaporte": "G12345678", "apellido_paterno": "TORRES",
         "apellido_materno": "VEGA", "nombres": "ANA LUCÍA", "nacionalidad": "MEX", "fecha_nacimiento": "1992-07-08",
         "sexo": "F", "curp": "TOVA920708MDFRGN02", "fecha_vencimiento": "2030-02-13",
         "nombre_completo": "ANA LUCÍA TORRES VEGA", "nacionalidad_impresa": "MEXICANA"}
MRZ = {"nombres": "ANA LUCIA", "apellido_paterno": "TORRES", "apellido_materno": "VEGA", "fecha_nacimiento": "1992-07-08",
       "fecha_vencimiento": "2030-02-13", "sexo": "F", "nacionalidad": "MEX", "integra": True, "nombre_abreviado": False}
SOL_OK = Solicitud(nombre="Torres Vega Ana Lucia", curp="TOVA920708MDFRGN02", fecha_nacimiento="08/07/1992",
                   nacionalidad="Mexicana")


def _res(r, id_):
    return next(i for i in r["validaciones"] if i["id"] == id_)


def test_todo_coincide():
    r = evaluar("pasaporte", DATOS, MRZ, SOL_OK)
    assert r["cumple"] is True and r["mensaje"] == plan.MENSAJE_OK and r["motivos_rechazo"] == []
    assert [i["id"] for i in r["validaciones"]] == ["hoja_en_blanco", "imagen_ilegible", "es_pasaporte", "vigente",
                                                    "nombre_coincide", "curp_coincide", "fecha_nacimiento_coincide",
                                                    "nacionalidad_coincide"]
    assert [i["resultado"] for i in r["validaciones"]] == ["NO", "NO", "SI", "SI", "SI", "SI", "SI", "SI"]


def test_no_coincide():
    sol = Solicitud(nombre="Ana Torres", fecha_nacimiento="1990-01-01", nacionalidad="Colombiana")
    r = evaluar("pasaporte", DATOS, MRZ, sol)
    assert r["cumple"] is False and r["mensaje"] == "Revisar documento y motivo de rechazo"
    assert _res(r, "nombre_coincide")["resultado"] == "NO"
    assert _res(r, "fecha_nacimiento_coincide")["resultado"] == "NO"
    assert _res(r, "nacionalidad_coincide")["resultado"] == "NO"
    assert _res(r, "curp_coincide")["resultado"] == "NO_APLICA"  # la solicitud no trae CURP: no bloquea
    assert len(r["motivos_rechazo"]) == 3


def test_mrz_integra_respalda_nombre_y_fecha():
    # La hoja de datos se leyó mal, pero la MRZ (íntegra) coincide con la solicitud
    datos = {**DATOS, "nombre_completo": "ANA LUCIA TORRES VEGO", "fecha_nacimiento": "1992-07-03"}
    r = evaluar("pasaporte", datos, MRZ, SOL_OK)
    assert _res(r, "nombre_coincide")["resultado"] == "SI"
    assert "MRZ" in _res(r, "nombre_coincide")["detalle"]
    assert _res(r, "fecha_nacimiento_coincide")["resultado"] == "SI"
    # Con una MRZ no íntegra no hay respaldo
    r = evaluar("pasaporte", datos, {**MRZ, "integra": False}, SOL_OK)
    assert _res(r, "nombre_coincide")["resultado"] == "NO"
    assert _res(r, "fecha_nacimiento_coincide")["resultado"] == "NO"


def test_mrz_abreviada_no_respalda_nombre():
    datos = {**DATOS, "nombre_completo": "ANA LUCIA TORRES VEGO"}
    r = evaluar("pasaporte", datos, {**MRZ, "nombre_abreviado": True}, SOL_OK)
    assert _res(r, "nombre_coincide")["resultado"] == "NO"


def test_vigencia_por_anio_y_por_fecha():
    hoy = date(2026, 10, 27)
    assert vigencia({"fecha_vencimiento": "2026-03-01"}, regla="anio", hoy=hoy)[0] is True
    assert vigencia({"fecha_vencimiento": "2026-03-01"}, regla="fecha", hoy=hoy)[0] is False
    assert vigencia({"fecha_vencimiento": "2025-12-31"}, regla="anio", hoy=hoy)[0] is False
    assert vigencia({}, MRZ, regla="anio", hoy=hoy)[0] is True          # sin vencimiento impreso: la MRZ íntegra
    assert vigencia({}, {**MRZ, "integra": False}, hoy=hoy)[0] is None


def test_curp_con_confusion_de_ocr():
    datos = {**DATOS, "curp": "TOVA920708MDFRGN0Z"}  # Z por 2 en la lectura
    r = evaluar("pasaporte", datos, MRZ, SOL_OK)
    assert _res(r, "curp_coincide")["resultado"] == "SI"


def test_pasaporte_extranjero_sin_curp():
    datos = {k: v for k, v in DATOS.items() if k != "curp"} | {"nacionalidad": "COL", "nacionalidad_impresa": "COLOMBIANA"}
    sol = Solicitud(nombre="Ana Lucia Torres Vega", curp="TOVA920708MDFRGN02", fecha_nacimiento="1992-07-08",
                    nacionalidad="Colombia")
    r = evaluar("pasaporte", datos, {**MRZ, "nacionalidad": "COL"}, sol)
    assert _res(r, "curp_coincide")["resultado"] == "NO_APLICA"
    assert _res(r, "nacionalidad_coincide")["resultado"] == "SI"
    assert r["cumple"] is True


def test_sin_solicitud():
    r = evaluar("pasaporte", DATOS, MRZ, Solicitud())
    assert r["cumple"] is False
    assert _res(r, "nombre_coincide")["resultado"] == "NO_VERIFICADO"
    assert r["motivos_rechazo"][-1].startswith("No se enviaron datos de la solicitud")


def test_no_es_pasaporte_y_hoja_en_blanco():
    r = evaluar("otro", None, None, SOL_OK)
    assert _res(r, "es_pasaporte")["resultado"] == "NO" and r["cumple"] is False
    assert r["motivos_rechazo"] == ["¿Es un pasaporte? NO: El documento no es un pasaporte."]
    r = evaluar("hoja_en_blanco", None, None, SOL_OK)
    assert _res(r, "hoja_en_blanco")["resultado"] == "SI"
    assert _res(r, "imagen_ilegible")["resultado"] == "SI"


def test_imagen_ilegible():
    datos = {k: v for k, v in DATOS.items() if k not in ("numero_pasaporte", "fecha_nacimiento")}
    r = evaluar("pasaporte", datos, MRZ, SOL_OK)
    assert _res(r, "imagen_ilegible")["resultado"] == "SI"
    datos = {k: v for k, v in DATOS.items() if k != "numero_pasaporte"}
    assert _res(evaluar("pasaporte", datos, MRZ, SOL_OK), "imagen_ilegible")["resultado"] == "NO"
    assert _res(evaluar("pasaporte", datos, {}, SOL_OK), "imagen_ilegible")["resultado"] == "SI"


def test_paises():
    assert pais_iso3("Mexicana") == "MEX"
    assert pais_iso3("estadounidense") == "USA"
    assert pais_iso3("CO") == "COL"
    assert pais_iso3("SVK") == "SVK"          # código ICAO fuera del catálogo de gentilicios
    assert pais_iso3("Eslovaca") == "SVK"
    assert pais_iso3("D") == "DEU"            # Alemania en la MRZ
    assert pais_iso3("Narnia") is None


def test_vigencia_usa_la_mrz_integra():
    hoy = date(2026, 10, 27)
    datos = {"fecha_vencimiento": "2023-06-21"}  # el 8 se leyó como 3 en la hoja de datos
    mrz = {**MRZ, "fecha_vencimiento": "2028-06-21"}
    vig, det = vigencia(datos, mrz, hoy=hoy)
    assert vig is True and "MRZ" in det and "2023-06-21" in det
    assert vigencia(datos, {**mrz, "integra": False}, hoy=hoy)[0] is False
