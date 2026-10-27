"""Genera docs/ejemplos_respuesta.json: respuestas de POST /pasaporte producidas por el código real de
la API, con DATOS FICTICIOS. Los usa docs/generar_documentacion.py.

    python -m scripts.generar_ejemplos docs/ejemplos_respuesta.json

Los casos procesados (200-212) se arman con la fusión y la capa homologada reales a partir de una
lectura simulada del modelo; los errores (400, 401, 413, 422, 222) se piden a la API real con
TestClient, sin cargar los modelos.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["FORMATO_RESPUESTA"] = "homologado"
os.environ["MRZ_MANDA"] = "false"
os.environ["API_KEY"] = "clave-de-ejemplo"
os.environ["ENABLE_DOCS"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app import homologado, mrz_td3, plan  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.merge import Merger  # noqa: E402
from app.schemas import Meta, ResultadoPasaporte  # noqa: E402

# Pasaporte mexicano ficticio (mismo del contrato de homologación)
L1 = "P<MEXTORRES<VEGA<<ANA<LUCIA<<<<<<<<<<<<<<<<<"
L2 = "G123456786MEX9207086F3002131TOVA920708MDFR78"
VLM = {"tipo_documento": "P", "pais_emisor": "MEX", "numero_pasaporte": "G12345678", "apellidos": "TORRES VEGA",
       "nombres": "ANA LUCIA", "nacionalidad": "MEXICANA", "fecha_nacimiento": "08 JUL 1992", "sexo": "F",
       "sexo_impreso": "F", "lugar_nacimiento": "CIUDAD DE MEXICO", "fecha_expedicion": "14 FEB 2020",
       "fecha_vencimiento": "13 FEB 2030", "autoridad": "SRE", "curp": "TOVA920708MDFRGN02",
       "mrz_linea1": L1, "mrz_linea2": L2, "campos_ilegibles": []}
SELLO = {"presente": True, "fecha": "15/01/2026", "reviso": "Jorge Luis Medina Ortiz", "clave_revisor": "S318204",
         "pagina": 1}
META = dict(tiempo_total_ms=17840, tiempos_ms={"render": 160, "ocr_y_recorte": 8900, "vlm_pasaporte": 5600,
                                                "vlm_sexo": 1300, "sello": 1880},
            modelo_vlm="qwen3-vl:8b-instruct", paginas=2, pagina_pasaporte=1, recorte="ancla", mrz_fuente="ocr",
            otros_documentos=["tarjeta_td1"], caracteres_leidos=412, categoria="pasaporte")


def procesado(vlm: dict, sello: dict | None) -> dict:
    m = mrz_td3.parse([L1, L2])
    merger = Merger(dict(vlm), m)
    datos = merger.run()
    datos.mrz.origen = "ocr"
    r = ResultadoPasaporte(archivo="expediente.pdf", estado="ok", datos=datos, confianza=merger.conf,
                           validaciones=merger.checks, advertencias=merger.warnings, meta=Meta(**META),
                           lectura_impresa=merger.impreso, correcciones=merger.correcciones, sello_lectura=sello)
    return homologado.construir(r, get_settings())


def sin_datos(categoria: str, caracteres: int) -> dict:
    meta = Meta(tiempo_total_ms=9400, paginas=1, caracteres_leidos=caracteres, categoria=categoria)
    return homologado.construir(ResultadoPasaporte(estado="rechazado", error="x", meta=meta), get_settings())


def main() -> None:
    salida = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/ejemplos_respuesta.json")
    ej = {
        "200": procesado(VLM, SELLO),
        # El modelo leyó mal el último dígito del número impreso; la MRZ lo trae bien.
        "210": procesado({**VLM, "numero_pasaporte": "G12345673"}, SELLO),
        # La CURP se leyó con el dígito verificador equivocado y se corrigió con la MRZ.
        "211": procesado({**VLM, "curp": "TOVA920708MDFRGN07"}, SELLO),
        # El sello trae fecha, pero REVISÓ sólo tiene firma y no viene la clave del revisor.
        "212": procesado(VLM, {"presente": True, "fecha": "15/01/2026", "reviso": "", "clave_revisor": "",
                               "pagina": 1}),
        "sin_sello": procesado(VLM, None),
        "225": sin_datos("otro", 640),
        "221": sin_datos("hoja_en_blanco", 0),
    }
    c = TestClient(app)
    k = {"X-API-Key": "clave-de-ejemplo"}
    pdf = ("expediente.pdf", b"%PDF-1.4 roto", "application/pdf")
    ej["401"] = c.post("/pasaporte", files={"file": pdf}).json()
    ej["400"] = c.post("/pasaporte", headers=k,
                       files={"file": ("foto.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64, "image/png")}).json()
    ej["413"] = c.post("/pasaporte", headers=k,
                       files={"file": ("grande.pdf", b"%PDF" + b"0" * (26 * 1024 * 1024), "application/pdf")}).json()
    ej["422"] = c.post("/pasaporte", headers=k, files={"otro": pdf}).json()
    ej["222"] = c.post("/pasaporte", headers=k, files={"file": ("vacio.pdf", b"no es un pdf", "application/pdf")}).json()
    ej["health"] = {"status": "ok", "vlm": True, "modelo_vlm": "qwen3-vl:8b-instruct", "backend_vlm": "ollama",
                    "formato_respuesta": "homologado", "max_concurrent_jobs": 2}
    # Plan de atención: misma lógica que agrega la API (main._atender) con una solicitud ficticia
    sol = plan.Solicitud(nombre="Ana Lucia Torres Vega", curp="TOVA920708MDFRGN02", fecha_nacimiento="1992-07-08",
                         nacionalidad="Mexicana")
    for k in ("200", "210", "211", "212", "sin_sello", "225", "221"):
        b = ej[k]
        ej[k]["validacion_plan"] = plan.evaluar(b["clasificacion"]["categoria"], b.get("datos"), b.get("mrz"), sol)
    malo = plan.Solicitud(nombre="Ana Torres", fecha_nacimiento="1990-07-08", nacionalidad="Colombiana")
    ej["plan_rechazo"] = plan.evaluar("pasaporte", ej["200"]["datos"], ej["200"]["mrz"], malo)
    salida.write_text(json.dumps(ej, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ok", salida, {k: v.get("codigo") for k, v in ej.items()})


if __name__ == "__main__":
    main()
