"""Sello de cotejo de Santander ("COTEJADO CONTRA ORIGINAL", con FECHA, REVISÓ y clave del revisor).

El texto impreso del sello lo encuentra el OCR; alrededor de esa línea se recorta una zona holgada
(medida sobre el lote: FECHA queda a la izquierda y abajo, REVISÓ a la derecha y abajo, el logo
encima) y el modelo de visión lee lo escrito a mano o estampado.
"""

import re
from dataclasses import dataclass
from datetime import date

import cv2
import numpy as np

from . import validators as v
from .ocr import Line

# Recorte en unidades del ancho de la línea "COTEJADO CONTRA ORIGINAL", desde su centro
CROP_X = 1.0
CROP_UP = 0.5
CROP_DOWN = 0.9
CROP_MIN_WIDTH = 1200


def _norm(t: str) -> str:
    return re.sub(r"[^A-Z]", "", v.strip_accents(t.upper()))


def is_anchor(text: str) -> bool:
    u = _norm(text)
    return "COTEJAD" in u or "CONTRAORIGINAL" in u


def find_anchor(lines: list[Line]) -> Line | None:
    return next((l for l in lines if is_anchor(l.text) and l.w > 0), None)


def crop(img: np.ndarray, anchor: Line) -> np.ndarray:
    h, w = img.shape[:2]
    aw = anchor.w
    x0, x1 = int(max(0, anchor.cx - CROP_X * aw)), int(min(w, anchor.cx + CROP_X * aw))
    y0, y1 = int(max(0, anchor.cy - CROP_UP * aw)), int(min(h, anchor.cy + CROP_DOWN * aw))
    out = img[y0:y1, x0:x1].copy()
    if out.size and out.shape[1] < CROP_MIN_WIDTH:
        s = CROP_MIN_WIDTH / out.shape[1]
        out = cv2.resize(out, (int(out.shape[1] * s), int(out.shape[0] * s)), interpolation=cv2.INTER_CUBIC)
    return out


# ---------------------------------------------------------------- interpretación de lo leído

_NUM_DATE = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})")


def parse_fecha(raw: str | None) -> date | None:
    """Fecha de un sello: DD/MM/AAAA, DD/MM/AA, DD.MM.AAAA, '24 ABR 2026'... Sólo fechas reales y plausibles."""
    if not raw or not raw.strip():
        return None
    s = raw.strip().upper()
    s = re.sub(r"(?<=\b\d) (?=\d\b)", "", s)  # fechador con dígitos espaciados: "2 4 JUL 2026"
    d = None
    compacto = re.fullmatch(r"\d{6}|\d{8}", s.replace(" ", ""))
    if compacto:  # DDMMAAAA o DDMMAA sin separadores
        t = compacto.group(0)
        y = int(t[4:]) + (2000 if len(t) == 6 else 0)
        try:
            d = date(y, int(t[2:4]), int(t[0:2]))
        except ValueError:
            d = None
    m = None if d else _NUM_DATE.fullmatch(s.strip(" ."))
    if m:
        y = int(m[3])
        if y < 100:
            y += 2000
        try:
            d = date(y, int(m[2]), int(m[1]))
        except ValueError:
            d = None
    if d is None and re.search(r"[A-Z]{3}", s):  # con mes en letras: "24 ABR 2026"
        d = v.parse_date(s)
    if d is None or not (2000 <= d.year <= date.today().year + 1):
        return None
    return d


_CLAVE = re.compile(r"^[A-Z]\d{5,7}$")


def parse_clave(raw: str | None) -> str | None:
    """Una letra + 5 a 7 dígitos. El OCR confunde la S inicial con $ o 5: se corrige."""
    if not raw:
        return None
    s = re.sub(r"[\s\-._/]", "", raw.upper())
    if s and s[0] in "$5" and 5 <= len(s) - 1 <= 7 and s[1:].isdigit():
        s = "S" + s[1:]
    return s if _CLAVE.match(s) else None


def limpiar_texto(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip(" -,:;.")
    return s or None


@dataclass
class SelloInterpretado:
    presente: bool
    campos: dict  # fecha (ISO), reviso, clave_revisor: sólo los válidos
    ausentes: list[str]  # campos que el sello no trae
    avisos: list[str]


def interpretar(lectura: dict | None) -> SelloInterpretado:
    """De la lectura cruda del VLM a lo que pide el contrato (sección 5 de la homologación)."""
    if not lectura:
        return SelloInterpretado(False, {}, [], [])
    raw = {k: limpiar_texto(lectura.get(k) if isinstance(lectura.get(k), str) else None)
           for k in ("fecha", "reviso", "clave_revisor")}
    presente = bool(lectura.get("presente")) or any(raw.values())
    if not presente:
        return SelloInterpretado(False, {}, [], [])
    campos, ausentes, avisos = {}, [], []
    if raw["fecha"] is None:
        ausentes.append("fecha")
    else:
        f = parse_fecha(raw["fecha"])
        if f:
            campos["fecha"] = f.isoformat()
        else:
            avisos.append(f"sello.fecha ilegible: se leyó '{raw['fecha']}'")
    if raw["reviso"] is None:
        ausentes.append("reviso")
    else:
        campos["reviso"] = raw["reviso"]
    if raw["clave_revisor"] is None:
        ausentes.append("clave_revisor")
    else:
        c = parse_clave(raw["clave_revisor"])
        if c:
            campos["clave_revisor"] = c
        else:
            avisos.append(f"sello.clave_revisor sin forma de clave: se leyó '{raw['clave_revisor']}'")
    ordered = {k: campos[k] for k in ("fecha", "reviso", "clave_revisor") if k in campos}
    return SelloInterpretado(True, ordered, ausentes, avisos)
