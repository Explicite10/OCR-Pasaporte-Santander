"""
Validaciones del "Plan de atención - Validación documental", sección Pasaporte.

Mismo contrato que el bloque `validacion_plan` de las APIs de forma migratoria INM (OCR-INM-DocumentAI y
OCR-INM-OpenSource): trabaja sobre el JSON ya homologado (`datos`, `mrz`, `clasificacion.categoria`) y
no depende del motor de extracción.

Responde las 8 preguntas del plan con SI / NO, en el mismo orden:

  1. ¿Es una hoja en blanco?              (pasa si NO)
  2. ¿La imagen es ilegible?              (pasa si NO)
  3. ¿Es un pasaporte?                    (pasa si SI)
  4. ¿Está vigente?                       (pasa si SI; por año, como pide el plan)
  5. ¿El nombre coincide?                 (vs captura de la solicitud)
  6. ¿La CURP coincide?                   (vs captura, siempre y cuando exista el dato)
  7. ¿La fecha de nacimiento coincide?    (vs captura)
  8. ¿La nacionalidad coincide?           (vs captura)

Si no se cumplen al 100 %: mensaje "Revisar documento y motivo de rechazo" + motivos.

Diferencia con INM: `datos` lleva la lectura impresa de la hoja de datos (regla de la referencia).
Si el nombre o la fecha de nacimiento impresos no coinciden con la solicitud pero la MRZ es íntegra
(sus dígitos de control cuadran) y la MRZ sí coincide, la validación pasa y el detalle lo explica.

Valores de `resultado`:
  SI / NO          respuesta a la pregunta
  NO_APLICA        la comprobación no corresponde (CURP sin dato en pasaporte o solicitud): no bloquea
  NO_VERIFICADO    faltan datos para responder (p. ej. no se envió el dato de la solicitud): bloquea
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from typing import Optional

from . import validators as v

MENSAJE_OK = "Documento válido: cumple con todas las validaciones."
MENSAJE_RECHAZO = "Revisar documento y motivo de rechazo"


@dataclass
class Solicitud:
    """Datos capturados en la solicitud. Todos opcionales."""
    nombre: Optional[str] = None             # nombre completo, en cualquier orden
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    nombres: Optional[str] = None
    curp: Optional[str] = None
    fecha_nacimiento: Optional[str] = None   # AAAA-MM-DD o DD/MM/AAAA
    nacionalidad: Optional[str] = None       # gentilicio, país o código ISO

    def nombre_completo(self) -> Optional[str]:
        if self.nombre and self.nombre.strip():
            return self.nombre
        partes = [p for p in (self.apellido_paterno, self.apellido_materno, self.nombres) if p and p.strip()]
        return " ".join(partes) or None

    def vacia(self) -> bool:
        return not any((self.nombre_completo(), self.curp, self.fecha_nacimiento, self.nacionalidad))


# ------------------------------------------------------------------ normalización


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper()


def _tokens(nombre: str) -> list[str]:
    return sorted(t for t in re.split(r"[^A-Z]+", _ascii(nombre)) if t)


def _fecha(s: Optional[str]) -> Optional[str]:
    if not s or not s.strip():
        return None
    s = s.strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return None
    d = v.parse_date(s)  # DD/MM/AAAA, DD-MM-AAAA, "15 MAR 1990"
    return d.isoformat() if d else None


# Pares que el OCR confunde con frecuencia en la CURP
_CONFUNDIBLES = {frozenset(p) for p in ("O0", "I1", "S5", "B8", "Z2", "G6", "Q0", "D0")}


# ------------------------------------------------------------------ países

# ISO-3 -> nombres y raíces de gentilicio (sin acentos, mayúsculas). Mismo catálogo que INM.
_PAISES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "ARG": (("ARGENTINA",), ("ARGENTIN",)), "BOL": (("BOLIVIA",), ("BOLIVIAN",)),
    "BRA": (("BRASIL", "BRAZIL"), ("BRASILEN", "BRASILER")), "CHL": (("CHILE",), ("CHILEN",)),
    "COL": (("COLOMBIA",), ("COLOMBIAN",)), "CRI": (("COSTA RICA",), ("COSTARRICENS",)),
    "CUB": (("CUBA",), ("CUBAN",)), "DOM": (("REPUBLICA DOMINICANA",), ("DOMINICAN",)),
    "ECU": (("ECUADOR",), ("ECUATORIAN",)), "SLV": (("EL SALVADOR",), ("SALVADOREN",)),
    "GTM": (("GUATEMALA",), ("GUATEMALTEC",)), "HND": (("HONDURAS",), ("HONDUREN",)),
    "HTI": (("HAITI",), ("HAITIAN",)), "JAM": (("JAMAICA",), ("JAMAIQUIN", "JAMAICAN")),
    "MEX": (("MEXICO",), ("MEXICAN",)), "NIC": (("NICARAGUA",), ("NICARAGUENS",)),
    "PAN": (("PANAMA",), ("PANAMEN",)), "PRY": (("PARAGUAY",), ("PARAGUAY",)),
    "PER": (("PERU",), ("PERUAN",)), "PRI": (("PUERTO RICO",), ("PUERTORRIQUEN",)),
    "URY": (("URUGUAY",), ("URUGUAY",)), "VEN": (("VENEZUELA",), ("VENEZOLAN",)),
    "USA": (("ESTADOS UNIDOS", "ESTADOS UNIDOS DE AMERICA", "EUA", "EEUU", "USA"), ("ESTADOUNIDENS", "NORTEAMERICAN")),
    "CAN": (("CANADA",), ("CANADIENS",)), "ESP": (("ESPANA", "SPAIN"), ("ESPANOL",)),
    "PRT": (("PORTUGAL",), ("PORTUGUES",)), "FRA": (("FRANCIA", "FRANCE"), ("FRANCES",)),
    "ITA": (("ITALIA", "ITALY"), ("ITALIAN",)), "DEU": (("ALEMANIA", "GERMANY"), ("ALEMAN",)),
    "GBR": (("REINO UNIDO", "GRAN BRETANA", "INGLATERRA", "UNITED KINGDOM"), ("BRITANIC", "INGLES")),
    "IRL": (("IRLANDA",), ("IRLANDES",)), "NLD": (("PAISES BAJOS", "HOLANDA"), ("NEERLANDES", "HOLANDES")),
    "BEL": (("BELGICA",), ("BELG",)), "CHE": (("SUIZA",), ("SUIZ",)), "AUT": (("AUSTRIA",), ("AUSTRIAC",)),
    "SWE": (("SUECIA",), ("SUEC",)), "NOR": (("NORUEGA",), ("NORUEG",)), "DNK": (("DINAMARCA",), ("DANES",)),
    "FIN": (("FINLANDIA",), ("FINLANDES",)), "POL": (("POLONIA",), ("POLAC",)), "RUS": (("RUSIA",), ("RUS",)),
    "UKR": (("UCRANIA",), ("UCRANIAN",)), "ROU": (("RUMANIA",), ("RUMAN",)), "GRC": (("GRECIA",), ("GRIEG",)),
    "TUR": (("TURQUIA",), ("TURC",)), "ISR": (("ISRAEL",), ("ISRAELI",)), "LBN": (("LIBANO",), ("LIBANES",)),
    "CHN": (("CHINA",), ("CHIN",)), "JPN": (("JAPON",), ("JAPONES",)), "KOR": (("COREA DEL SUR", "COREA"), ("COREAN", "SURCOREAN")),
    "IND": (("INDIA",), ("INDI", "HINDU")), "PHL": (("FILIPINAS",), ("FILIPIN",)), "VNM": (("VIETNAM",), ("VIETNAMIT",)),
    "AUS": (("AUSTRALIA",), ("AUSTRALIAN",)), "NZL": (("NUEVA ZELANDA",), ("NEOZELANDES",)),
    "ZAF": (("SUDAFRICA",), ("SUDAFRICAN",)), "NGA": (("NIGERIA",), ("NIGERIAN",)), "EGY": (("EGIPTO",), ("EGIPCI",)),
    "MAR": (("MARRUECOS",), ("MARROQU",)), "IRN": (("IRAN",), ("IRANI",)), "PAK": (("PAKISTAN",), ("PAKISTANI",)),
    # Países que aparecen en el lote de pasaportes y no estaban en el catálogo de INM
    "SVK": (("ESLOVAQUIA",), ("ESLOVAC",)), "SVN": (("ESLOVENIA",), ("ESLOVEN",)),
    "CZE": (("CHEQUIA", "REPUBLICA CHECA"), ("CHEC",)), "HUN": (("HUNGRIA",), ("HUNGAR",)),
    "BGR": (("BULGARIA",), ("BULGAR",)), "HRV": (("CROACIA",), ("CROAT",)), "SRB": (("SERBIA",), ("SERBI",)),
    "ERI": (("ERITREA",), ("ERITRE",)), "GHA": (("GHANA",), ("GHANES",)), "KEN": (("KENIA",), ("KENIAN",)),
    "CMR": (("CAMERUN",), ("CAMERUNES",)), "SEN": (("SENEGAL",), ("SENEGALES",)), "DZA": (("ARGELIA",), ("ARGELIN",)),
    "SAU": (("ARABIA SAUDITA",), ("SAUDI", "SAUDIT")), "ARE": (("EMIRATOS ARABES UNIDOS",), ("EMIRATI",)),
    "TWN": (("TAIWAN",), ("TAIWANES",)), "HKG": (("HONG KONG",), ("HONGKONES",)), "SGP": (("SINGAPUR",), ("SINGAPURENS",)),
    "MYS": (("MALASIA",), ("MALAYO", "MALASI")), "IDN": (("INDONESIA",), ("INDONESI",)), "THA": (("TAILANDIA",), ("TAILANDES",)),
    "BGD": (("BANGLADES",), ("BANGLADESI",)), "LTU": (("LITUANIA",), ("LITUAN",)), "LVA": (("LETONIA",), ("LETON",)),
    "EST": (("ESTONIA",), ("ESTONI",)), "BLR": (("BIELORRUSIA",), ("BIELORRUS",)), "GEO": (("GEORGIA",), ("GEORGIAN",)),
    "ARM": (("ARMENIA",), ("ARMENI",)), "KAZ": (("KAZAJISTAN",), ("KAZAJ",)),
}
_POR_CODIGO_ISO2 = {"AR": "ARG", "BO": "BOL", "BR": "BRA", "CL": "CHL", "CO": "COL", "CR": "CRI", "CU": "CUB",
                    "DO": "DOM", "EC": "ECU", "SV": "SLV", "GT": "GTM", "HN": "HND", "HT": "HTI", "MX": "MEX",
                    "NI": "NIC", "PA": "PAN", "PY": "PRY", "PE": "PER", "UY": "URY", "VE": "VEN", "US": "USA",
                    "CA": "CAN", "ES": "ESP", "PT": "PRT", "FR": "FRA", "IT": "ITA", "DE": "DEU", "GB": "GBR",
                    "CN": "CHN", "JP": "JPN", "KR": "KOR", "IN": "IND", "AU": "AUS", "IL": "ISR"}
# Alemania usa "D" en la MRZ; el resto de códigos ICAO de 3 letras se acepta tal cual
_ICAO_EQUIV = {"D": "DEU", "D<<": "DEU"}


def _raiz_gentilicio(s: str) -> str:
    s = re.sub(r"[^A-Z]", "", _ascii(s))
    return re.sub(r"(AS|OS|ES|A|O|E|S)$", "", s)


def pais_iso3(texto: Optional[str]) -> Optional[str]:
    """Convierte gentilicio, nombre de país o código (ISO-2/ISO-3/ICAO) a ISO-3. None si no se reconoce."""
    if not texto or not texto.strip():
        return None
    t = re.sub(r"\s+", " ", _ascii(texto)).strip(" .")
    if t in _ICAO_EQUIV:
        return _ICAO_EQUIV[t]
    if t in _PAISES:
        return t
    if t in _POR_CODIGO_ISO2:
        return _POR_CODIGO_ISO2[t]
    if len(t) == 3 and t in v.ICAO_CODES:
        return t
    raiz = _raiz_gentilicio(t)
    for iso, (nombres, raices) in _PAISES.items():
        if t in nombres or any(raiz == _raiz_gentilicio(r) or raiz.startswith(r) for r in raices):
            return iso
    for iso, nombre in v.PAISES.items():  # nombres de país del catálogo de la API (sin gentilicio)
        if len(iso) == 3 and t == _ascii(nombre):
            return iso
    return None


# ------------------------------------------------------------------ validaciones


def _item(id_: str, pregunta: str, resultado: str, ok: bool, detalle: str) -> dict:
    return {"id": id_, "pregunta": pregunta, "resultado": resultado, "ok": ok, "detalle": detalle}


def _mrz_integra(mrz: dict) -> bool:
    return bool(mrz.get("integra"))


def vigencia(datos: dict, mrz: Optional[dict] = None, regla: str = "anio",
             hoy: Optional[date] = None) -> tuple[Optional[bool], str]:
    """(vigente, detalle). regla 'anio': año de vencimiento >= año actual (plan de atención).
    regla 'fecha': fecha de vencimiento >= hoy. Si la MRZ es íntegra se usa su fecha de vencimiento,
    verificada por su dígito de control; si no, la de la hoja de datos."""
    hoy = hoy or date.today()
    mrz = mrz or {}
    venc, fuente = datos.get("fecha_vencimiento"), "la hoja de datos"
    if _mrz_integra(mrz) and mrz.get("fecha_vencimiento"):
        fuente = "la MRZ, verificada por su dígito de control"
        if venc and venc != mrz["fecha_vencimiento"]:
            fuente += f"; la hoja de datos se leyó {venc}"
        venc = mrz["fecha_vencimiento"]
    if not venc:
        return None, "No se pudo leer la fecha de vencimiento."
    f = date.fromisoformat(venc)
    if regla == "fecha":
        return f >= hoy, f"Vence el {venc} (según {fuente}); se compara contra la fecha de hoy ({hoy.isoformat()})."
    return f.year >= hoy.year, f"Año de vigencia {f.year} (según {fuente}) contra año actual {hoy.year}."


def _ilegible(categoria: str, datos: dict, mrz: dict) -> tuple[bool, str]:
    if categoria == "hoja_en_blanco":
        return True, "No se leyó texto en el documento."
    if categoria != "pasaporte":
        return False, "Se leyó texto, pero el documento no es un pasaporte."
    esenciales = {"nombre": datos.get("apellido_paterno") or datos.get("nombres"),
                  "fecha_nacimiento": datos.get("fecha_nacimiento"),
                  "numero_pasaporte": datos.get("numero_pasaporte")}
    faltan = [k for k, val in esenciales.items() if not val]
    mrz_ok = _mrz_integra(mrz)
    if (not mrz_ok and faltan) or len(faltan) >= 2:
        return True, ("No se pudieron leer datos esenciales: " + ", ".join(faltan)
                      + ("; la MRZ tampoco es legible." if not mrz_ok else "."))
    return False, "Los datos esenciales se leyeron" + (" y la MRZ es legible." if mrz_ok else "; la MRZ no es legible.")


def _nombre_mrz(mrz: dict) -> Optional[str]:
    if not _mrz_integra(mrz) or mrz.get("nombre_abreviado"):
        return None
    partes = [mrz.get(k) for k in ("nombres", "apellido_paterno", "apellido_materno") if mrz.get(k)]
    # Transliteración ICAO de la Ñ (NXX) -> N, para compararla con la captura sin acentos
    return " ".join(p.replace("NXX", "N") for p in partes) or None


def _comparar_nombre(datos: dict, mrz: dict, sol: Optional[str]) -> tuple[str, bool, str]:
    doc, de_mrz = datos.get("nombre_completo"), _nombre_mrz(mrz)
    if not sol:
        return "NO_VERIFICADO", False, "No se envió el nombre de la solicitud."
    if not doc and not de_mrz:
        return "NO_VERIFICADO", False, "No se pudo leer el nombre en el pasaporte."
    b = _tokens(sol)
    if doc and _tokens(doc) == b:
        return "SI", True, "El nombre coincide con la captura (sin importar orden, acentos ni mayúsculas)."
    if de_mrz and _tokens(de_mrz) == b:
        return "SI", True, ("El nombre coincide con la captura según la MRZ, verificada por sus dígitos de control"
                            + ("; la lectura de la hoja de datos difiere." if doc else "."))
    a = _tokens(doc or de_mrz)
    faltan, sobran = sorted(set(b) - set(a)), sorted(set(a) - set(b))
    det = "El nombre no coincide."
    if faltan:
        det += f" En la solicitud y no en el pasaporte: {' '.join(faltan)}."
    if sobran:
        det += f" En el pasaporte y no en la solicitud: {' '.join(sobran)}."
    return "NO", False, det


def _sexo_curp(datos: dict, mrz: dict) -> Optional[str]:
    """Sexo en la convención de la CURP (H/M), tomado de la MRZ íntegra (M=male, F=female)."""
    if _mrz_integra(mrz) and mrz.get("sexo") in ("M", "F"):
        return {"M": "H", "F": "M"}[mrz["sexo"]]
    return None


def _comparar_curp(datos: dict, mrz: dict, sol: Optional[str]) -> tuple[str, bool, str]:
    doc = datos.get("curp")
    if not sol:
        return "NO_APLICA", True, "La solicitud no trae CURP."
    sol_n = re.sub(r"[^A-Z0-9]", "", _ascii(sol))
    if not doc:
        return "NO_APLICA", True, "El pasaporte no trae CURP legible (solo la traen los pasaportes mexicanos)."
    if doc == sol_n:
        return "SI", True, "La CURP coincide con la captura."
    if len(doc) == len(sol_n) == 18:
        difs = [(x, y) for x, y in zip(doc, sol_n) if x != y]
        if len(difs) <= 2 and all(frozenset((x, y)) in _CONFUNDIBLES for x, y in difs):
            # La lectura difiere solo en caracteres que el OCR confunde: se acepta si la CURP capturada
            # es coherente con la fecha de nacimiento y el sexo verificados.
            fn = datos.get("fecha_nacimiento") or (mrz.get("fecha_nacimiento") if _mrz_integra(mrz) else None)
            sexo = _sexo_curp(datos, mrz)
            fecha_ok = bool(fn) and sol_n[4:10] == fn[2:4] + fn[5:7] + fn[8:10]
            sexo_ok = sexo is None or sol_n[10] == sexo
            if fecha_ok and sexo_ok:
                return "SI", True, ("La CURP coincide; la lectura del pasaporte difiere solo en "
                                    f"{len(difs)} carácter(es) que el OCR suele confundir, y la CURP capturada "
                                    "es coherente con la fecha de nacimiento y el sexo verificados.")
    return "NO", False, f"La CURP no coincide: pasaporte '{doc}' vs solicitud '{sol_n}'."


def _comparar_fecha(datos: dict, mrz: dict, sol: Optional[str]) -> tuple[str, bool, str]:
    doc = datos.get("fecha_nacimiento")
    de_mrz = mrz.get("fecha_nacimiento") if _mrz_integra(mrz) else None
    if not sol:
        return "NO_VERIFICADO", False, "No se envió la fecha de nacimiento de la solicitud."
    sol_f = _fecha(sol)
    if not sol_f:
        return "NO_VERIFICADO", False, f"La fecha de la solicitud '{sol}' no tiene un formato reconocible (usar AAAA-MM-DD)."
    if not doc and not de_mrz:
        return "NO_VERIFICADO", False, "No se pudo leer la fecha de nacimiento en el pasaporte."
    if doc == sol_f:
        return "SI", True, "La fecha de nacimiento coincide con la captura."
    if de_mrz == sol_f:
        return "SI", True, ("La fecha de nacimiento coincide con la captura según la MRZ, verificada por su dígito de "
                            "control" + (f"; la hoja de datos se leyó {doc}." if doc else "."))
    return "NO", False, f"La fecha de nacimiento no coincide: pasaporte {doc or de_mrz} vs solicitud {sol_f}."


def _comparar_nacionalidad(datos: dict, mrz: dict, sol: Optional[str]) -> tuple[str, bool, str]:
    if not sol:
        return "NO_VERIFICADO", False, "No se envió la nacionalidad de la solicitud."
    doc_iso = (pais_iso3(datos.get("nacionalidad")) or pais_iso3(datos.get("nacionalidad_impresa"))
               or (pais_iso3(mrz.get("nacionalidad")) if _mrz_integra(mrz) else None))
    impresa = datos.get("nacionalidad_impresa") or ""
    if not doc_iso and not impresa:
        return "NO_VERIFICADO", False, "No se pudo leer la nacionalidad en el pasaporte."
    sol_iso = pais_iso3(sol)
    if sol_iso and doc_iso:
        if sol_iso == doc_iso:
            return "SI", True, f"La nacionalidad coincide ({doc_iso})."
        return "NO", False, f"La nacionalidad no coincide: pasaporte {doc_iso} vs solicitud {sol_iso} ('{sol}')."
    # País no reconocido en el catálogo: se compara el gentilicio impreso sin su terminación
    if impresa and _raiz_gentilicio(impresa) == _raiz_gentilicio(sol):
        return "SI", True, f"La nacionalidad coincide ({impresa})."
    return "NO", False, f"La nacionalidad no coincide o no se reconoce: pasaporte '{impresa or doc_iso}' vs solicitud '{sol}'."


_DEPENDIENTES = (("vigente", "¿Está vigente?"), ("nombre_coincide", "¿El nombre coincide?"),
                 ("curp_coincide", "¿La CURP coincide?"),
                 ("fecha_nacimiento_coincide", "¿La fecha de nacimiento coincide?"),
                 ("nacionalidad_coincide", "¿La nacionalidad coincide?"))


def evaluar(categoria: str, datos: Optional[dict], mrz: Optional[dict], solicitud: Solicitud,
            regla_vigencia: str = "anio") -> dict:
    """Arma el bloque validacion_plan. categoria: pasaporte | otro | hoja_en_blanco."""
    datos, mrz = datos or {}, mrz or {}
    es_pas = categoria == "pasaporte"
    items: list[dict] = []

    blanco = categoria == "hoja_en_blanco"
    items.append(_item("hoja_en_blanco", "¿Es una hoja en blanco?", "SI" if blanco else "NO", not blanco,
                       "No se leyó texto en el documento." if blanco else "El documento tiene contenido."))

    ileg, det = _ilegible(categoria, datos, mrz)
    items.append(_item("imagen_ilegible", "¿La imagen es ilegible?", "SI" if ileg else "NO", not ileg, det))

    items.append(_item("es_pasaporte", "¿Es un pasaporte?", "SI" if es_pas else "NO", es_pas,
                       "Se identificó la página de datos de un pasaporte." if es_pas
                       else "El documento no es un pasaporte."))

    if es_pas:
        vig, det = vigencia(datos, mrz, regla_vigencia)
        res = "NO_VERIFICADO" if vig is None else ("SI" if vig else "NO")
        items.append(_item("vigente", "¿Está vigente?", res, bool(vig), det))
        r, ok, det = _comparar_nombre(datos, mrz, solicitud.nombre_completo())
        items.append(_item("nombre_coincide", "¿El nombre coincide?", r, ok, det))
        r, ok, det = _comparar_curp(datos, mrz, solicitud.curp)
        items.append(_item("curp_coincide", "¿La CURP coincide?", r, ok, det))
        r, ok, det = _comparar_fecha(datos, mrz, solicitud.fecha_nacimiento)
        items.append(_item("fecha_nacimiento_coincide", "¿La fecha de nacimiento coincide?", r, ok, det))
        r, ok, det = _comparar_nacionalidad(datos, mrz, solicitud.nacionalidad)
        items.append(_item("nacionalidad_coincide", "¿La nacionalidad coincide?", r, ok, det))
    else:
        for id_, preg in _DEPENDIENTES:
            items.append(_item(id_, preg, "NO_VERIFICADO", False, "No aplica: el documento no es un pasaporte."))

    cumple = all(i["ok"] for i in items)
    # Motivos de raíz: si no es pasaporte, las validaciones que dependen de ello no se repiten como motivo.
    motivos = [f"{i['pregunta']} {i['resultado']}: {i['detalle']}" for i in items
               if not i["ok"] and not i["detalle"].startswith("No aplica: el documento no es")]
    if es_pas and solicitud.vacia():
        motivos.append("No se enviaron datos de la solicitud: las validaciones de coincidencia no se pudieron realizar.")
    return {"cumple": cumple, "mensaje": MENSAJE_OK if cumple else MENSAJE_RECHAZO,
            "motivos_rechazo": motivos, "regla_vigencia": regla_vigencia, "validaciones": items}
