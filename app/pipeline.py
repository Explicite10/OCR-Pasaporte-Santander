"""Orquestación: archivo -> páginas -> OCR + localización por MRZ -> VLM -> fusión -> JSON."""

import asyncio
import base64
import logging
import time

import cv2
import numpy as np

from . import mrz_td3
from .config import get_settings
from .documents import DocumentError, encode_png, load_pages
from .layout import Box, CardBox, Layout, analyze, analyze_boxes, ocr_text_chars
from .merge import CRITICAL_FIELDS, Merger, needs_review
from .ocr import engine
from .schemas import Meta, ResultadoPasaporte
from .vlm import MRZ_PROMPT, MRZ_SCHEMA, VIZ_PROMPT, VIZ_SCHEMA, VlmClient, VlmError

log = logging.getLogger(__name__)

MIN_CARACTERES_OCR = 10


def _ms(t: float) -> int:
    return int(t * 1000)


def _meta(s, times, t_start, layout: Layout, mrz_source, vlm, caracteres, categoria=None) -> Meta:
    return Meta(
        tiempo_total_ms=_ms(time.perf_counter() - t_start), tiempos_ms=times,
        modelo_vlm=s.vlm_model if vlm is not None and s.vlm_enabled else None,
        paginas=layout.pages, pagina_pasaporte=layout.passport.page + 1 if layout.passport else None,
        rotado=layout.rotated, recorte=layout.passport.method if layout.passport else None,
        mrz_fuente=mrz_source, otros_documentos=layout.otros_documentos, caracteres_leidos=caracteres,
        categoria=categoria,
    )


def _mrz_strip(img: np.ndarray) -> np.ndarray:
    """Franja inferior del recorte (donde va la MRZ), ampliada para que el VLM la lea mejor."""
    h, w = img.shape[:2]
    strip = img[int(h * 0.70):h, :]
    if w < 1800:
        scale = 1800 / w
        strip = cv2.resize(strip, (int(w * scale), int(strip.shape[0] * scale)), interpolation=cv2.INTER_CUBIC)
    return strip


