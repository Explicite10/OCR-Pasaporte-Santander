"""Corre el validador del contrato (scripts/validador_pasaporte.py) sobre una carpeta de respuestas.

    python -m scripts.validar_respuestas lote/res_homologado/respuestas

Imprime, por documento, el código y cuántos ERROR / AVISO tuvo, y un resumen de los tipos de ERROR.
Los mensajes se resumen SIN los valores entre comillas (pueden traer datos personales).
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validador_pasaporte import revisar  # noqa: E402


def _sin_valores(msg: str) -> str:
    return re.sub(r"'[^']*'|\"[^\"]*\"", "'…'", msg)


def main() -> None:
    carpeta = Path(sys.argv[1])
    tipos_err, tipos_av, codigos = Counter(), Counter(), Counter()
    n_err_docs = 0
    files = sorted(carpeta.glob("*.json"))
    for f in files:
        r = json.loads(f.read_text(encoding="utf-8"))
        errores, avisos = revisar(r)
        codigos[r.get("codigo")] += 1
        n_err_docs += bool(errores)
        for e in errores:
            tipos_err[_sin_valores(e)] += 1
        for a in avisos:
            tipos_av[_sin_valores(a)] += 1
        print(f"{f.name}: codigo {r.get('codigo')} · {len(errores)} ERROR · {len(avisos)} AVISO")
    print(f"\n{len(files)} respuestas · {n_err_docs} con ERROR · {sum(tipos_err.values())} ERROR en total")
    print("códigos:", dict(sorted(codigos.items(), key=lambda x: str(x[0]))))
    if tipos_err:
        print("\nTipos de ERROR:")
        for k, n in tipos_err.most_common():
            print(f"  {n:4d}  {k}")
    print("\nTipos de AVISO (extensiones):")
    for k, n in tipos_av.most_common(10):
        print(f"  {n:4d}  {k}")
    sys.exit(1 if tipos_err else 0)


if __name__ == "__main__":
    main()
