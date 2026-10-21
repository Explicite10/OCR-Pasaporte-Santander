"""Vuelve a armar las respuestas homologadas a partir de los resultados internos (json/) de un lote,
sin repetir el OCR ni el VLM. Sirve para iterar sobre la capa de salida.

    python -m scripts.rehacer_respuestas lote/res_homologado
    MRZ_MANDA=true python -m scripts.rehacer_respuestas lote/res_homologado --salida respuestas_mrz_manda
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("lote", help="Carpeta del lote (con json/)")
    ap.add_argument("--salida", default="respuestas", help="Subcarpeta donde se escriben las respuestas")
    args = ap.parse_args()
    os.environ["FORMATO_RESPUESTA"] = "homologado"

    from app import homologado
    from app.config import get_settings
    from app.schemas import ResultadoPasaporte

    s = get_settings()
    out = Path(args.lote) / args.salida
    out.mkdir(exist_ok=True)
    n = 0
    for f in sorted((Path(args.lote) / "json").glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        data.pop("recortes", None)
        resp = homologado.construir(ResultadoPasaporte.model_validate(data), s)
        (out / f.name).write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
        n += 1
    print(f"{n} respuestas en {out} (MRZ_MANDA={s.mrz_manda})")


if __name__ == "__main__":
    main()
