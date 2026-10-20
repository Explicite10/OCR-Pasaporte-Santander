"""Compara dos corridas (resultados.csv) campo por campo: cuántos documentos cambiaron y en qué.

    python -m scripts.comparar_lotes lote/res_qwen3vl/resultados.csv lote/res_glm/resultados.csv
"""

import csv
import statistics
import sys
from collections import Counter

CAMPOS = ["numero_pasaporte", "apellidos", "nombres", "fecha_nacimiento", "fecha_vencimiento", "sexo",
          "pais_emisor", "nacionalidad", "fecha_expedicion", "lugar_nacimiento", "curp"]


def load(path: str) -> dict[str, dict]:
    with open(path, encoding="utf-8-sig") as fh:
        return {r["archivo"]: r for r in csv.DictReader(fh)}


def resumen(nombre: str, rows: dict[str, dict]) -> str:
    est = Counter(r["estado"] for r in rows.values())
    mrz = sum(1 for r in rows.values() if r.get("mrz_integra") == "True")
    alta = Counter(f for r in rows.values() for f in CAMPOS if r.get(f"conf_{f}") == "alta")
    t = [int(float(r["tiempo_ms"])) for r in rows.values() if r.get("tiempo_ms")]
    med = statistics.median(t) / 1000 if t else 0
    return (f"{nombre}: ok {est.get('ok', 0)} · revisar {est.get('revisar', 0)} · rechazado {est.get('rechazado', 0)}"
            f" · error {est.get('error', 0)} · MRZ íntegra {mrz} · mediana {med:.1f} s\n"
            f"   confianza alta por campo: " + ", ".join(f"{f}={alta.get(f, 0)}" for f in CAMPOS))


def main() -> None:
    a, b = load(sys.argv[1]), load(sys.argv[2])
    comunes = sorted(set(a) & set(b))
    print(f"Documentos comparados: {len(comunes)}\n")
    print(resumen("A", {k: a[k] for k in comunes}))
    print(resumen("B", {k: b[k] for k in comunes}))
    cambios = Counter()
    por_doc = {}
    for k in comunes:
        diff = [f for f in CAMPOS if (a[k].get(f) or "") != (b[k].get(f) or "")]
        if a[k]["estado"] != b[k]["estado"]:
            diff.append(f"estado {a[k]['estado']}→{b[k]['estado']}")
        for f in diff:
            cambios[f.split(" ")[0]] += 1
        if diff:
            por_doc[k] = diff
    print(f"\nDocumentos idénticos: {len(comunes) - len(por_doc)} de {len(comunes)}")
    print("\nCampos que cambiaron:")
    for f, n in cambios.most_common():
        print(f"  {f}: {n}")
    print("\nPor documento (sólo nombres de campo):")
    for k, diff in list(por_doc.items())[:80]:
        print(f"  {k}: {', '.join(diff)}")


if __name__ == "__main__":
    main()
