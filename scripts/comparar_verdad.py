"""Compara una captura de verdad de terreno (verdad.jsonl, un pasaporte por línea) contra lo que respondió
la API, campo por campo, y produce la exactitud por campo y la lista de discrepancias para revisión humana.

    python -m scripts.comparar_verdad verdad.jsonl lote/res_v2 --salida lote/verdad

Compara dos salidas del mismo motor:
  * homologado: `datos` de la respuesta homologada (lectura impresa, regla de la referencia)
  * interno:    `datos` del resultado interno (fusión donde la MRZ manda cuando su dígito la respalda)

Campos de verdad.jsonl: id, pais, numero, apellidos, nombres, nacionalidad (impresa), nacimiento, sexo,
lugar, expedicion, vencimiento, autoridad, curp, nota. Un campo vacío = el capturista no lo pudo leer
(no se evalúa). Imprime SOLO conteos; los valores van al CSV de discrepancias.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CAMPOS = ["pais", "numero", "apellidos", "nombres", "nacionalidad", "nacimiento", "sexo", "lugar", "expedicion",
          "vencimiento", "autoridad", "curp"]
HOM = {"pais": "pais_emisor", "numero": "numero_pasaporte", "nacionalidad": "nacionalidad_impresa",
       "nacimiento": "fecha_nacimiento", "lugar": "lugar_nacimiento", "expedicion": "fecha_expedicion",
       "vencimiento": "fecha_vencimiento", "autoridad": "autoridad_expedidora"}
INT = {"pais": "pais_emisor", "numero": "numero_pasaporte", "nacionalidad": "nacionalidad_impresa",
       "nacimiento": "fecha_nacimiento", "lugar": "lugar_nacimiento", "expedicion": "fecha_expedicion",
       "vencimiento": "fecha_vencimiento", "autoridad": "autoridad"}


def _n(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _code(s):
    return re.sub(r"[^A-Z0-9]", "", _n(s))


def igual(campo, verdad, api):
    """(resultado, nota): 'ok' | 'parcial' | 'falla' | 'vacio' (la API no lo entregó)."""
    if api in (None, ""):
        return "vacio", ""
    if campo in ("numero", "curp"):
        return ("ok" if _code(verdad) == _code(api) else "falla"), ""
    if campo == "pais":
        v, a = _code(verdad), _code(api)
        if v == a or {v, a} == {"D", "DEU"}:
            return "ok", ""
        return "falla", ""
    if campo == "sexo":
        v, a = _code(verdad), _code(api)
        return ("ok" if v == a or (v, a) in (("M", "H"), ("H", "M")) else "falla"), ""
    if campo in ("nacimiento", "expedicion", "vencimiento"):
        return ("ok" if str(verdad) == str(api) else "falla"), ""
    v, a = _n(verdad), _n(api)
    if v == a or v.replace(" ", "") == a.replace(" ", ""):
        return "ok", ""
    if campo in ("apellidos", "nombres"):
        # mismas palabras en otro orden, o una lectura es prefijo de la otra (MRZ recortada)
        if sorted(v.split()) == sorted(a.split()):
            return "ok", "orden"
    if campo in ("lugar", "autoridad", "nacionalidad"):
        if v in a or a in v:
            return "parcial", "uno contiene al otro"
    return "falla", ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verdad")
    ap.add_argument("lote")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()
    out = Path(a.salida)
    out.mkdir(parents=True, exist_ok=True)
    verdad = [json.loads(l) for l in open(a.verdad, encoding="utf-8") if l.strip()]

    filas = []
    tot = {m: defaultdict(Counter) for m in ("homologado", "interno")}
    docs_perfectos = Counter()
    no_pasaporte = []
    for v in verdad:
        id_ = v["id"]
        interno = json.loads((Path(a.lote) / "json" / f"{id_}.json").read_text(encoding="utf-8"))
        hom_p = Path(a.lote) / "respuestas" / f"{id_}.json"
        hom = json.loads(hom_p.read_text(encoding="utf-8")) if hom_p.exists() else {}
        if not v.get("numero"):  # el recorte no era un pasaporte según el capturista
            no_pasaporte.append((id_, hom.get("codigo"), (hom.get("clasificacion") or {}).get("categoria"),
                                 interno.get("estado"), v.get("nota", "")[:60]))
            continue
        di = interno.get("datos") or {}
        dh = hom.get("datos") or {}
        mrz = hom.get("mrz") or {}
        conf = interno.get("confianza") or {}
        perfecto = {"homologado": True, "interno": True}
        for campo in CAMPOS:
            if not v.get(campo):
                continue
            if campo == "curp" and v.get("pais") != "MEX":
                continue
            val_h = dh.get(HOM.get(campo, campo))
            if campo == "apellidos":
                val_h = " ".join(x for x in (dh.get("apellido_paterno"), dh.get("apellido_materno")) if x) or None
            val_i = di.get(INT.get(campo, campo))
            for modo, val in (("homologado", val_h), ("interno", val_i)):
                r, nota = igual(campo, v[campo], val)
                tot[modo][campo][r] += 1
                if r != "ok":
                    perfecto[modo] = False
                if r in ("falla", "parcial", "vacio"):
                    filas.append({"id": id_, "campo": campo, "modo": modo, "resultado": r, "verdad": v[campo],
                                  "api": val or "", "nota": nota or v.get("nota", ""),
                                  "mrz_integra": mrz.get("integra"), "confianza": conf.get(INT.get(campo, campo), ""),
                                  "codigo": hom.get("codigo")})
        for modo in perfecto:
            docs_perfectos[modo] += perfecto[modo]

    with open(out / "discrepancias.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "campo", "modo", "resultado", "verdad", "api", "nota", "mrz_integra",
                                           "confianza", "codigo"])
        w.writeheader()
        w.writerows(sorted(filas, key=lambda x: (x["modo"], x["campo"], x["id"])))

    n = len(verdad) - len(no_pasaporte)
    lines = [f"# Verdad de terreno: {len(verdad)} recortes, {n} pasaportes evaluados", ""]
    for modo in ("homologado", "interno"):
        lines.append(f"## {modo}")
        lines.append("| campo | evaluados | ok | parcial | falla | no entregado | exactitud |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        T = Counter()
        for campo in CAMPOS:
            c = tot[modo][campo]
            ev = sum(c.values())
            if not ev:
                continue
            T.update(c)
            lines.append(f"| {campo} | {ev} | {c['ok']} | {c['parcial']} | {c['falla']} | {c['vacio']} | {c['ok'] / ev:.1%} |")
        ev = sum(T.values())
        lines.append(f"| **total** | {ev} | {T['ok']} | {T['parcial']} | {T['falla']} | {T['vacio']} | **{T['ok'] / ev:.1%}** |")
        lines.append(f"\nDocumentos con todos los campos correctos: {docs_perfectos[modo]} de {n} ({docs_perfectos[modo] / n:.0%})\n")
    if no_pasaporte:
        lines.append("## Recortes que no eran pasaporte (según el capturista)")
        for x in no_pasaporte:
            lines.append(f"- {x[0]}: API codigo {x[1]}, categoria {x[2]}, estado interno {x[3]}")
    (out / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nDiscrepancias con valores: {out / 'discrepancias.csv'} ({len(filas)} filas)")


if __name__ == "__main__":
    main()
