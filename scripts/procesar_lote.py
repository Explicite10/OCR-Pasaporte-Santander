"""Procesa una carpeta de PDFs con pasaportes y genera JSON, CSV y un resumen.

Ejemplos:
    python -m scripts.procesar_lote lote/pdfs --salida lote/resultados --concurrencia 2
    python -m scripts.procesar_lote lote/pdfs --salida lote/resultados --limite 30 --recortes
    python -m scripts.procesar_lote --salida lote/resultados --solo-resumen

Es reanudable: si se interrumpe, al volver a correrlo salta los archivos que ya tienen JSON
(usa --forzar para reprocesar). Con --modelo se cambia el VLM (para comparar modelos).
"""

import argparse
import asyncio
import base64
import csv
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXTS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
CONF_FIELDS = ["numero_pasaporte", "apellidos", "nombres", "fecha_nacimiento", "fecha_vencimiento", "sexo",
               "pais_emisor", "nacionalidad", "fecha_expedicion", "lugar_nacimiento", "autoridad", "curp"]


def flatten(r: dict) -> dict:
    d = r.get("datos") or {}
    mrz = d.get("mrz") or {}
    conf = r.get("confianza") or {}
    checks = {c["regla"]: c["resultado"] for c in r.get("validaciones") or []}
    meta = r.get("meta") or {}
    row = {"archivo": r.get("archivo"), "estado": r.get("estado"), "codigo_api": None,
           "campos_a_revisar": ";".join(r.get("campos_a_revisar") or [])}
    for f in CONF_FIELDS:
        row[f] = d.get(f)
    row.update({
        "pais_emisor_nombre": d.get("pais_emisor_nombre"), "nombre_completo": d.get("nombre_completo"),
        "mrz_integra": mrz.get("integra"), "mrz_fuente": meta.get("mrz_fuente"),
        "mrz_linea1": (mrz.get("lineas") or [None])[0], "mrz_linea2": (mrz.get("lineas") or [None, None])[1],
        "error": r.get("error"),
        **{f"conf_{f}": conf.get(f) for f in CONF_FIELDS},
        **{f"val_{k}": v for k, v in checks.items()},
        "recorte": meta.get("recorte"), "rotado": meta.get("rotado"), "pagina": meta.get("pagina_pasaporte"),
        "otros_documentos": ";".join(meta.get("otros_documentos") or []),
        "tiempo_ms": meta.get("tiempo_total_ms"),
        **{f"t_{k}": v for k, v in (meta.get("tiempos_ms") or {}).items()},
    })
    try:
        from app import respuesta
        from app.schemas import ResultadoPasaporte
        row["codigo_api"] = respuesta.construir(ResultadoPasaporte.model_validate(r))["codigo"]
    except Exception:  # noqa: BLE001
        pass
    return row


PERSONAL = {"numero_pasaporte", "apellidos", "nombres", "fecha_nacimiento", "nombre_completo", "curp",
            "lugar_nacimiento", "mrz_linea1", "mrz_linea2", "fecha_expedicion", "fecha_vencimiento"}


def diagnostico(row: dict) -> dict:
    """Fila sin datos personales (para compartir y analizar mejoras)."""
    return {k: v for k, v in row.items() if k not in PERSONAL}


