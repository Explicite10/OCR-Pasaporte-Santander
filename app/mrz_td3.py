"""Lectura de la MRZ de pasaportes (ICAO 9303, formato TD3: 2 líneas x 44 caracteres).

    Línea 1: P + tipo(1) + país emisor(3) + APELLIDOS<<NOMBRES (39, relleno con '<')
    Línea 2: número(9) + dígito + nacionalidad(3) + nacimiento AAMMDD + dígito + sexo(1)
             + vencimiento AAMMDD + dígito + opcional(14) + dígito + dígito compuesto

El dígito compuesto cubre: número+dígito, nacimiento+dígito, vencimiento+dígito, opcional+dígito.

Los errores típicos del OCR (O/0, I/1, S/5, B/8, «/<<, K/<...) se corrigen según el tipo
de cada posición, y si un dígito verificador no cuadra se intenta una sola sustitución
entre caracteres que se confunden visualmente (como en el proyecto de INE).
"""

import re
from dataclasses import dataclass, field
from datetime import date

LINE_LEN = 44

_TO_DIGIT = str.maketrans({"O": "0", "Q": "0", "D": "0", "U": "0", "I": "1", "L": "1", "T": "1",
                           "Z": "2", "S": "5", "B": "8", "G": "6", "A": "4", "E": "8"})
_TO_ALPHA = str.maketrans({"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G", "4": "A"})
_FILLER_LIKE = str.maketrans({"(": "<", "[": "<", "{": "<", "‹": "<", "«": "<", "»": "<", "K": "<", "C": "<",
                              "L": "<", "E": "<"})

# Pares que el OCR suele confundir; se usan para reparar con el dígito verificador.
_CONFUSABLE = {
    "0": "86935OD", "1": "74IL", "2": "73Z", "3": "89562", "4": "19A", "5": "63896S",
    "6": "58035G", "7": "12T", "8": "035693B", "9": "8304",
    "O": "0DQ", "D": "0O", "Q": "0O", "I": "1L", "L": "1I", "Z": "2", "S": "5", "B": "8", "G": "6",
    "A": "4", "T": "7", "<": "KC", "K": "<", "C": "<G", "E": "F", "F": "E", "M": "N", "N": "M",
}


def check_digit(s: str) -> int:
    weights = (7, 3, 1)
    total = 0
    for i, ch in enumerate(s):
        if ch.isdigit():
            v = int(ch)
        elif "A" <= ch <= "Z":
            v = ord(ch) - 55
        else:
            v = 0
        total += v * weights[i % 3]
    return total % 10


@dataclass
class MrzCheck:
    nombre: str
    valido: bool
    corregido: bool = False


@dataclass
class MrzTD3:
    lineas: list[str]
    tipo_documento: str | None = None
    pais_emisor: str | None = None
    apellidos: str | None = None
    nombres: str | None = None
    numero: str | None = None
    nacionalidad: str | None = None
    fecha_nacimiento: date | None = None
    sexo: str | None = None
    fecha_vencimiento: date | None = None
    opcional: str | None = None
    checks: list[MrzCheck] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return bool(self.checks) and all(c.valido for c in self.checks)

    @property
    def corregido(self) -> bool:
        return any(c.corregido for c in self.checks)

    @property
    def n_validos(self) -> int:
        return sum(c.valido for c in self.checks)

    @property
    def integra(self) -> bool:
        """Número, nacimiento, vencimiento y compuesto cuadran (el opcional puede faltar)."""
        esenciales = {"mrz_numero", "mrz_fecha_nacimiento", "mrz_vencimiento", "mrz_compuesto"}
        return all(c.valido for c in self.checks if c.nombre in esenciales) and len(self.checks) >= 4


# ---------------------------------------------------------------- normalización


def clean(s: str) -> str:
    s = s.upper().replace(" ", "").replace("«", "<<").replace("»", "<<")
    s = s.translate(str.maketrans({"(": "<", "[": "<", "{": "<", "‹": "<"}))
    return re.sub(r"[^A-Z0-9<]", "", s)


def _fit(s: str) -> str:
    return (s + "<" * LINE_LEN)[:LINE_LEN]


def _map(s: str, kind: str) -> str:
    """kind por carácter: d=dígito, a=letra, f=relleno '<', x=alfanumérico o '<', n=letra o '<', s=sexo."""
    out = []
    for ch, k in zip(s, kind):
        if k == "d":
            ch = ch.translate(_TO_DIGIT)
        elif k == "a":
            ch = ch.translate(_TO_ALPHA)
        elif k == "f":
            ch = "<"
        elif k == "n":
            if ch in "([{‹«":
                ch = "<"
            elif ch != "<":
                ch = ch.translate(_TO_ALPHA)
        elif k == "s":
            ch = {"N": "M", "W": "M", "H": "M", "P": "F", "E": "F", "K": "<", "C": "<"}.get(ch, ch)
            if ch not in "MFX<":
                ch = "<"
        # "x" (número de pasaporte, opcional): se deja tal cual, puede ser letra o dígito
        out.append(ch)
    return "".join(out)


