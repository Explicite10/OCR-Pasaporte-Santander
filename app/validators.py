"""Utilidades de texto, fechas y CURP (para pasaportes mexicanos)."""

import re
import unicodedata
from datetime import date
from difflib import SequenceMatcher

CURP_RE = re.compile(r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{2}[B-DF-HJ-NP-TV-Z]{3}[0-9A-Z]\d$")
_CURP_ALPHABET = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
                           "S": "5", "B": "8", "G": "6", "T": "7"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"})

# Códigos ICAO de 3 letras -> nombre del país (los más frecuentes en el lote; el resto se devuelve tal cual)
PAISES = {
    "MEX": "MEXICO", "VEN": "VENEZUELA", "COL": "COLOMBIA", "ARG": "ARGENTINA", "CUB": "CUBA",
    "ESP": "ESPAÑA", "BRA": "BRASIL", "KOR": "COREA DEL SUR", "CHL": "CHILE", "USA": "ESTADOS UNIDOS",
    "CHN": "CHINA", "ITA": "ITALIA", "POL": "POLONIA", "HND": "HONDURAS", "CRI": "COSTA RICA",
    "GTM": "GUATEMALA", "ISR": "ISRAEL", "PAN": "PANAMA", "BOL": "BOLIVIA", "PRT": "PORTUGAL",
    "ECU": "ECUADOR", "NGA": "NIGERIA", "CAN": "CANADA", "PER": "PERU", "SLV": "EL SALVADOR",
    "NIC": "NICARAGUA", "DOM": "REPUBLICA DOMINICANA", "URY": "URUGUAY", "PRY": "PARAGUAY",
    "FRA": "FRANCIA", "DEU": "ALEMANIA", "D": "ALEMANIA", "GBR": "REINO UNIDO", "IND": "INDIA",
    "JPN": "JAPON", "RUS": "RUSIA", "UKR": "UCRANIA", "TUR": "TURQUIA", "NLD": "PAISES BAJOS",
    "BEL": "BELGICA", "CHE": "SUIZA", "AUT": "AUSTRIA", "SWE": "SUECIA", "NOR": "NORUEGA",
    "DNK": "DINAMARCA", "FIN": "FINLANDIA", "IRL": "IRLANDA", "AUS": "AUSTRALIA", "NZL": "NUEVA ZELANDA",
    "PHL": "FILIPINAS", "VNM": "VIETNAM", "THA": "TAILANDIA", "IRN": "IRAN", "EGY": "EGIPTO",
    "ZAF": "SUDAFRICA", "HTI": "HAITI", "JAM": "JAMAICA", "GRC": "GRECIA", "ROU": "RUMANIA",
    "HUN": "HUNGRIA", "CZE": "CHEQUIA", "SVK": "ESLOVAQUIA", "HRV": "CROACIA", "SRB": "SERBIA",
    "TWN": "TAIWAN", "HKG": "HONG KONG", "SGP": "SINGAPUR", "MYS": "MALASIA", "IDN": "INDONESIA",
    "PAK": "PAKISTAN", "BGD": "BANGLADESH", "LBN": "LIBANO", "SAU": "ARABIA SAUDITA", "ARE": "EMIRATOS ARABES",
    "MAR": "MARRUECOS", "DZA": "ARGELIA", "GHA": "GHANA", "KEN": "KENIA", "CMR": "CAMERUN", "SEN": "SENEGAL",
    "PRK": "COREA DEL NORTE", "BLR": "BIELORRUSIA", "LTU": "LITUANIA", "LVA": "LETONIA", "EST": "ESTONIA",
    "BGR": "BULGARIA", "SVN": "ESLOVENIA", "GEO": "GEORGIA", "ARM": "ARMENIA", "KAZ": "KAZAJISTAN",
}


# Códigos de país ICAO 9303 (ISO 3166-1 alfa-3 + especiales) para validar el país emisor y la nacionalidad
ICAO_CODES = set("""
AFG ALB DZA ASM AND AGO AIA ATA ATG ARG ARM ABW AUS AUT AZE BHS BHR BGD BRB BLR BEL BLZ BEN BMU BTN BOL BIH BWA
BRA IOT BRN BGR BFA BDI KHM CMR CAN CPV CYM CAF TCD CHL CHN CXR CCK COL COM COG COD COK CRI CIV HRV CUB CYP CZE
DNK DJI DMA DOM ECU EGY SLV GNQ ERI EST ETH FLK FRO FJI FIN FRA GUF PYF ATF GAB GMB GEO D DEU GHA GIB GRC GRL GRD
GLP GUM GTM GIN GNB GUY HTI HMD VAT HND HKG HUN ISL IND IDN IRN IRQ IRL ISR ITA JAM JPN JOR KAZ KEN KIR PRK KOR
KWT KGZ LAO LVA LBN LSO LBR LBY LIE LTU LUX MAC MKD MDG MWI MYS MDV MLI MLT MHL MTQ MRT MUS MYT MEX FSM MDA MCO
MNG MNE MSR MAR MOZ MMR NAM NRU NPL NLD ANT NCL NZL NIC NER NGA NIU NFK MNP NOR OMN PAK PLW PSE PAN PNG PRY PER
PHL PCN POL PRT PRI QAT REU ROU RUS RWA SHN KNA LCA SPM VCT WSM SMR STP SAU SEN SRB SYC SLE SGP SVK SVN SLB SOM
ZAF SGS SSD ESP LKA SDN SUR SJM SWZ SWE CHE SYR TWN TJK TZA THA TLS TGO TKL TON TTO TUN TUR TKM TCA TUV UGA UKR
ARE GBR GBD GBN GBO GBP GBS USA UMI URY UZB VUT VEN VNM VGB VIR WLF ESH YEM ZMB ZWE RKS UNO UNA UNK XXA XXB XXC
XXX EUE XOM XPO XCC XEC XKX UTO
""".split())


def strip_accents(s: str) -> str:
    s = s.replace("Ñ", "\0").replace("ñ", "\0")
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.replace("\0", "Ñ")


def norm_text(s: str | None) -> str:
    """MAYÚSCULAS sin acentos (la Ñ se vuelve N, como en la MRZ) ni signos; espacios simples."""
    if not s:
        return ""
    s = strip_accents(s.upper()).replace("Ñ", "N")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_code(s: str | None) -> str:
    """Para números de pasaporte y códigos: sin espacios ni guiones, mayúsculas."""
    if not s:
        return ""
    return re.sub(r"[^A-Z0-9]", "", strip_accents(s.upper()))


def similarity(a: str | None, b: str | None) -> float:
    a, b = norm_text(a), norm_text(b)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


_MESES = {
    "ENE": 1, "FEB": 2, "MAR": 3, "ABR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AGO": 8, "SEP": 9, "SET": 9,
    "OCT": 10, "NOV": 11, "DIC": 12,
    "JAN": 1, "APR": 4, "AUG": 8, "DEC": 12,
    "FEV": 2, "AVR": 4, "MAI": 5, "JUI": 6, "AOU": 8, "DEZ": 12, "OUT": 10, "MRZ": 3, "OKT": 10,
}


def parse_date(s: str | None) -> date | None:
    """Acepta AAAA-MM-DD, DD/MM/AAAA, DD.MM.AAAA, '12 ENE/JAN 1985', '12 ENE 85'..."""
    if not s:
        return None
    s = strip_accents(s.upper())
    m = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", s)
    if m:
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    m = re.search(r"(\d{1,2})\s*[/\-. ]\s*(\d{1,2})\s*[/\-. ]\s*(\d{4})", s)
    if m:
        return _mk(int(m[3]), int(m[2]), int(m[1]))
    m = re.search(r"(\d{1,2})\s*[/\-. ]?\s*([A-Z]{3})[A-Z]*(?:\s*/\s*[A-Z]{3,})?\s*[/\-. ]?\s*(\d{2,4})", s)
    if m and m[2] in _MESES:
        y = int(m[3])
        if y < 100:
            y += 2000 if y <= date.today().year % 100 else 1900
        return _mk(y, _MESES[m[2]], int(m[1]))
    m = re.search(r"([A-Z]{3})[A-Z]*\s+(\d{1,2}),?\s+(\d{4})", s)  # JAN 12, 1985
    if m and m[1] in _MESES:
        return _mk(int(m[3]), _MESES[m[1]], int(m[2]))
    m = re.search(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        return _mk(int(m[1]), int(m[2]), int(m[3]))
    return None


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


# ---------------------------------------------------------------- CURP (pasaportes mexicanos)


def _typed(s: str, kinds: str) -> str:
    out = []
    for ch, k in zip(s, kinds):
        if k == "d":
            ch = ch.translate(_TO_DIGIT)
        elif k == "a":
            ch = ch.translate(_TO_ALPHA)
        out.append(ch)
    return "".join(out)


def curp_check_digit(curp17: str) -> str:
    total = sum(_CURP_ALPHABET.index(c) * (18 - i) for i, c in enumerate(curp17) if c in _CURP_ALPHABET)
    return str((10 - total % 10) % 10)


def normalize_curp(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"[^A-Z0-9Ñ]", "", strip_accents(raw.upper()))
    if len(s) != 18:
        return s or None
    s = _typed(s, "aaaaddddddaaaaaaxd")
    return s


def curp_valid(curp: str | None) -> bool:
    if not curp or len(curp) != 18 or not CURP_RE.match(curp):
        return False
    return curp_check_digit(curp[:17]) == curp[17]


_CURP_CONFUSABLE = {"0": "OD", "O": "0", "D": "0", "1": "IL", "I": "1", "L": "1", "2": "Z", "Z": "2", "5": "S",
                    "S": "5", "8": "B", "B": "8", "6": "G", "G": "6", "4": "A", "A": "4", "7": "T", "T": "7",
                    "N": "Ñ", "Ñ": "N", "E": "F", "F": "E", "M": "N", "H": "M", "9": "g"}


def curp_repair(curp: str | None, fecha: date | None = None, sexo: str | None = None) -> str | None:
    """Intenta arreglar una CURP de 18 caracteres que no cuadra: primero fecha y sexo con los de la MRZ,
    luego UNA sustitución de un carácter confusable que haga cuadrar el dígito verificador.
    Devuelve la CURP reparada o None si no hay una reparación única."""
    if not curp or len(curp) != 18:
        return None
    if curp_valid(curp):
        return curp
    base = curp
    if fecha is not None:
        base = base[:4] + fecha.strftime("%y%m%d") + base[10:]
    if sexo in ("M", "F"):
        base = base[:10] + {"M": "H", "F": "M"}[sexo] + base[11:]
    if curp_valid(base):
        return base
    cands = set()
    for i, ch in enumerate(base):
        if 4 <= i <= 10:
            continue  # fecha y sexo ya vienen de la MRZ
        for alt in _CURP_CONFUSABLE.get(ch, ""):
            alt = alt.upper()
            cand = base[:i] + alt + base[i + 1:]
            if curp_valid(cand):
                cands.add(cand)
    if curp_check_digit(base[:17]) != base[17] and CURP_RE.match(base[:17] + curp_check_digit(base[:17])):
        cands.add(base[:17] + curp_check_digit(base[:17]))  # el dígito verificador mal leído
    return cands.pop() if len(cands) == 1 else None


_HOMOCLAVE_A_DIGITO = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5",
                                      "B": "8", "G": "6", "T": "7", "A": "4"})
