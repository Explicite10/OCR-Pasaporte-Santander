"""Fusión de las fuentes (MRZ con dígitos verificadores vs. lectura visual del VLM) y validaciones.

Regla de confianza (igual que en el proyecto de INE):
  alta  = dos fuentes independientes coinciden, o lo respalda un dígito verificador
  media = una sola fuente con estructura válida
  baja  = las fuentes se contradicen o no se pudo leer
"""

from dataclasses import dataclass, field
from datetime import date

from . import validators as v
from .mrz_td3 import MrzTD3
from .schemas import DatosPasaporte, Mrz, Validacion

CRITICAL_FIELDS = {"numero_pasaporte", "apellidos", "nombres", "fecha_nacimiento", "fecha_vencimiento",
                   "pais_emisor"}

_SEX = {"M": "M", "H": "M", "F": "F", "X": "X", "MASCULINO": "M", "FEMENINO": "F", "MALE": "M", "FEMALE": "F",
        "HOMBRE": "M", "MUJER": "F"}


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _s(d: dict | None, k: str) -> str:
    val = (d or {}).get(k)
    return val.strip() if isinstance(val, str) else ""


@dataclass
class Merger:
    vlm: dict | None
    mrz: MrzTD3 | None
    ocr_texts: list[str] = field(default_factory=list)  # líneas OCR del recorte (fuente extra para la CURP)
    conf: dict[str, str] = field(default_factory=dict)
    checks: list[Validacion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ------------------------------------------------------------ helpers
    def _check(self, regla: str, ok: bool | None, detalle: str | None = None) -> None:
        self.checks.append(Validacion(regla=regla, resultado="no_aplica" if ok is None else ("ok" if ok else "falla"),
                                      detalle=detalle))

    def _mrz_ok(self, nombre: str) -> bool:
        return bool(self.mrz) and any(c.nombre == nombre and c.valido for c in self.mrz.checks)

    def _mrz_fuerte(self, nombre: str) -> bool:
        """El dato lo respaldan su dígito verificador Y el compuesto: una lectura visual distinta
        es casi seguro error del VLM, no del documento."""
        return self._mrz_ok(nombre) and self._mrz_ok("mrz_compuesto")

    # ------------------------------------------------------------ run
    def run(self) -> DatosPasaporte:
        d = DatosPasaporte()
        m = self.mrz
        vlm = self.vlm or {}

        if m is not None:
            for c in m.checks:
                self._check(c.nombre, c.valido, "corregido con el dígito verificador" if c.corregido else None)
            d.mrz = Mrz(
                lineas=m.lineas, tipo_documento=m.tipo_documento, pais_emisor=m.pais_emisor, numero=m.numero,
                nacionalidad=m.nacionalidad, fecha_nacimiento=_iso(m.fecha_nacimiento), sexo=m.sexo,
                fecha_vencimiento=_iso(m.fecha_vencimiento), apellidos=m.apellidos, nombres=m.nombres,
                opcional=m.opcional, digitos_control={c.nombre.removeprefix("mrz_"): c.valido for c in m.checks},
                integra=m.integra,
            )
        else:
            self._check("mrz_legible", False, "no se encontró una MRZ legible")

        # --- país emisor / tipo
        mrz_pais = m.pais_emisor if m else None
        vlm_pais = v.norm_code(_s(vlm, "pais_emisor"))[:3] or None
        if mrz_pais and mrz_pais not in v.ICAO_CODES:
            # La línea 1 no tiene dígito verificador: un código que no existe es error de lectura.
            alterno = vlm_pais if vlm_pais in v.ICAO_CODES else (m.nacionalidad if m.nacionalidad in v.ICAO_CODES else None)
            if alterno:
                self.warnings.append(f"País emisor de la MRZ ilegible ({mrz_pais}); se usó {alterno}")
                d.pais_emisor = alterno
                self.conf["pais_emisor"] = "media"
                mrz_pais = None
                vlm_pais = None
        if mrz_pais and len(mrz_pais) == 3:
            d.pais_emisor = mrz_pais
            if vlm_pais and vlm_pais != mrz_pais:
                self._check("pais_emisor_mrz_vs_impreso", False, f"MRZ {mrz_pais} / impreso {vlm_pais}")
                self.conf["pais_emisor"] = "media"
            else:
                self.conf["pais_emisor"] = "alta" if vlm_pais else "media"
        elif vlm_pais:
            d.pais_emisor = vlm_pais
            self.conf["pais_emisor"] = "media"
        elif d.pais_emisor is None:
            self.conf["pais_emisor"] = "baja"
        d.pais_emisor_nombre = v.PAISES.get(d.pais_emisor or "", None)
        d.tipo_documento = (m.tipo_documento if m and m.tipo_documento else None) or _s(vlm, "tipo_documento").upper()[:2] or None

        # --- número de pasaporte (dígito verificador en la MRZ)
        mrz_num = m.numero if m else None
        vlm_num = v.norm_code(_s(vlm, "numero_pasaporte")) or None
        if self._mrz_ok("mrz_numero") and mrz_num:
            d.numero_pasaporte = mrz_num
            if vlm_num and vlm_num != mrz_num and self._mrz_fuerte("mrz_numero"):
                self._check("numero_pasaporte_mrz_vs_impreso", True, f"lectura visual {vlm_num} descartada: la MRZ cuadra")
                self.warnings.append(f"El número de pasaporte se tomó de la MRZ (la lectura visual decía {vlm_num})")
                self.conf["numero_pasaporte"] = "alta"
            elif vlm_num and vlm_num != mrz_num:
                self._check("numero_pasaporte_mrz_vs_impreso", False, f"MRZ {mrz_num} / impreso {vlm_num}")
                self.conf["numero_pasaporte"] = "media"
            else:
                self._check("numero_pasaporte_mrz_vs_impreso", True if vlm_num else None)
                self.conf["numero_pasaporte"] = "alta"
        elif vlm_num and mrz_num and vlm_num == mrz_num:
            d.numero_pasaporte = vlm_num
            self._check("numero_pasaporte_mrz_vs_impreso", True)
            self.conf["numero_pasaporte"] = "alta"
        elif vlm_num or mrz_num:
            d.numero_pasaporte = vlm_num or mrz_num
            if vlm_num and mrz_num:
                self._check("numero_pasaporte_mrz_vs_impreso", False, f"MRZ {mrz_num} / impreso {vlm_num}")
            self.conf["numero_pasaporte"] = "baja" if (vlm_num and mrz_num) else "media"
        else:
            self.conf["numero_pasaporte"] = "baja"

        # --- apellidos y nombres (sin dígito verificador: se cruzan MRZ y lectura visual)
        mrz_integra = bool(m and m.integra)
        for campo in ("apellidos", "nombres"):
            mrz_val = _clean_name(getattr(m, campo)) if m else None
            vlm_val = _clean_name(_s(vlm, campo).upper()) or None
            if vlm_val and mrz_val:
                sim = v.similarity(vlm_val, mrz_val)
                tv, tm = set(v.norm_text(vlm_val).split()), set(v.norm_text(mrz_val).split())
                prefijo = v.norm_text(vlm_val).replace(" ", "").startswith(v.norm_text(mrz_val).replace(" ", ""))
                if sim >= 0.85 or (prefijo and len(mrz_val) >= 6):
                    setattr(d, campo, vlm_val)  # conserva Ñ y acentos
                    self._check(f"{campo}_mrz_vs_impreso", True)
                    self.conf[campo] = "alta"
                elif tv and tm and (tv <= tm or tm <= tv) and mrz_integra:
                    # Una lectura trae más palabras que la otra (apellido compuesto, segundo nombre):
                    # manda la MRZ íntegra; se avisa.
                    setattr(d, campo, mrz_val if tv < tm else vlm_val)
                    self._check(f"{campo}_mrz_vs_impreso", True, f"palabras de más/menos: MRZ '{mrz_val}' / impreso '{vlm_val}'")
                    self.warnings.append(f"{campo}: MRZ '{mrz_val}' e impreso '{vlm_val}' difieren en palabras; se usó el más completo")
                    self.conf[campo] = "media"
                else:
                    setattr(d, campo, mrz_val if mrz_integra else vlm_val)
                    self._check(f"{campo}_mrz_vs_impreso", False, f"MRZ '{mrz_val}' / impreso '{vlm_val}'")
                    self.conf[campo] = "baja"
            elif vlm_val or mrz_val:
                setattr(d, campo, vlm_val or mrz_val)
                self.conf[campo] = "media"
            else:
                self.conf[campo] = "baja"
        if d.apellidos or d.nombres:
            d.nombre_completo = " ".join(x for x in (d.nombres, d.apellidos) if x)

        # --- fechas con dígito verificador
        for campo, mrz_attr, chk in (("fecha_nacimiento", "fecha_nacimiento", "mrz_fecha_nacimiento"),
                                     ("fecha_vencimiento", "fecha_vencimiento", "mrz_vencimiento")):
            mrz_date = getattr(m, mrz_attr) if m else None
            vlm_date = v.parse_date(_s(vlm, campo))
            if self._mrz_ok(chk) and mrz_date:
                setattr(d, campo, _iso(mrz_date))
                if vlm_date and vlm_date != mrz_date and _swapped(vlm_date, mrz_date):
                    # El pasaporte imprime DD/MM y el VLM lo leyó MM/DD: misma fecha
                    vlm_date = mrz_date
                if vlm_date and vlm_date != mrz_date and self._mrz_fuerte(chk):
                    self._check(f"{campo}_mrz_vs_impresa", True, f"lectura visual {vlm_date} descartada: la MRZ cuadra")
                    self.warnings.append(f"{campo} tomada de la MRZ (la lectura visual decía {vlm_date})")
                    self.conf[campo] = "alta"
                elif vlm_date and vlm_date != mrz_date:
                    self._check(f"{campo}_mrz_vs_impresa", False, f"MRZ {mrz_date} / impresa {vlm_date}")
                    self.conf[campo] = "media"
                else:
                    self._check(f"{campo}_mrz_vs_impresa", True if vlm_date else None)
                    self.conf[campo] = "alta"
            elif vlm_date and mrz_date and vlm_date == mrz_date:
                setattr(d, campo, _iso(vlm_date))
                self._check(f"{campo}_mrz_vs_impresa", True)
                self.conf[campo] = "alta"
            elif vlm_date or mrz_date:
                setattr(d, campo, _iso(vlm_date or mrz_date))
                if vlm_date and mrz_date:
                    self._check(f"{campo}_mrz_vs_impresa", False, f"MRZ {mrz_date} / impresa {vlm_date}")
                self.conf[campo] = "baja" if (vlm_date and mrz_date) else "media"
            else:
                self.conf[campo] = "baja"
        if d.fecha_vencimiento:
            d.vigente = date.fromisoformat(d.fecha_vencimiento) >= date.today()

        # --- sexo
        mrz_sex = m.sexo if m else None
        vlm_sex = _SEX.get(_s(vlm, "sexo").upper().strip(". ")) if _s(vlm, "sexo") else None
        if mrz_sex and vlm_sex:
            d.sexo = mrz_sex if m.integra else vlm_sex
            self._check("sexo_mrz_vs_impreso", mrz_sex == vlm_sex, None if mrz_sex == vlm_sex else f"MRZ {mrz_sex} / impreso {vlm_sex}")
            self.conf["sexo"] = "alta" if mrz_sex == vlm_sex else "baja"
        elif mrz_sex or vlm_sex:
            d.sexo = mrz_sex or vlm_sex
            self.conf["sexo"] = "media"
        else:
            self.conf["sexo"] = "baja"

        # --- nacionalidad
        d.nacionalidad = m.nacionalidad if m and m.nacionalidad and len(m.nacionalidad) == 3 else None
        d.nacionalidad_impresa = _s(vlm, "nacionalidad").upper() or None
        if d.nacionalidad is None and d.pais_emisor and d.nacionalidad_impresa:
            d.nacionalidad = d.pais_emisor  # casi siempre coincide; se marca media
        self.conf["nacionalidad"] = "alta" if (m and m.nacionalidad and m.integra) else ("media" if d.nacionalidad else "baja")

        # --- sólo lectura visual
        d.lugar_nacimiento = _s(vlm, "lugar_nacimiento").upper() or None
        d.autoridad = _s(vlm, "autoridad").upper() or None
        exp = v.parse_date(_s(vlm, "fecha_expedicion"))
        d.fecha_expedicion = _iso(exp)
        if exp and d.fecha_vencimiento:
            venc = date.fromisoformat(d.fecha_vencimiento)
            ok = exp < venc and (venc.year - exp.year) <= 12
            self._check("fecha_expedicion_antes_de_vencimiento", ok, None if ok else f"expedición {exp} / vencimiento {venc}")
            self.conf["fecha_expedicion"] = "alta" if ok else "baja"
        elif exp:
            self.conf["fecha_expedicion"] = "media"
        for campo in ("lugar_nacimiento", "autoridad"):
            if getattr(d, campo):
                self.conf[campo] = "media"

        # --- CURP (pasaportes mexicanos)
        curp = v.normalize_curp(_s(vlm, "curp"))
        ocr_curp = _curp_en_ocr(self.ocr_texts)
        if ocr_curp and (not curp or (not v.curp_valid(curp) and v.curp_valid(ocr_curp))):
            if curp and curp != ocr_curp:
                self.warnings.append(f"CURP tomada del OCR ({ocr_curp}); la lectura visual decía {curp}")
            curp = ocr_curp
        if not curp and m and m.pais_emisor == "MEX" and m.opcional and len(m.opcional) >= 14:
            pass  # el campo opcional de la MRZ mexicana no trae la CURP completa; sólo referencia
        if d.pais_emisor == "MEX" or curp:
            if curp:
                reparada = v.curp_repair(curp, date.fromisoformat(d.fecha_nacimiento) if d.fecha_nacimiento else None,
                                         d.sexo) if not v.curp_valid(curp) else None
                if reparada and reparada != curp:
                    self.warnings.append(f"CURP corregida con la MRZ y el dígito verificador ({curp} -> {reparada})")
                    curp = reparada
                d.curp = curp
                valid = v.curp_valid(curp)
                self._check("curp_estructura_y_digito", valid)
                if d.fecha_nacimiento:
                    ok = v.curp_birthdate(curp) == date.fromisoformat(d.fecha_nacimiento)
                    self._check("curp_vs_fecha_nacimiento", ok)
                    valid = valid and ok
                if d.sexo:
                    ok = v.curp_sex(curp) == d.sexo
                    self._check("curp_vs_sexo", ok)
                    valid = valid and ok
                self.conf["curp"] = "alta" if valid else "baja"
            elif d.pais_emisor == "MEX":
                self.warnings.append("Pasaporte mexicano sin CURP legible")
                self.conf["curp"] = "baja"

        if self.vlm is not None:
            for campo in vlm.get("campos_ilegibles") or []:
                if isinstance(campo, str) and campo in self.conf and self.conf[campo] == "media":
                    self.conf[campo] = "baja"
        return d


_NAME_DIGITS = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z", "4": "A", "6": "G", "7": "T"})
_NOISE_TOKENS = {"C", "K", "L", "E", "I", "<"}


def _clean_name(name: str | None) -> str | None:
    """Quita dígitos (0→O...), comas y tokens de una letra que son ruido del relleno '<' (C, K...)."""
    if not name:
        return None
    name = name.translate(_NAME_DIGITS).replace(",", " ").replace("<", " ")
    tokens = [t for t in name.split() if t]
    while tokens and tokens[-1] in _NOISE_TOKENS:
        tokens.pop()
    return " ".join(tokens) or None


def _curp_en_ocr(texts: list[str]) -> str | None:
    """Primer token de 18 caracteres con estructura de CURP válida en el texto OCR del recorte."""
    import re

    for t in texts:
        for tok in re.findall(r"(?=([A-Z0-9Ñ]{18}))", v.strip_accents(t.upper()).replace(" ", "")):
            c = v.normalize_curp(tok)
            if c and v.curp_valid(c):
                return c
    return None


def _swapped(a: date, b: date) -> bool:
    return a.year == b.year and a.day == b.month and a.month == b.day


def needs_review(conf: dict[str, str]) -> list[str]:
    return [k for k, c in conf.items() if c == "baja"]