L1_KIND = "a" + "n" + "aaa" + "n" * 39
L2_KIND = "x" * 9 + "d" + "aaa" + "d" * 6 + "d" + "s" + "d" * 6 + "d" + "x" * 14 + "d" + "d"


def normalize_line1(raw: str, known_codes: set[str] | None = None) -> str:
    s = clean(raw)
    if known_codes and s.startswith("P") and len(s) >= 5 and s[2:5] not in known_codes and s[1:4] in known_codes:
        s = "P<" + s[1:]  # el OCR se comió el "<" después de la P
    # El OCR a veces se come la "P" o lee "P<" como "PK" / "PC": se fuerza el inicio.
    if not s.startswith("P"):
        m = re.search(r"P[A-Z<][A-Z]{3}", s)
        s = s[m.start():] if m else "P" + s
    s = _fit(s)
    s = _map(s, L1_KIND)
    if s[1] not in "<ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        s = s[0] + "<" + s[2:]
    return s


def normalize_line2(raw: str) -> str:
    s = clean(raw)
    s = _fit(s)
    return _map(s, L2_KIND)


# ---------------------------------------------------------------- reparación


def _repair_candidates(value: str, expected: str) -> list[tuple[str, str]]:
    """Sustituciones de UN carácter confusable que hacen cuadrar el dígito verificador."""
    candidates = set()
    for i, ch in enumerate(value):
        for alt in _CONFUSABLE.get(ch, ""):
            cand = value[:i] + alt + value[i + 1:]
            if str(check_digit(cand)) == expected:
                candidates.add((cand, expected))
    for alt in _CONFUSABLE.get(expected, ""):
        if alt.isdigit() and str(check_digit(value)) == alt:
            candidates.add((value, alt))  # el que estaba mal leído es el verificador
    return sorted(candidates)


def _has_content(value: str) -> bool:
    return value.strip("<") != ""


def _date(yymmdd: str, *, future: bool) -> date | None:
    if not yymmdd.isdigit():
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    if future:
        year = 2000 + yy
    else:
        year = 2000 + yy if yy <= date.today().year % 100 else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _composite(l2: str) -> str:
    return l2[0:10] + l2[13:20] + l2[21:43]


def _composite_ok(l2: str) -> bool:
    if not (_has_content(l2[0:9]) and l2[13:19].isdigit()):
        return False
    return l2[43].isdigit() and str(check_digit(_composite(l2))) == l2[43]


def _verify(l2: str, start: int, length: int, nombre: str, checks: list[MrzCheck],
            *, es_fecha: bool = False, futura: bool = False, opcional: bool = False) -> str:
    value, expected = l2[start:start + length], l2[start + length]
    if opcional and not _has_content(value):
        # Campo opcional vacío: su dígito debe ser 0 ó '<'; no cuenta como validación real.
        if expected in "0<":
            return l2
        checks.append(MrzCheck(nombre, False))
        return l2
    if not _has_content(value):
        checks.append(MrzCheck(nombre, False))
        return l2
    if expected.isdigit() and str(check_digit(value)) == expected:
        checks.append(MrzCheck(nombre, True))
        return l2
    options = []
    if expected.isdigit():
        for cand, digit in _repair_candidates(value, expected):
            if es_fecha and _date(cand, future=futura) is None:
                continue
            options.append(l2[:start] + cand + digit + l2[start + length + 1:])
    # Si varias reparaciones cuadran, se queda la que además cuadra con el dígito compuesto.
    # Si ninguna cuadra con el compuesto (quizá roto por otro error), sólo se acepta si es única.
    con_compuesto = [o for o in options if _composite_ok(o)]
    if len(con_compuesto) > 1:
        # Cambiar el dato y cambiar su dígito pueden dar el mismo compuesto: se prefiere corregir el dato.
        con_compuesto = [o for o in con_compuesto if o[start + length] == expected]
    if len(con_compuesto) == 1:
        options = con_compuesto
    if len(options) == 1:
        checks.append(MrzCheck(nombre, True, corregido=True))
        return options[0]
    checks.append(MrzCheck(nombre, False))
    return l2


def _names(l1: str) -> tuple[str | None, str | None]:
    zone = l1[5:].rstrip("<")
    parts = zone.split("<<", 1)
    surnames = " ".join(p for p in parts[0].split("<") if p)
    given = " ".join(p for p in parts[1].split("<") if p) if len(parts) > 1 else ""
    return surnames or None, given or None