async def process(files: list[bytes], vlm: VlmClient | None, filename: str | None = None,
                  include_crops: bool = False) -> ResultadoPasaporte:
    s = get_settings()
    t_start = time.perf_counter()
    times: dict[str, int] = {}

    # 1. Páginas
    t = time.perf_counter()
    try:
        pages: list[np.ndarray] = []
        for data in files:
            pages += await asyncio.to_thread(load_pages, data, s.render_dpi, s.max_pages, s.max_paginas_documento)
    except DocumentError as e:
        return ResultadoPasaporte(archivo=filename, estado="error", error=str(e), error_codigo=e.codigo,
                                  meta=Meta(tiempo_total_ms=_ms(time.perf_counter() - t_start)))
    times["render"] = _ms(time.perf_counter() - t)

    # 2. OCR + localización por MRZ
    t = time.perf_counter()
    ocr_read = engine.read if s.ocr_enabled else (lambda img: [])
    layout: Layout = await asyncio.to_thread(analyze, pages, ocr_read, s.ocr_todas_las_paginas)
    times["ocr_y_recorte"] = _ms(time.perf_counter() - t)
    vlm_on = vlm is not None and s.vlm_enabled

    texto = ocr_text_chars(layout.page_lines)
    if s.rechazar_no_pasaporte and s.ocr_enabled and texto < MIN_CARACTERES_OCR:
        motivo = "No es un pasaporte: el documento está en blanco o no tiene texto legible"
        return ResultadoPasaporte(archivo=filename, estado="rechazado", error=motivo, advertencias=list(layout.warnings),
                                  meta=_meta(s, times, t_start, layout, None, vlm, texto, "hoja_en_blanco"))

    # 2b. Sin MRZ en ninguna página: el VLM ubica el pasaporte y se repite el OCR en el recorte
    if vlm_on and s.vlm_localizador and s.ocr_enabled and not layout.anchored:
        t = time.perf_counter()
        try:
            cards: list[CardBox] = []
            for i, page in enumerate(layout.page_images[:2]):
                found, _ = await vlm.locate(page)
                cards += [CardBox(i, Box(*c["bbox_2d"]), c["rotacion"]) for c in found]
                if cards:
                    break
            if cards:
                layout = await asyncio.to_thread(analyze_boxes, layout, cards, ocr_read)
            else:
                layout.warnings.append("El localizador no vio ningún pasaporte en la página")
        except VlmError as e:
            log.error("Localizador falló: %s", e)
            layout.warnings.append("El localizador falló; se analizó la página completa")
        times["localizacion_vlm"] = _ms(time.perf_counter() - t)
    warnings = list(layout.warnings)
    passport = layout.passport

    ocr_mrz = mrz_td3.parse(passport.mrz_lines) if passport and passport.mrz_lines else None

    # 3. VLM: lectura visual de la página de datos (incluye su propia lectura de la MRZ)
    vlm_viz: dict | None = None
    vlm_mrz = None
    if vlm_on and passport is not None:
        try:
            vlm_viz, secs = await vlm.extract(passport.image, VIZ_PROMPT, VIZ_SCHEMA)
            times["vlm_pasaporte"] = _ms(secs)
            vlm_mrz = mrz_td3.parse([vlm_viz.get("mrz_linea1") or "", vlm_viz.get("mrz_linea2") or ""])
        except VlmError as e:
            log.error("VLM falló: %s", e)
            warnings.append("El modelo de visión falló; se usó sólo OCR")
        # 3b. Ninguna MRZ íntegra: segunda lectura del VLM sobre la franja de la MRZ ampliada
        if not ((ocr_mrz and ocr_mrz.integra) or (vlm_mrz and vlm_mrz.integra)) and passport.method != "pagina_completa":
            try:
                data, secs = await vlm.extract(_mrz_strip(passport.image), MRZ_PROMPT, MRZ_SCHEMA, max_side=2000)
                times["vlm_mrz"] = _ms(secs)
                vlm_mrz = mrz_td3.best(vlm_mrz, mrz_td3.parse([data.get("mrz_linea1") or "", data.get("mrz_linea2") or ""]))
            except VlmError as e:
                log.error("VLM (MRZ) falló: %s", e)
    elif not vlm_on:
        warnings.append("VLM deshabilitado: resultados sólo con OCR")

    chosen = mrz_td3.best(ocr_mrz, vlm_mrz)
    mrz_source = None
    if chosen is not None:
        mrz_source = "ocr" if chosen is ocr_mrz else "vlm"
        other = vlm_mrz if chosen is ocr_mrz else ocr_mrz
        if other is not None and other.integra and chosen.integra and other.numero != chosen.numero:
            warnings.append("OCR y VLM leyeron MRZ íntegras pero distintas")

    # 4. Fusión y validación
    merger = Merger(vlm_viz, chosen, [l.text for l in passport.lines] if passport else [])
    datos = merger.run()
    warnings += merger.warnings
    review = needs_review(merger.conf)
    critical_bad = [f for f in review if f in CRITICAL_FIELDS]
    estado = "revisar" if critical_bad or not (chosen and chosen.integra) else "ok"
    if vlm_viz is None and vlm_on:
        estado = "revisar"

    meta = _meta(s, times, t_start, layout, mrz_source, vlm, texto, "pasaporte")

    # 5. ¿De verdad es un pasaporte? Sin MRZ con algún dígito verificador válido y sin número ni
    #    nombre leídos por el VLM, no hay datos de pasaporte.
    mrz_real = chosen is not None and chosen.n_validos > 0 and chosen.numero is not None
    # Sin ningún dígito verificador que cuadre, la lectura visual sólo vale si su MRZ empieza como
    # la de un pasaporte (P + país ICAO): ante una tarjeta del INM el VLM "lee" un pasaporte que no está.
    vlm_l1_ok = bool(mrz_td3.line1_country(vlm_mrz.lineas[0])) if vlm_mrz else False
    vlm_real = vlm_viz is not None and bool(datos.numero_pasaporte) and bool(datos.apellidos) and vlm_l1_ok
    if s.rechazar_no_pasaporte and not mrz_real and not vlm_real and (vlm_viz is not None or not vlm_on):
        meta.categoria = "otro"
        if "tarjeta_td1" in layout.otros_documentos:
            meta.documento_detectado = "tarjeta_residente_inm"
            motivo = ("No se reconoció un pasaporte: el documento trae una tarjeta de residente (MRZ TD1) "
                      "pero no la página de datos de un pasaporte")
        else:
            motivo = "No se reconoció un pasaporte: sin MRZ válida y sin número de pasaporte ni nombre legibles"
        return ResultadoPasaporte(archivo=filename, estado="rechazado", error=motivo, advertencias=warnings, meta=meta)

    result = ResultadoPasaporte(archivo=filename, estado=estado, datos=datos, confianza=merger.conf,
                                campos_a_revisar=review, validaciones=merger.checks, advertencias=warnings, meta=meta)
    if include_crops and passport is not None:
        result.recortes = {"pasaporte": base64.b64encode(encode_png(passport.image, 1400)).decode()}
    return result
