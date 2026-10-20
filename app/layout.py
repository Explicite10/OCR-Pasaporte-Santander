"""Localiza la página de datos del pasaporte dentro de cada página escaneada.

El ancla es la MRZ TD3 (2 renglones de 44 caracteres al pie de la página de datos).
Con la posición y el ancho de la MRZ se estima el rectángulo de la página de datos
(proporción 125 x 88 mm) y se agrega un margen. Si en ninguna página aparece la MRZ,
se prueban los giros (90°, 180°, 270°) y después el pipeline puede pedir al modelo de
visión que ubique el pasaporte (`analyze_boxes`).

Los PDFs del lote traen además otros documentos (tarjeta de residente del INM con MRZ TD1,
sellos del banco...): se registran en `otros_documentos` pero no se extraen.
"""

import re
from dataclasses import dataclass, field

import cv2
import numpy as np

from . import mrz_td3
from .ocr import Line

PAGE_RATIO = 125.0 / 88.0  # ancho / alto de la página de datos (TD3)
MARGIN = 0.06
W_PER_MRZ = 1.06  # ancho de la página respecto al ancho de la MRZ
LEFT_OFFSET = 0.03  # fracción del ancho a la izquierda de la MRZ
BOTTOM_OFFSET = 0.05  # fracción del alto por debajo de la MRZ
CROP_MIN_WIDTH = 1200

_ROTATIONS = {90: cv2.ROTATE_90_CLOCKWISE, 180: cv2.ROTATE_180, 270: cv2.ROTATE_90_COUNTERCLOCKWISE}


@dataclass
class Box:
    x0: int
    y0: int
    x1: int
    y1: int

    def contains(self, x: float, y: float) -> bool:
        return self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1

    def clip(self, w: int, h: int) -> "Box":
        return Box(max(0, self.x0), max(0, self.y0), min(w, self.x1), min(h, self.y1))

    @property
    def area(self) -> int:
        return max(0, self.x1 - self.x0) * max(0, self.y1 - self.y0)


@dataclass
class Passport:
    page: int
    box: Box
    image: np.ndarray
    lines: list[Line]  # líneas OCR dentro del recorte, de arriba abajo
    method: str  # "ancla" | "localizador" | "pagina_completa"
    mrz_lines: list[str] = field(default_factory=list)


@dataclass
class Layout:
    passport: Passport | None
    rotated: bool
    pages: int
    warnings: list[str]
    page_lines: list[list[Line]] = field(default_factory=list)
    page_images: list[np.ndarray] = field(default_factory=list)
    otros_documentos: list[str] = field(default_factory=list)

    @property
    def anchored(self) -> bool:
        return bool(self.passport and self.passport.method == "ancla")


# ---------------------------------------------------------------- MRZ en el OCR


def _merge_rows(lines: list[Line]) -> list[Line]:
    """Une fragmentos de un mismo renglón (el OCR a veces parte la MRZ en 2 ó 3 cajas)."""
    horiz = sorted((l for l in lines if l.w >= l.h), key=lambda l: (l.cy, l.x0))
    rows: list[list[Line]] = []
    for l in horiz:
        for row in rows:
            ref = row[-1]
            if abs(l.cy - ref.cy) < 0.6 * max(l.h, ref.h) and l.x0 >= ref.x1 - 0.3 * ref.h:
                row.append(l)
                break
        else:
            rows.append([l])
    merged = []
    for row in rows:
        if len(row) == 1:
            merged.append(row[0])
            continue
        text = "".join(r.text for r in row)
        merged.append(Line(text, min(r.score for r in row), min(r.x0 for r in row), min(r.y0 for r in row),
                           max(r.x1 for r in row), max(r.y1 for r in row)))
    return merged


def _x_overlap(a: Line, b: Line) -> float:
    inter = min(a.x1, b.x1) - max(a.x0, b.x0)
    return inter / max(1, min(a.w, b.w))