def parse(lines: list[str]) -> MrzTD3 | None:
    """Recibe las 2 líneas crudas (en orden) y devuelve los datos con sus validaciones.

    Si la línea 2 no mide 44 caracteres (el OCR se comió o inventó uno), se prueban las variantes
    con un '<' insertado o un carácter quitado en cada posición y se queda la que más dígitos
    verificadores cuadra."""
    if len(lines) < 2 or not lines[1]:
        return None
    raw2 = clean(lines[1])
    variants = [raw2]
    if len(raw2) == LINE_LEN - 1:
        variants += [raw2[:i] + "<" + raw2[i:] for i in range(len(raw2) + 1)]
    elif len(raw2) == LINE_LEN + 1:
        variants += [raw2[:i] + raw2[i + 1:] for i in range(len(raw2))]
    best_r = None
    for var in variants:
        r = _parse_lines(lines[0] or "", var)
        if best_r is None or (r.n_validos, not r.corregido) > (best_r.n_validos, not best_r.corregido):
            best_r = r
        if best_r.n_validos >= 4:
            break
    return best_r


def _parse_lines(raw1: str, raw2: str) -> MrzTD3:
    from .validators import ICAO_CODES

    l1 = normalize_line1(raw1, ICAO_CODES)
    l2 = normalize_line2(raw2)

    checks: list[MrzCheck] = []
    l2 = _verify(l2, 0, 9, "mrz_numero", checks)
    l2 = _verify(l2, 13, 6, "mrz_fecha_nacimiento", checks, es_fecha=True)
    l2 = _verify(l2, 21, 6, "mrz_vencimiento", checks, es_fecha=True, futura=True)
    l2 = _verify(l2, 28, 14, "mrz_opcional", checks, opcional=True)
    checks.append(MrzCheck("mrz_compuesto", _composite_ok(l2)))

    r = MrzTD3(lineas=[l1, l2], checks=checks)
    r.tipo_documento = l1[0:2].replace("<", "") or None
    r.pais_emisor = l1[2:5].replace("<", "") or None
    r.apellidos, r.nombres = _names(l1)
    num = l2[0:9].rstrip("<")
    r.numero = num or None
    r.nacionalidad = l2[10:13].replace("<", "") or None
    r.fecha_nacimiento = _date(l2[13:19], future=False)
    r.sexo = l2[20] if l2[20] in "MFX" else None
    r.fecha_vencimiento = _date(l2[21:27], future=True)
    opt = l2[28:42].strip("<")
    r.opcional = opt or None
    return r


def best(*candidates: MrzTD3 | None) -> MrzTD3 | None:
    """Elige la lectura con más verificaciones válidas (prefiere las no corregidas)."""
    valid = [c for c in candidates if c is not None]
    if not valid:
        return None
    return max(valid, key=lambda c: (c.n_validos, not c.corregido, bool(c.nombres)))


# ---------------------------------------------------------------- detección en texto OCR

_L1_RE = re.compile(r"^P[A-Z<][A-Z<]{3}[A-Z<]{10,}")
_L2_RE = re.compile(r"^[A-Z0-9<]{9}[0-9O][A-Z<0-9]{3}[0-9O]{7}[MFX<KC][0-9O]{7}")
_TD1_RE = re.compile(r"^[IAC][A-Z<][A-Z]{3}[A-Z0-9<]{5,}")


def looks_like_line1(text: str) -> bool:
    """Línea 1 de TD3: "P" + tipo + país ICAO (admite que el OCR se haya comido el '<' o una letra)."""
    from .validators import ICAO_CODES

    t = clean(text)
    if not (_L1_RE.match(t) and len(t) >= 24 and t.count("<") >= 3):
        return False
    return t[2:5] in ICAO_CODES or t[1:4] in ICAO_CODES or (t[1] == "<" and t[2:4] + "<" in ICAO_CODES)


def line1_country(text: str) -> str | None:
    """País emisor de una línea 1 ya normalizada, sólo si es un código ICAO válido."""
    from .validators import ICAO_CODES

    code = text[2:5].replace("<", "") if text else ""
    return code if code in ICAO_CODES else None


def looks_like_line2(text: str) -> bool:
    t = clean(text)
    return bool(_L2_RE.match(t)) and len(t) >= 28


def looks_like_td1(text: str) -> bool:
    """Línea 1 de una tarjeta TD1 (p. ej. tarjeta de residente del INM: I<MEX...)."""
    t = clean(text)
    return bool(_TD1_RE.match(t)) and 24 <= len(t) <= 32 and not looks_like_line1(t)