async def run(args: argparse.Namespace) -> None:
    if args.modelo:
        os.environ["VLM_MODEL"] = args.modelo
    if args.formato:
        os.environ["VLM_FORMATO"] = args.formato
    from app import pipeline
    from app.config import get_settings
    from app.ocr import engine
    from app.vlm import VlmClient

    s = get_settings()
    out = Path(args.salida)
    (out / "json").mkdir(parents=True, exist_ok=True)
    if args.recortes:
        (out / "recortes").mkdir(exist_ok=True)

    if not args.solo_resumen:
        files = sorted(p for p in Path(args.carpeta).iterdir() if p.suffix.lower() in EXTS)
        if args.limite:
            files = files[:args.limite]
        pending = [f for f in files if args.forzar or not (out / "json" / f"{f.stem}.json").exists()]
        print(f"{len(files)} archivos, {len(pending)} por procesar · VLM {s.vlm_model} ({s.vlm_backend}, {s.vlm_formato})")
        if s.ocr_enabled:
            await asyncio.to_thread(engine.warmup)
        vlm = VlmClient(s) if s.vlm_enabled else None
        sem = asyncio.Semaphore(args.concurrencia)
        done = 0
        t0 = time.time()

        async def one(f: Path) -> None:
            nonlocal done
            async with sem:
                try:
                    r = await pipeline.process([f.read_bytes()], vlm, f.name, include_crops=args.recortes)
                    data = r.model_dump(mode="json")
                except Exception as e:  # noqa: BLE001
                    data = {"archivo": f.name, "estado": "error", "error": f"{type(e).__name__}: {e}"}
                if args.recortes and data.get("recortes"):
                    for name, b64 in data.pop("recortes").items():
                        (out / "recortes" / f"{f.stem}_{name}.png").write_bytes(base64.b64decode(b64))
                (out / "json" / f"{f.stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                done += 1
                print(f"[{done}/{len(pending)}] {f.name}: {data.get('estado')} "
                      f"({(data.get('meta') or {}).get('tiempo_total_ms', '?')} ms) · {time.time() - t0:.0f} s", flush=True)

        await asyncio.gather(*(one(f) for f in pending))
        if vlm:
            await vlm.aclose()

    reportes(out)


def reportes(out: Path) -> None:
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((out / "json").glob("*.json"))]
    if not results:
        print("Sin resultados")
        return
    rows = [flatten(r) for r in results]
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out / "resultados.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    diag = [diagnostico(r) for r in rows]
    with open(out / "diagnostico.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=[k for k in keys if k not in PERSONAL])
        w.writeheader()
        w.writerows(diag)

    n = len(results)
    estados = Counter(r.get("estado") for r in results)
    codigos = Counter(r["codigo_api"] for r in rows)
    paises = Counter(r.get("pais_emisor") for r in rows)
    conf = {f: Counter(r.get(f"conf_{f}") for r in rows) for f in CONF_FIELDS}
    fallas = Counter(k[4:] for r in rows for k, v in r.items() if k.startswith("val_") and v == "falla")
    mrz_int = sum(1 for r in rows if r.get("mrz_integra"))
    mrz_src = Counter(r.get("mrz_fuente") for r in rows)
    recorte = Counter(r.get("recorte") for r in rows)
    tiempos = [r["tiempo_ms"] for r in rows if r.get("tiempo_ms")]
    etapas = Counter()
    for r in rows:
        for k, v in r.items():
            if k.startswith("t_") and isinstance(v, int):
                etapas[k[2:]] += v
    modelo = next((r.get("meta", {}).get("modelo_vlm") for r in results if r.get("meta")), None)

    lines = [f"# Resumen del lote ({n} documentos) · VLM: {modelo}", ""]
    lines.append("## Estados")
    lines += [f"- {k}: {v} ({v / n:.1%})" for k, v in estados.most_common()]
    lines += ["", "## Código de la API"] + [f"- {k}: {v} ({v / n:.1%})" for k, v in sorted(codigos.items(), key=lambda x: str(x[0]))]
    lines += ["", f"## MRZ íntegra (todos los dígitos verificadores): {mrz_int} ({mrz_int / n:.1%})",
              f"- fuente: {dict(mrz_src)}", f"- recorte: {dict(recorte)}"]
    lines += ["", "## Países emisores"] + [f"- {k}: {v}" for k, v in paises.most_common()]
    lines += ["", "## Confianza por campo (alta / media / baja / vacío)"]
    for f, c in conf.items():
        lines.append(f"- {f}: {c.get('alta', 0)} / {c.get('media', 0)} / {c.get('baja', 0)} / {c.get(None, 0)}")
    lines += ["", "## Validaciones que más fallan"] + [f"- {k}: {v}" for k, v in fallas.most_common(15)]
    if tiempos:
        lines += ["", "## Tiempos", f"- mediana por documento: {statistics.median(tiempos) / 1000:.1f} s",
                  f"- promedio: {statistics.mean(tiempos) / 1000:.1f} s · máximo: {max(tiempos) / 1000:.1f} s"]
        lines += [f"- {k}: {v / n / 1000:.1f} s/doc" for k, v in etapas.most_common()]
    errores = [(r["archivo"], r.get("error")) for r in rows if r.get("estado") in ("error", "rechazado")]
    if errores:
        lines += ["", "## Errores y rechazos"] + [f"- {a}: {e}" for a, e in errores[:40]]
    (out / "resumen.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", nargs="?", help="Carpeta con PDFs")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--concurrencia", type=int, default=2)
    ap.add_argument("--limite", type=int)
    ap.add_argument("--forzar", action="store_true")
    ap.add_argument("--recortes", action="store_true", help="Guardar el recorte del pasaporte (PNG)")
    ap.add_argument("--solo-resumen", action="store_true")
    ap.add_argument("--modelo", help="Nombre del modelo VLM (sobrescribe VLM_MODEL)")
    ap.add_argument("--formato", choices=["schema", "plantilla"], help="Sobrescribe VLM_FORMATO")
    args = ap.parse_args()
    if not args.solo_resumen and not args.carpeta:
        ap.error("falta la carpeta de PDFs")
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