def find_mrz(lines: list[Line]) -> list[Line] | None:
    """Las 2 líneas de la MRZ TD3 agrupadas geométricamente (o sólo la 2ª si la 1ª no se leyó)."""
    rows = _merge_rows(lines)
    l1 = next((l for l in rows if mrz_td3.looks_like_line1(l.text)), None)
    if l1 is not None:
        below = [l for l in rows if l is not l1 and 0.4 * l1.h < l.cy - l1.cy < 3.0 * l1.h
                 and _x_overlap(l, l1) > 0.5 and len(mrz_td3.clean(l.text)) >= 20]
        below.sort(key=lambda l: (not mrz_td3.looks_like_line2(l.text), l.cy))
        return [l1] + below[:1]
    l2 = next((l for l in rows if mrz_td3.looks_like_line2(l.text)), None)
    if l2 is None:
        return None
    above = [l for l in rows if l is not l2 and 0.4 * l2.h < l2.cy - l.cy < 3.0 * l2.h
             and _x_overlap(l, l2) > 0.5 and len(mrz_td3.clean(l.text)) >= 20]
    above.sort(key=lambda l: -l.cy)
    return (above[:1] or [Line("", 0, l2.x0, l2.y0 - l2.h, l2.x1, l2.y0)]) + [l2]


def has_td1(lines: list[Line]) -> bool:
    return any(mrz_td3.looks_like_td1(l.text) for l in _merge_rows(lines))


def _passport_box(mrz: list[Line]) -> Box:
    real = [l for l in mrz if l.text]
    x0 = min(l.x0 for l in real)
    x1 = max(l.x1 for l in real)
    y1 = max(l.y1 for l in real)
    if len(real) < 2:  # falta un renglón: el fondo queda corto
        y1 += int(1.3 * real[0].h)
    w = (x1 - x0) * W_PER_MRZ
    h = w / PAGE_RATIO
    left = x0 - LEFT_OFFSET * w
    bottom = y1 + BOTTOM_OFFSET * h
    return Box(int(left - MARGIN * w), int(bottom - h - MARGIN * h), int(left + w * (1 + MARGIN)),
               int(bottom + MARGIN * h))


def _lines_in(lines: list[Line], box: Box) -> list[Line]:
    return sorted((l for l in lines if box.contains(l.cx, l.cy)), key=lambda l: (l.cy, l.x0))


def _crop(img: np.ndarray, box: Box) -> np.ndarray:
    return img[box.y0:box.y1, box.x0:box.x1].copy()


def _locate(img: np.ndarray, lines: list[Line]) -> tuple[list[Line] | None, Box | None]:
    mrz = find_mrz(lines)
    if not mrz:
        return None, None
    h, w = img.shape[:2]
    box = _passport_box(mrz).clip(w, h)
    if box.area == 0:
        return None, None
    return mrz, box


def _mostly_vertical(lines: list[Line]) -> bool:
    long = [l for l in lines if len(l.text) >= 6]
    return sum(l.h > 1.5 * l.w for l in long) > sum(l.w > 1.5 * l.h for l in long)


def _locate_with_rotations(img: np.ndarray, lines: list[Line], ocr_read):
    """Busca la MRZ en la imagen y, si no está, en sus giros (90°, 180°, 270°)."""
    found = _locate(img, lines)
    if found[0] or not lines:
        return img, lines, found, False
    likely = [90, 270] if _mostly_vertical(lines) else [180]
    for deg in likely + [d for d in (90, 180, 270) if d not in likely]:
        r_img = cv2.rotate(img, _ROTATIONS[deg])
        r_lines = ocr_read(r_img)
        r = _locate(r_img, r_lines)
        if r[0]:
            return r_img, r_lines, r, True
    return img, lines, found, False