_HOMOCLAVE_A_LETRA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "7": "T", "4": "A"})


def curp_homoclave(curp: str | None, fecha: date | None) -> str | None:
    """La posición 17 de la CURP (índice 16) es un dígito para nacidos antes de 2000 y una letra desde
    2000. Con la fecha de nacimiento verificada se corrige una O/0, I/1, S/5... en esa posición, siempre
    que la CURP corregida cuadre con su dígito verificador. Devuelve la CURP (corregida o igual)."""
    if not curp or len(curp) != 18 or fecha is None:
        return curp
    c16 = curp[16]
    if fecha.year < 2000 and c16.isalpha():
        cand = curp[:16] + c16.translate(_HOMOCLAVE_A_DIGITO) + curp[17:]
    elif fecha.year >= 2000 and c16.isdigit():
        cand = curp[:16] + c16.translate(_HOMOCLAVE_A_LETRA) + curp[17:]
    else:
        return curp
    return cand if cand != curp and curp_valid(cand) else curp


def curp_birthdate(curp: str) -> date | None:
    if not curp or len(curp) < 10 or not curp[4:10].isdigit():
        return None
    yy, mm, dd = int(curp[4:6]), int(curp[6:8]), int(curp[8:10])
    year = 2000 + yy if curp[16].isalpha() else 1900 + yy
    return _mk(year, mm, dd)


def curp_sex(curp: str) -> str | None:
    if not curp or len(curp) < 11:
        return None
    return {"H": "M", "M": "F"}.get(curp[10])
