"""Prueba de punta a punta del bloque validacion_plan contra la API desplegada.

Para cada PDF arma una solicitud con los datos de un lote anterior (carpeta json/ de
scripts.procesar_lote, valores ya verificados con la MRZ), llama a POST /pasaporte con esos datos y
guarda la respuesta. Después reevalúa el plan sin llamar a la API con solicitudes alteradas
(nombre incompleto, otra fecha, otra nacionalidad) para comprobar que también se rechazan.

    python -m scripts.probar_plan --api http://localhost:8000 --lote lote/res_v2 \\
        --pdfs lote/pdfs --archivos a.pdf,b.pdf --salida lote/res_plan

Sólo imprime conteos y motivos SIN valores entre comillas (pueden traer datos personales).
"""

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import plan  # noqa: E402


def solicitud_de(interno: dict) -> dict:
    d = interno.get("datos") or {}
    sol = {}
    nombre = " ".join(x for x in (d.get("nombres"), d.get("apellidos")) if x)
    if nombre:
        sol["nombre"] = nombre
    if d.get("fecha_nacimiento"):
        y, m, dd = d["fecha_nacimiento"].split("-")
        sol["fecha_nacimiento"] = f"{dd}/{m}/{y}"  # como la captura más común
    if d.get("nacionalidad"):
        sol["nacionalidad"] = d["nacionalidad"]
    if d.get("curp"):
        sol["curp"] = d["curp"]
    return sol


def alterar(sol: dict) -> list[tuple[str, dict]]:
    out = []
    if sol.get("nombre") and len(sol["nombre"].split()) > 1:
        out.append(("nombre", {**sol, "nombre": " ".join(sol["nombre"].split()[:-1])}))
    if sol.get("fecha_nacimiento"):
        d, m, y = sol["fecha_nacimiento"].split("/")
        out.append(("fecha", {**sol, "fecha_nacimiento": f"{d}/{m}/{int(y) - 1}"}))
    if sol.get("nacionalidad"):
        out.append(("nacionalidad", {**sol, "nacionalidad": "ARG" if sol["nacionalidad"] != "ARG" else "CHL"}))
    return out


def _sin_valores(s: str) -> str:
    s = re.sub(r"'[^']*'", "'…'", s)
    s = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "AAAA-MM-DD", s)
    return re.sub(r"(solicitud|tarjeta|pasaporte|pasaporte y no en la solicitud|solicitud y no en el pasaporte):[^.]*\.",
                  r"\1: ….", s)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--lote", required=True)
    ap.add_argument("--pdfs", required=True)
    ap.add_argument("--archivos", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--concurrencia", type=int, default=2)
    args = ap.parse_args()
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    key = os.environ.get("API_KEY", "")
    sem = asyncio.Semaphore(args.concurrencia)

    async def uno(cli: httpx.AsyncClient, nombre: str) -> None:
        dest = out / (Path(nombre).stem + ".json")
        if dest.exists():
            return
        interno = json.loads((Path(args.lote) / "json" / (Path(nombre).stem + ".json")).read_text(encoding="utf-8"))
        sol = solicitud_de(interno)
        async with sem:
            with open(Path(args.pdfs) / nombre, "rb") as fh:
                r = await cli.post(f"{args.api}/pasaporte", headers={"X-API-Key": key}, data=sol,
                                   files={"file": (nombre, fh.read(), "application/pdf")})
        dest.write_text(json.dumps({"solicitud": sol, "respuesta": r.json()}, ensure_ascii=False), encoding="utf-8")
        print(nombre, r.json().get("codigo"), (r.json().get("validacion_plan") or {}).get("cumple"), flush=True)

    async with httpx.AsyncClient(timeout=600) as cli:
        await asyncio.gather(*(uno(cli, n) for n in args.archivos.split(",")))

    cumple, por_codigo, fallas, rechazos_alterados, total_alterados = Counter(), Counter(), Counter(), Counter(), Counter()
    respaldo_mrz = Counter()
    for f in sorted(out.glob("*.json")):
        x = json.loads(f.read_text(encoding="utf-8"))
        r, sol = x["respuesta"], x["solicitud"]
        vp = r.get("validacion_plan")
        por_codigo[r.get("codigo")] += 1
        if not vp:
            continue
        cat = r["clasificacion"]["categoria"]
        cumple[(cat, vp["cumple"])] += 1
        for i in vp["validaciones"]:
            if not i["ok"]:
                fallas[f"{i['id']}={i['resultado']}: {_sin_valores(i['detalle'])}"] += 1
            if i["resultado"] == "SI" and "según la MRZ" in i["detalle"]:
                respaldo_mrz[i["id"]] += 1
        if cat == "pasaporte":
            for tipo, mala in alterar(sol):
                total_alterados[tipo] += 1
                ev = plan.evaluar(cat, r.get("datos"), r.get("mrz"), plan.Solicitud(**mala))
                rechazos_alterados[tipo] += not ev["cumple"]

    print("\nCódigos:", dict(sorted(por_codigo.items(), key=lambda x: str(x[0]))))
    print("Plan con la solicitud correcta (categoria, cumple):", dict(cumple))
    print("Validaciones que pasaron gracias a la MRZ:", dict(respaldo_mrz))
    print("Validaciones que no pasaron con la solicitud correcta:")
    for k, n in fallas.most_common():
        print(f"  {n:3d}  {k}")
    print("Solicitudes alteradas rechazadas (debe ser 100 %):")
    for t in total_alterados:
        print(f"  {t}: {rechazos_alterados[t]} de {total_alterados[t]}")


if __name__ == "__main__":
    asyncio.run(main())