def analyze(pages: list[np.ndarray], ocr_read, all_pages: bool = False) -> Layout:
    """Busca la página de datos del pasaporte en las páginas. `ocr_read(img) -> list[Line]`.
    Con `all_pages=False` se deja de pasar el OCR en cuanto aparece el pasaporte."""
    passport: Passport | None = None
    warnings: list[str] = []
    rotated = False
    page_lines: list[list[Line]] = []
    page_images: list[np.ndarray] = []
    otros: list[str] = []

    for i, page in enumerate(pages):
        if passport is not None and (not all_pages or i >= 2):
            page_images.append(page)
            page_lines.append([])
            continue
        img, lines, (mrz, box), rot = _locate_with_rotations(page, ocr_read(page), ocr_read)
        rotated = rotated or rot
        page_images.append(img)
        page_lines.append(lines)
        if has_td1(lines) and "tarjeta_td1" not in otros:
            otros.append("tarjeta_td1")
        if passport is None and box:
            passport = Passport(i, box, _crop(img, box), _lines_in(lines, box), "ancla",
                                mrz_lines=[l.text for l in mrz])

    layout = Layout(passport, rotated, len(pages), warnings, page_lines, page_images, otros)
    _fill_missing(layout)
    return layout


def _fill_missing(layout: Layout) -> None:
    """Sin ancla: se manda la página completa al VLM para no perder el documento."""
    if layout.passport is None and layout.page_images:
        img, lines = layout.page_images[0], layout.page_lines[0]
        layout.passport = Passport(0, Box(0, 0, img.shape[1], img.shape[0]), img, lines, "pagina_completa")
        layout.warnings.append("No se localizó la MRZ del pasaporte; se analizó la página completa")


@dataclass
class CardBox:
    page: int
    box: Box
    rotacion: int = 0


def _box_sane(box: Box, w: int, h: int) -> bool:
    b = box.clip(w, h)
    frac = b.area / max(1, w * h)
    return 0.02 <= frac <= 0.95 and (b.x1 - b.x0) >= 80 and (b.y1 - b.y0) >= 50


def analyze_boxes(layout: Layout, cards: list[CardBox], ocr_read) -> Layout:
    """Reemplaza el pasaporte sin ancla por el recorte del localizador (enderezado y ampliado),
    y vuelve a buscar la MRZ ahí."""
    passport = layout.passport if layout.anchored else None
    fallback = None
    used = 0
    for card in cards:
        if passport:
            break
        if not (0 <= card.page < len(layout.page_images)):
            continue
        page = layout.page_images[card.page]
        h, w = page.shape[:2]
        if not _box_sane(card.box, w, h):
            continue
        crop = _crop(page, card.box.clip(w, h))
        if card.rotacion in _ROTATIONS:
            crop = cv2.rotate(crop, _ROTATIONS[card.rotacion])
        ch, cw = crop.shape[:2]
        if cw < CROP_MIN_WIDTH:
            scale = CROP_MIN_WIDTH / cw
            crop = cv2.resize(crop, (int(cw * scale), int(ch * scale)), interpolation=cv2.INTER_CUBIC)
        used += 1
        img, lines, (mrz, box), _ = _locate_with_rotations(crop, ocr_read(crop), ocr_read)
        layout.page_lines[card.page] = layout.page_lines[card.page] + lines
        if box:
            passport = Passport(card.page, box, _crop(img, box), _lines_in(lines, box), "ancla",
                                mrz_lines=[l.text for l in mrz])
        elif fallback is None:
            fallback = Passport(card.page, Box(0, 0, img.shape[1], img.shape[0]), img, lines, "localizador")
    layout.passport = passport or fallback
    layout.warnings = [w for w in layout.warnings if not w.startswith("No se localizó")]
    layout.warnings.append(f"Localizador: {len(cards)} caja(s), {used} usable(s), "
                           f"{'con' if passport else 'sin'} MRZ")
    _fill_missing(layout)
    return layout


def ocr_text_chars(page_lines: list[list[Line]]) -> int:
    return sum(len(re.sub(r"[^A-Z0-9]", "", l.text.upper())) for lines in page_lines for l in lines)
