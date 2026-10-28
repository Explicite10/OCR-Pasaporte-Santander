# -*- coding: utf-8 -*-
"""Genera la documentacion PDF de integracion de la API OCR de pasaportes.

    python docs/generar_documentacion.py . docs/Documentacion_API_OCR_Pasaporte.pdf
"""
import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

PROYECTO = Path(sys.argv[1])
SALIDA = Path(sys.argv[2])
EJ = json.loads((PROYECTO / "docs" / "ejemplos_respuesta.json").read_text(encoding="utf-8"))
PROMPT = (PROYECTO / "docs" / "PROMPT_IA.md").read_text(encoding="utf-8").split("```text", 1)[1].rsplit("```", 1)[0].strip("\n")

URL = "http://172.10.30.17:18474"
VERSION_API = "0.3.1"
VERSION_DOC = "1.2"
FECHA_DOC = "27 de octubre de 2026"
FECHA_CORTA = "27/10/2026"
W, Hh = letter
AZUL = colors.HexColor("#1F3A5F")
AZUL2 = colors.HexColor("#2F5D8C")
CLARO = colors.HexColor("#E8EEF6")
GRIS = colors.HexColor("#5F6368")
LINEA = colors.HexColor("#D0D7E2")
CODIGO_BG = colors.HexColor("#F4F6F9")
VERDE = colors.HexColor("#2E7D32")
AMBAR = colors.HexColor("#B26A00")
ROJO = colors.HexColor("#B3261E")

ss = getSampleStyleSheet()
S = {
    "h1": ParagraphStyle("h1", keepWithNext=1, fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=AZUL, spaceBefore=4, spaceAfter=10),
    "h2": ParagraphStyle("h2", keepWithNext=1, fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=AZUL2, spaceBefore=12, spaceAfter=6),
    "h3": ParagraphStyle("h3", keepWithNext=1, fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=colors.black, spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", fontName="Helvetica", fontSize=9.6, leading=14, spaceAfter=6),
    "li": ParagraphStyle("li", fontName="Helvetica", fontSize=9.6, leading=14, leftIndent=14, bulletIndent=4, spaceAfter=3),
    "cel": ParagraphStyle("cel", fontName="Helvetica", fontSize=8.4, leading=11),
    "celb": ParagraphStyle("celb", fontName="Helvetica-Bold", fontSize=8.4, leading=11),
    "celw": ParagraphStyle("celw", fontName="Helvetica-Bold", fontSize=8.4, leading=11, textColor=colors.white),
    "celm": ParagraphStyle("celm", fontName="Courier", fontSize=8, leading=11),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=7.7, leading=10.2),
    "nota": ParagraphStyle("nota", fontName="Helvetica", fontSize=9, leading=13),
    "toc0": ParagraphStyle("toc0", fontName="Helvetica-Bold", fontSize=10.2, leading=15, leftIndent=0),
    "toc1": ParagraphStyle("toc1", fontName="Helvetica", fontSize=9.0, leading=12.5, leftIndent=16, textColor=GRIS),
}


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def P(t, st="p"):
    return Paragraph(t, S[st])


def H1(t):
    p = Paragraph(t, S["h1"]); p._toc = (0, t); return p


def H2(t):
    p = Paragraph(t, S["h2"]); p._toc = (1, t); return p


def H3(t):
    return Paragraph(t, S["h3"])


def LI(items, st="li"):
    return [Paragraph(t, S[st], bulletText="•") for t in items]


def m(t):
    """texto monoespaciado en linea"""
    return f'<font name="Courier" size="8.6">{esc(t)}</font>'


def _envolver(linea, ancho=104):
    """Parte lineas largas en el ultimo espacio, con sangria de continuacion."""
    if len(linea) <= ancho:
        return [linea]
    sangria = " " * (len(linea) - len(linea.lstrip()) + 4)
    out, resto = [], linea
    while len(resto) > ancho:
        corte = resto.rfind(" ", 0, ancho)
        if corte <= len(sangria):
            corte = ancho
        out.append(resto[:corte])
        resto = sangria + resto[corte:].lstrip()
    out.append(resto)
    return out


def code(texto, titulo=None, lineas_por_bloque=14):
    lineas = [x for l in texto.rstrip("\n").split("\n") for x in _envolver(l)]
    filas = []
    if titulo:
        filas.append([Paragraph(titulo, S["celw"])])
    for i in range(0, len(lineas), lineas_por_bloque):
        filas.append([Preformatted("\n".join(lineas[i:i + lineas_por_bloque]), S["code"])])
    t = Table(filas, colWidths=[17.2 * cm])
    est = [("BACKGROUND", (0, 0), (-1, -1), CODIGO_BG), ("BOX", (0, 0), (-1, -1), 0.6, LINEA),
           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]
    if titulo:
        est += [("BACKGROUND", (0, 0), (-1, 0), AZUL2), ("TOPPADDING", (0, 0), (-1, 0), 4), ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("NOSPLIT", (0, 0), (0, 1))]  # el titulo nunca queda solo al final de una pagina
    est += [("TOPPADDING", (0, 1 if titulo else 0), (-1, 1 if titulo else 0), 6),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 6)]
    t.setStyle(TableStyle(est))
    return [t, Spacer(1, 8)]


def tabla(encabezado, filas, anchos, mono_cols=(), zebra=True):
    data = [[Paragraph(h, S["celw"]) for h in encabezado]]
    for f in filas:
        data.append([Paragraph(str(c), S["celm"] if i in mono_cols else S["cel"]) for i, c in enumerate(f)])
    t = Table(data, colWidths=[a * cm for a in anchos], repeatRows=1)
    est = [("BACKGROUND", (0, 0), (-1, 0), AZUL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
           ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINEA), ("BOX", (0, 0), (-1, -1), 0.5, LINEA),
           ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
           ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if zebra:
        for i in range(2, len(data), 2):
            est.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F7F9FC")))
    t.setStyle(TableStyle(est))
    return [t, Spacer(1, 8)]


def caja(texto, color=AZUL2, fondo=CLARO, titulo=None):
    contenido = (f"<b>{titulo}</b><br/>" if titulo else "") + texto
    t = Table([[Paragraph(contenido, S["nota"])]], colWidths=[17.2 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), fondo), ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return [t, Spacer(1, 8)]


def js(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ documento

class Doc(BaseDocTemplate):
    def __init__(self, fn, **kw):
        super().__init__(fn, **kw)
        marco = Frame(2.1 * cm, 2.0 * cm, W - 4.2 * cm, Hh - 4.1 * cm, id="n")
        self.addPageTemplates([PageTemplate("portada", [Frame(0, 0, W, Hh, id="p")], onPage=portada),
                               PageTemplate("normal", [marco], onPage=pagina)])

    def afterFlowable(self, f):
        if hasattr(f, "_toc"):
            nivel, texto = f._toc
            clave = f"s{id(f)}"
            self.canv.bookmarkPage(clave)
            self.canv.addOutlineEntry(texto, clave, level=nivel, closed=nivel > 0)
            self.notify("TOCEntry", (nivel, texto, self.page, clave))


def portada(c, d):
    c.saveState()
    c.setFillColor(AZUL); c.rect(0, Hh - 9.5 * cm, W, 9.5 * cm, stroke=0, fill=1)
    c.setFillColor(AZUL2); c.rect(0, Hh - 9.8 * cm, W, 0.3 * cm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 11); c.drawString(2.4 * cm, Hh - 3.0 * cm, "GUÍA DE INTEGRACIÓN PARA DESARROLLADORES")
    c.setFont("Helvetica-Bold", 28); c.drawString(2.4 * cm, Hh - 4.6 * cm, "API OCR de")
    c.drawString(2.4 * cm, Hh - 5.8 * cm, "Pasaportes")
    c.setFont("Helvetica", 12.5)
    c.drawString(2.4 * cm, Hh - 7.2 * cm, "Extracción de la página de datos de pasaportes de cualquier país")
    c.drawString(2.4 * cm, Hh - 7.8 * cm, "con PaddleOCR, Qwen3-VL y validación MRZ (open source)")
    c.setFillColor(colors.black)
    y = Hh - 12 * cm
    filas = [("Endpoint principal", f"POST {URL}/pasaporte"), ("Autenticación", "Header X-API-Key"),
             ("Formato de respuesta", "JSON"),
             ("Versión de la API", VERSION_API), ("Versión del documento", f"{VERSION_DOC} · {FECHA_DOC}"),
             ("Elaborado por", "Alexis Eduardo Juárez Jaimes")]
    for k, v in filas:
        c.setFont("Helvetica-Bold", 10); c.setFillColor(GRIS); c.drawString(2.4 * cm, y, k.upper())
        c.setFont("Helvetica", 11.5); c.setFillColor(colors.black); c.drawString(7.4 * cm, y, v)
        c.setStrokeColor(LINEA); c.line(2.4 * cm, y - 0.35 * cm, W - 2.4 * cm, y - 0.35 * cm)
        y -= 1.05 * cm
    c.setFont("Helvetica", 8.5); c.setFillColor(GRIS)
    c.drawString(2.4 * cm, 2.0 * cm, "Uso interno. Contiene la especificación técnica del servicio; no contiene datos de clientes.")
    c.restoreState()


def pagina(c, d):
    c.saveState()
    c.setStrokeColor(LINEA); c.line(2.1 * cm, Hh - 1.45 * cm, W - 2.1 * cm, Hh - 1.45 * cm)
    c.setFont("Helvetica", 7.8); c.setFillColor(GRIS)
    c.drawString(2.1 * cm, Hh - 1.25 * cm, "API OCR de Pasaportes · Guía de integración")
    c.drawRightString(W - 2.1 * cm, Hh - 1.25 * cm, f"v{VERSION_DOC} · {FECHA_CORTA}")
    c.drawString(2.1 * cm, 1.2 * cm, "Uso interno")
    c.drawRightString(W - 2.1 * cm, 1.2 * cm, f"Página {d.page}")
    c.restoreState()


st = []
st += [NextPageTemplate("normal"), PageBreak()]

# ------------------------------------------------------------------ indice
st.append(Paragraph("Contenido", S["h1"]))
toc = TableOfContents()
toc.levelStyles = [S["toc0"], S["toc1"]]
toc.dotsMinLevel = 0
toc.tableStyle = TableStyle([("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)])
st += [toc, PageBreak()]

# ------------------------------------------------------------------ 1
st.append(H1("1. Qué hace esta API"))
st.append(P("La API recibe un expediente escaneado en PDF y devuelve en JSON los datos de la <b>página de datos del "
            "pasaporte</b>, de cualquier país. Si el expediente trae otros documentos (tarjeta de residente del INM, "
            "credencial INE, solicitudes, recibos, etc.), esas páginas se ignoran y no se extrae nada de ellas."))
st.append(P("Todo corre en el servidor de la empresa con modelos <b>open source</b> (PaddleOCR y Qwen3-VL): los "
            "documentos no salen a ningún servicio externo y no hay costo por página."))
st.append(H2("1.1 Cómo funciona por dentro"))
st += tabla(["Paso", "Qué ocurre"], [
    ("1. Recepción", "Valida la API key, que el archivo sea PDF, su tamaño y que se pueda abrir."),
    ("2. Localización", "PaddleOCR lee las páginas y ubica la zona MRZ del pasaporte (2 líneas «P&lt;...» al pie de la "
                        "página de datos). Si la hoja viene girada prueba 90°, 180° y 270°; si aun así no la encuentra, "
                        "el modelo de visión ubica el pasaporte en la página."),
    ("3. Lectura", "El modelo de visión Qwen3-VL lee los campos impresos de la página de datos."),
    ("4. Validación MRZ", "Lee la MRZ y verifica sus cinco dígitos de control. Corrige errores típicos de lectura "
                          "(O/0, I/1, S/5...) solo cuando el dígito de control lo confirma."),
    ("5. Sello de cotejo", "Si el PDF trae el sello «COTEJADO CONTRA ORIGINAL» del banco, lee la fecha, quién revisó "
                           "y su clave."),
    ("6. Comprobaciones", "Cruza la hoja de datos contra la MRZ y la CURP (fecha, sexo, número personal) y marca "
                          "coincidencias, discrepancias y lo que no se pudo verificar."),
    ("7. Plan de atención", "Si se envían los datos capturados en la solicitud, responde las 8 validaciones del "
                            "plan de atención (sección Pasaporte) con SÍ/NO y los motivos de rechazo."),
    ("8. Respuesta", "Entrega el JSON con un código que indica la calidad de la extracción y el bloque "
                     "validacion_plan con el resultado del plan de atención."),
], [3.2, 14])
st.append(H2("1.2 Fuentes que se cruzan para cada dato"))
st.append(P("La precisión viene de que los datos críticos tienen un dígito de control en la MRZ y los demás se cruzan "
            "entre dos lectores independientes:"))
st += tabla(["Dato", "Fuentes"], [
    ("Número de pasaporte", "MRZ (dígito de control) vs lectura visual de la hoja de datos"),
    ("Fecha de nacimiento, fecha de vencimiento", "MRZ (dígito de control) vs lectura visual"),
    ("Apellidos, nombres", "MRZ (sin dígito de control, puede venir recortada) vs lectura visual, que conserva acentos y Ñ"),
    ("Sexo, nacionalidad, país emisor", "MRZ vs lectura visual"),
    ("CURP (pasaportes mexicanos)", "Lectura visual vs OCR, estructura y dígito verificador, fecha y sexo de la MRZ, "
                                   "número personal de la MRZ"),
    ("Lugar de nacimiento, expedición, autoridad", "Solo lectura visual (expedición debe ser anterior al vencimiento)"),
    ("Sello de cotejo", "OCR ubica el sello; la lectura visual toma fecha, revisó y clave"),
], [4.6, 12.6])
st.append(H2("1.3 Documentos soportados"))
st += LI(["<b>Pasaportes de cualquier país</b> con zona MRZ de 2 líneas (formato ICAO TD3). Probado con más de 40 "
          "países: México, Colombia, Venezuela, Argentina, España, Cuba, Corea, Chile, Perú, Brasil, Estados Unidos...",
          "<b>Pasaportes mexicanos:</b> además se extrae y valida la CURP.",
          "<b>No soportados:</b> tarjeta de residente del INM, credencial INE, licencias y cualquier otro documento: "
          "devuelven el código <b>225</b>."])
st += caja("La página de datos debe incluir las <b>2 líneas MRZ del pie</b> y venir en las primeras 4 páginas del PDF. "
           "La MRZ es la base de la validación: sin ella los datos se entregan, pero sin las comprobaciones contra la "
           "MRZ (códigos 212 o 210).", titulo="Importante")

# ------------------------------------------------------------------ 2
st.append(H1("2. Inicio rápido"))
st += LI(["Solicita la <b>API key</b> al responsable del servicio. Guárdala en una variable de entorno o gestor de "
          "secretos, nunca en el código.",
          f"Envía el PDF por <b>POST multipart/form-data</b> en el campo {m('file')} a {m('/pasaporte')} "
          f"con el header {m('X-API-Key')}.",
          "Para validar contra la solicitud, agrega en el mismo formulario nombre, curp, fecha_nacimiento y "
          "nacionalidad capturados (sección 4.1).",
          f"Lee {m('validacion_plan.cumple')} para saber si el documento pasa el plan de atención, y {m('codigo')} "
          "para la calidad de la extracción (secciones 5.6 y 6)."])
st += code(f'''curl -X POST "{URL}/pasaporte" \\
  -H "X-API-Key: $OCR_PASAPORTE_API_KEY" \\
  -F "file=@expediente.pdf;type=application/pdf" \\
  -F "nombre=Ana Lucia Torres Vega" \\
  -F "curp=TOVA920708MDFRGN02" \\
  -F "fecha_nacimiento=1992-07-08" \\
  -F "nacionalidad=Mexicana"''', "Ejemplo (curl)")

# ------------------------------------------------------------------ 3
st.append(H1("3. Conexión"))
st += tabla(["Concepto", "Valor"], [
    ("URL base", m(URL)),
    ("Red", "Red interna de la empresa (servidor srviatwo). El servicio no está expuesto a internet."),
    ("Protocolo", "HTTP (sin TLS). Ver sección 10, Seguridad."),
    ("Autenticación", f"Header {m('X-API-Key')} con la clave del servicio. Sin ella se responde 401."),
    ("Formato de respuesta", "JSON UTF-8, siempre con el mismo sobre (sección 5)."),
    ("Documentación interactiva", f"Swagger en {m(URL + '/docs')} y especificación OpenAPI en {m(URL + '/openapi.json')}"),
], [4.2, 13])
st.append(H2("3.1 Endpoints"))
st += tabla(["Método", "Ruta", "Auth", "Uso"], [
    ("POST", m("/pasaporte"), "Sí", "<b>Endpoint principal.</b> Usar este en todas las integraciones."),
    ("POST", m("/extract"), "Sí", "Alias para pruebas. Responde exactamente igual que /pasaporte."),
    ("GET", m("/health"), "No", "Estado del servicio, para monitoreo."),
], [1.6, 4.0, 1.3, 10.3])
st.append(H2("3.2 Límites y tiempos"))
st += tabla(["Concepto", "Valor", "Qué pasa si se excede"], [
    ("Tamaño máximo", "25 MB por archivo", "Código 413"),
    ("Tipos aceptados", "Solo PDF", "Código 400 (imágenes) o 222 (archivo que no es PDF)"),
    ("Archivos por petición", "1", "Solo se procesa el campo file"),
    ("Páginas", "Hasta 30 por archivo. Se analizan las primeras 4: el pasaporte debe venir ahí", "Código 224"),
    ("Tiempo de respuesta", "10 a 25 segundos por expediente (típico 15 a 20)", "-"),
    ("Peticiones simultáneas", "Hasta 2 se procesan a la vez", "Las demás esperan su turno (ver 7.3)"),
    ("Timeout recomendado en el cliente", "120 segundos", "-"),
], [4.4, 7.0, 5.8])

# ------------------------------------------------------------------ 4
st.append(H1("4. Petición"))
st += tabla(["Elemento", "Valor"], [
    ("Método y ruta", m("POST /pasaporte")),
    ("Content-Type", m("multipart/form-data")),
    ("Header obligatorio", m("X-API-Key: <tu clave>")),
    ("Campo del archivo", f"{m('file')} (obligatorio). Si falta o tiene otro nombre: código 422."),
    ("Tipo del archivo", f"PDF. Se recomienda indicar {m('application/pdf')} en la parte del archivo; la API "
                         "reconoce el PDF por su contenido, no por el nombre ni por el tipo declarado."),
], [4.0, 13.2])
st.append(H2("4.1 Datos de la solicitud (opcionales)"))
st.append(P("Campos de texto en el mismo formulario. Con ellos la API responde las validaciones de coincidencia del "
            "plan de atención. Sin ellos la extracción funciona igual, pero esas validaciones quedan como "
            "NO_VERIFICADO y el plan no se cumple."))
st += tabla(["Campo", "Formato", "Uso"], [
    ("nombre", "Texto", "Nombre completo capturado, en cualquier orden (nombres y apellidos)."),
    ("apellido_paterno, apellido_materno, nombres", "Texto", "Alternativa a nombre, si la solicitud los captura por separado."),
    ("curp", "18 caracteres", "Solo si la solicitud tiene CURP. Si no se envía, o el pasaporte es extranjero y no trae CURP, "
                              "la validación queda NO_APLICA y no bloquea."),
    ("fecha_nacimiento", "AAAA-MM-DD", "También acepta DD/MM/AAAA."),
    ("nacionalidad", "Texto", "Gentilicio (Colombiana), país (Colombia) o código ISO de 2 o 3 letras (CO, COL)."),
], [5.2, 2.6, 9.4], mono_cols=(0,))
st.append(H2("4.2 Ejemplos por lenguaje"))
st += code(f'''import os
import requests

URL = "{URL}/pasaporte"
API_KEY = os.environ["OCR_PASAPORTE_API_KEY"]

def extraer_pasaporte(ruta_pdf: str, solicitud: dict | None = None) -> dict:
    with open(ruta_pdf, "rb") as f:
        resp = requests.post(
            URL,
            headers={{"X-API-Key": API_KEY}},
            files={{"file": (os.path.basename(ruta_pdf), f, "application/pdf")}},
            data=solicitud or {{}},   # nombre, curp, fecha_nacimiento, nacionalidad
            timeout=120,
        )
    return resp.json()          # siempre trae codigo, estado y mensaje

r = extraer_pasaporte("expediente.pdf", {{
    "nombre": "Ana Lucia Torres Vega", "curp": "TOVA920708MDFRGN02",
    "fecha_nacimiento": "1992-07-08", "nacionalidad": "Mexicana",
}})
plan = r.get("validacion_plan")
if plan:
    print("Cumple el plan:", plan["cumple"], "-", plan["mensaje"])
    for motivo in plan["motivos_rechazo"]:
        print("  -", motivo)
if r["codigo"] in (200, 210, 211, 212):
    d = r["datos"]
    print(d.get("numero_pasaporte"), d.get("nombre_completo"))   # usar .get(): las llaves pueden faltar''',
                "Python (requests)")
st += code(f'''import {{ readFile }} from "node:fs/promises";

const URL = "{URL}/pasaporte";

export async function extraerPasaporte(rutaPdf, solicitud = {{}}) {{
  const buffer = await readFile(rutaPdf);
  const form = new FormData();
  form.append("file", new Blob([buffer], {{ type: "application/pdf" }}), "expediente.pdf");
  // solicitud: {{ nombre, curp, fecha_nacimiento, nacionalidad }} (opcionales)
  for (const [k, v] of Object.entries(solicitud)) if (v) form.append(k, v);

  const resp = await fetch(URL, {{
    method: "POST",
    headers: {{ "X-API-Key": process.env.OCR_PASAPORTE_API_KEY }},
    body: form,
    signal: AbortSignal.timeout(120_000),
  }});
  return await resp.json();   // {{ codigo, estado, mensaje, datos?, validacion_plan?, ... }}
}}''', "JavaScript / Node.js 18+ (fetch nativo)")
st += code(f'''using System.Net.Http.Headers;
using System.Text.Json;

var http = new HttpClient {{ Timeout = TimeSpan.FromSeconds(120) }};
http.DefaultRequestHeaders.Add("X-API-Key", Environment.GetEnvironmentVariable("OCR_PASAPORTE_API_KEY"));

using var form = new MultipartFormDataContent();
var archivo = new ByteArrayContent(await File.ReadAllBytesAsync("expediente.pdf"));
archivo.Headers.ContentType = new MediaTypeHeaderValue("application/pdf");
form.Add(archivo, "file", "expediente.pdf");
form.Add(new StringContent("Ana Lucia Torres Vega"), "nombre");   // datos de la solicitud (opcionales)
form.Add(new StringContent("1992-07-08"), "fecha_nacimiento");
form.Add(new StringContent("Mexicana"), "nacionalidad");

var resp = await http.PostAsync("{URL}/pasaporte", form);
using var json = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
int codigo = json.RootElement.GetProperty("codigo").GetInt32();
if (json.RootElement.TryGetProperty("validacion_plan", out var plan))
    Console.WriteLine($"Cumple: {{plan.GetProperty("cumple").GetBoolean()}}");
if (codigo is 200 or 210 or 211 or 212)
{{
    var datos = json.RootElement.GetProperty("datos");
    if (datos.TryGetProperty("numero_pasaporte", out var num)) Console.WriteLine(num.GetString());
}}''', "C# (.NET 6+)")
st += code(f'''<?php
$ch = curl_init("{URL}/pasaporte");
curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_HTTPHEADER     => ["X-API-Key: " . getenv("OCR_PASAPORTE_API_KEY")],
    CURLOPT_POSTFIELDS     => [
        "file"             => new CURLFile("expediente.pdf", "application/pdf", "expediente.pdf"),
        "nombre"           => "Ana Lucia Torres Vega",   // datos de la solicitud (opcionales)
        "fecha_nacimiento" => "1992-07-08",
        "nacionalidad"     => "Mexicana",
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT        => 120,
]);
$body = json_decode(curl_exec($ch), true);
curl_close($ch);

$cumple = $body["validacion_plan"]["cumple"] ?? false;
if (in_array($body["codigo"], [200, 210, 211, 212])) {{
    $numero = $body["datos"]["numero_pasaporte"] ?? null;   // la llave puede no venir
}}''', "PHP (cURL)")

# ------------------------------------------------------------------ 5
st.append(H1("5. Estructura de la respuesta"))
st.append(P("Todas las respuestas, exitosas o de error, comparten el mismo sobre. Los bloques de datos solo aparecen "
            "cuando aplican. <b>Regla general: si un dato no se pudo leer, la llave no aparece</b> (no viene con "
            f"{m('null')} ni vacía). Accede a los campos de forma segura."))
st += code('''{
  "codigo": 200,                 // número: qué pasó (sección 6). Úsalo para decidir.
  "estado": "PROCESADO",         // texto fijo equivalente al código
  "mensaje": "...",              // texto para mostrar a una persona; puede cambiar
  "datos": { ... },              // datos de la página de datos      (solo códigos 200-212)
  "sello": { ... },              // sello de cotejo; {} si no hay    (solo códigos 200-212)
  "mrz": { ... },                // lectura y validación de la MRZ   (solo códigos 200-212)
  "validacion": { ... },         // comprobaciones cruzadas          (solo códigos 200-212)
  "avisos": [ ... ],             // puntos a revisar por una persona (solo códigos 200-212)
  "clasificacion": { ... },      // qué documento se detectó         (códigos 200-212, 221 y 225)
  "confianza": { ... },          // nivel de confianza por campo     (solo códigos 200-212)
  "meta": { ... },               // tiempos, páginas, motor          (solo códigos 200-212)
  "validacion_plan": { ... }     // las 8 validaciones del plan      (códigos 200-212, 221 y 225)
}''', "Sobre de la respuesta")
st.append(P(f"Las nueve primeras llaves son el contrato homologado con la API de pasaportes de referencia; "
            f"{m('confianza')}, {m('meta')} y {m('validacion_plan')} son extensiones de este servicio, iguales "
            "a las de la API de forma migratoria INM."))
st.append(H2("5.1 Bloque datos"))
st += tabla(["Campo", "Tipo", "Ejemplo", "Descripción"], [
    ("tipo_documento", "texto", "P", "Tipo del documento según la página de datos (casi siempre P)."),
    ("pais_emisor", "texto", "MEX", "Código ICAO de 3 letras del país que expidió el pasaporte."),
    ("numero_pasaporte", "texto", "G12345678", "Como está impreso, sin espacios."),
    ("apellido_paterno", "texto", "TORRES", "Primera palabra de los apellidos impresos."),
    ("apellido_materno", "texto", "VEGA", "Resto de los apellidos. <b>No aparece</b> si el pasaporte trae un solo apellido."),
    ("nombres", "texto", "ANA LUCIA", "Conserva acentos y Ñ como están impresos."),
    ("nacionalidad", "texto", "MEX", "Código de 3 letras de la nacionalidad."),
    ("fecha_nacimiento", "fecha", "1992-07-08", "Formato AAAA-MM-DD."),
    ("lugar_nacimiento", "texto", "CIUDAD DE MEXICO", "Como está impreso."),
    ("sexo", "texto", "F", "<b>Tal como está impreso</b>, sin traducir (F, M, H...). Ver pregunta frecuente sobre la M."),
    ("curp", "texto", "TOVA920708MDFRGN02", "18 caracteres. Solo pasaportes mexicanos."),
    ("fecha_expedicion", "fecha", "2020-02-14", "AAAA-MM-DD."),
    ("fecha_vencimiento", "fecha", "2030-02-13", "AAAA-MM-DD."),
    ("autoridad_expedidora", "texto", "SRE", "Autoridad u oficina que expidió el pasaporte."),
    ("nombre_completo", "texto", "ANA LUCIA TORRES VEGA", "Extensión: nombres seguidos de apellidos."),
    ("pais_emisor_nombre", "texto", "MEXICO", "Extensión: nombre del país emisor."),
    ("nacionalidad_impresa", "texto", "MEXICANA", "Extensión: nacionalidad tal como está impresa."),
    ("vigente", "booleano", "true", "Extensión: misma regla que el plan (año de vencimiento igual o mayor al actual)."),
], [4.0, 1.6, 4.2, 7.4], mono_cols=(0, 2))
st.append(H2("5.2 Bloque sello"))
st.append(P("El sello «COTEJADO CONTRA ORIGINAL» que el banco pone sobre la copia. Es <b>opcional</b>: si el PDF no lo "
            f"trae, el bloque es {m('{}')} y no cuenta como falta."))
st += tabla(["Campo", "Tipo", "Descripción"], [
    ("fecha", "fecha", "Fecha del sello, AAAA-MM-DD. Si lo leído no es una fecha real se omite y se agrega un aviso."),
    ("reviso", "texto", "Nombre de quien revisó, tal como se lee. Una firma sin nombre cuenta como ausente."),
    ("clave_revisor", "texto", "Una letra y de 5 a 7 dígitos (S318204). Si no tiene esa forma se omite y se agrega un aviso."),
], [3.4, 1.7, 12.1], mono_cols=(0,))
st.append(H2("5.3 Bloque mrz"))
st.append(P("La MRZ son las dos líneas de 44 caracteres al pie de la página de datos. Sus números y fechas traen "
            f"dígitos de control, por eso es la fuente más confiable. Si no se pudo leer, el bloque es {m('{}')}."))
st += tabla(["Campo", "Tipo", "Descripción"], [
    ("lineas", "lista", "Las 2 líneas tal como quedaron después de corregirlas (44 caracteres cada una)."),
    ("tipo_documento / pais_emisor", "texto", "Tipo (P) y país emisor según la MRZ."),
    ("numero_pasaporte", "texto", "Número del pasaporte según la MRZ."),
    ("nacionalidad", "texto", "Código de 3 letras."),
    ("numero_personal", "texto", "Campo opcional de la MRZ. En pasaportes mexicanos trae el inicio de la CURP."),
    ("fecha_nacimiento / fecha_vencimiento", "fecha", "AAAA-MM-DD."),
    ("sexo", "texto", "<b>M, F o X</b> (convención internacional: M = male, F = female)."),
    ("apellido_paterno / apellido_materno / nombres", "texto", "Según la MRZ, sin acentos (la MRZ no los admite)."),
    ("nombre_abreviado", "booleano", "true si el nombre llenó toda la línea y viene recortado."),
    ("digitos_control", "objeto", "numero_pasaporte, fecha_nacimiento, fecha_vencimiento, numero_personal y compuesto: "
                                  "true si el dígito cuadra."),
    ("integra", "booleano", "true solo si los cinco dígitos de control cuadran."),
    ("origen", "texto", "texto (leída por el OCR) o entidad (leída por el modelo de visión)."),
], [5.6, 1.7, 9.9], mono_cols=(0,))
st.append(H2("5.4 Bloque validacion"))
st += tabla(["Campo", "Tipo", "Descripción"], [
    ("ok", "booleano", "true si no hay discrepancias."),
    ("completo", "booleano", "true si se pudieron correr todas las comprobaciones."),
    ("coincidencias", "lista de texto", "Comprobaciones que cuadraron."),
    ("discrepancias", "lista de texto", "Datos que se contradicen. <b>Si no está vacía, el código es 210.</b>"),
    ("sin_verificar", "lista de texto", "Comprobaciones que no se pudieron hacer (dato faltante, MRZ ilegible, sello a medias)."),
], [3.4, 2.6, 11.2], mono_cols=(0,))
st.append(P("Comprobaciones que realiza la API, con su etiqueta: " + " · ".join(m(x) for x in [
    "MRZ (dígitos de control)", "numero_pasaporte (MRZ)", "fecha_nacimiento (MRZ)", "sexo (MRZ)",
    "fecha_vencimiento (MRZ)", "nacionalidad (MRZ)", "apellido_paterno (MRZ)", "apellido_materno (MRZ)",
    "nombres (MRZ)", "curp vs número personal (MRZ)", "fecha_nacimiento (CURP)", "sexo (CURP)"]) +
    ". Los nombres se comparan sin acentos y con Ñ = N, porque la MRZ no los lleva."))
st += tabla(["Mensaje", "Cuándo aparece"], [
    (m("<etiqueta>: hoja de datos 'X' vs 'Y'"), "discrepancias: la hoja de datos dice X y la MRZ (o la CURP) dice Y."),
    (m("MRZ corrupta: fallan los dígitos de control de ..."), "discrepancias: la MRZ no cuadra; no se pudo contrastar la hoja contra ella."),
    (m("todas las comprobaciones contra la MRZ"), "sin_verificar: acompaña a la MRZ corrupta."),
    (m("MRZ completa (no se extrajo)"), "sin_verificar: no se encontró la MRZ."),
    (m("sello.<campo> (ausente)"), "sin_verificar: el sello se encontró, pero le falta ese dato."),
], [7.6, 9.6])
st.append(H2("5.5 avisos, clasificacion, confianza y meta"))
st += tabla(["Bloque", "Contenido"], [
    ("avisos", "Lista de textos con puntos que conviene revisar a mano, aunque no sean contradicciones: fecha o clave "
               "del sello ilegibles, una CURP corregida con la MRZ, o un PDF con más de un pasaporte. "
               "<b>Si no está vacía, el código es 211.</b>"),
    ("clasificacion", "categoria: pasaporte · otro · hoja_en_blanco. caracteres_leidos: cantidad de texto detectado. "
                      "confianza: siempre null (se conserva por homologación)."),
    ("confianza", "Nivel por campo: <b>alta</b> (dos fuentes coinciden o lo respalda un dígito de control), "
                  "<b>media</b> (una sola fuente), <b>baja</b> (las fuentes se contradicen o no se leyó). "
                  "Úsalo para resaltar campos en pantallas de revisión."),
    ("meta", "tiempo_total_ms, tiempos_ms, modelo_vlm, paginas, pagina_pasaporte, rotado, recorte, mrz_fuente, "
             "otros_documentos (p. ej. tarjeta_td1 si el PDF trae la tarjeta del INM), validaciones_extra y "
             "advertencias. Informativo; no tomar decisiones con él."),
], [3.0, 14.2], mono_cols=(0,))

st.append(H2("5.6 Bloque validacion_plan (plan de atención)"))
st.append(P("Responde las 8 validaciones del <b>Plan de atención - Validación documental</b>, sección Pasaporte, "
            "en el mismo orden. Es independiente de <b>codigo</b>: codigo describe la calidad de la extracción y "
            "validacion_plan dice si el documento cumple el plan. Es el mismo bloque que entrega la API de forma "
            "migratoria INM."))
st += tabla(["Campo", "Tipo", "Descripción"], [
    ("cumple", "booleano", "true solo si las 8 validaciones pasan al 100 %."),
    ("mensaje", "texto", "«Documento válido: cumple con todas las validaciones.» o «Revisar documento y motivo de rechazo»."),
    ("motivos_rechazo", "lista de texto", "Una línea por cada validación que no pasó, con su explicación."),
    ("regla_vigencia", "texto", "Regla usada para la vigencia: anio (plan de atención) o fecha."),
    ("validaciones", "lista", "Las 8 validaciones: id, pregunta, resultado, ok y detalle."),
], [3.6, 2.6, 11.0], mono_cols=(0,))
st += tabla(["#", "id", "Pregunta del plan", "Pasa cuando", "Regla"], [
    ("1", "hoja_en_blanco", "¿Es una hoja en blanco?", "NO", "Se leyó texto en el documento."),
    ("2", "imagen_ilegible", "¿La imagen es ilegible?", "NO", "SÍ si no hay texto, si faltan 2 o más datos esenciales "
                                                            "(nombre, fecha de nacimiento, número de pasaporte) o si falta uno y la MRZ tampoco cuadra."),
    ("3", "es_pasaporte", "¿Es un pasaporte?", "SI", "Página de datos de un pasaporte de cualquier país."),
    ("4", "vigente", "¿Está vigente?", "SI", "Año de vencimiento igual o mayor al año actual. Con MRZ íntegra se usa su fecha, verificada por el dígito de control."),
    ("5", "nombre_coincide", "¿El nombre coincide?", "SI", "Mismas palabras sin importar orden, acentos ni mayúsculas. Si la "
                                                          "hoja de datos se leyó distinto, se acepta cuando coincide la MRZ íntegra."),
    ("6", "curp_coincide", "¿La CURP coincide?", "SI o NO_APLICA", "Igual a la capturada. Se toleran hasta 2 caracteres que el OCR confunde "
                                                                 "(O/0, I/1, S/5, B/8...) si la CURP capturada cuadra con la fecha y el sexo verificados. "
                                                                 "Sin CURP en solicitud o pasaporte (extranjeros): NO_APLICA."),
    ("7", "fecha_nacimiento_coincide", "¿La fecha de nacimiento coincide?", "SI", "Misma fecha. Si la hoja de datos se leyó distinto, se "
                                                                             "acepta cuando coincide la de la MRZ íntegra."),
    ("8", "nacionalidad_coincide", "¿La nacionalidad coincide?", "SI", "Mismo país: acepta gentilicio, nombre del país o código ISO."),
], [0.6, 4.6, 3.4, 2.0, 6.6], mono_cols=(1,))
st += tabla(["resultado", "Significado", "¿Bloquea?"], [
    ("SI / NO", "Respuesta a la pregunta del plan.", "Según la columna «Pasa cuando»"),
    ("NO_APLICA", "La comprobación no corresponde (CURP sin dato).", "No"),
    ("NO_VERIFICADO", "Faltan datos para responder: no se envió el dato de la solicitud, no se leyó en el pasaporte "
                      "o el documento no es un pasaporte.", "Sí"),
], [3.2, 10.0, 4.0], mono_cols=(0,))
st += caja("La regla de vigencia del plan compara solo el año. Si se prefiere comparar la fecha exacta de vencimiento "
           "contra hoy, el responsable del servicio la cambia con REGLA_VIGENCIA=fecha. datos.vigente usa siempre la "
           "misma regla que el plan.", titulo="Vigencia")
st += caja("La MRZ solo respalda nombre y fecha de nacimiento cuando es <b>íntegra</b> (sus cinco dígitos de control "
           "cuadran) y el nombre no viene recortado. En ese caso el detalle de la validación lo indica.",
           titulo="Respaldo de la MRZ")

# ------------------------------------------------------------------ 6
st.append(H1("6. Códigos de respuesta"))
st += caja(f"Los códigos <b>200 a 225 viajan con HTTP 200</b>, porque la petición fue correcta aunque el documento no "
           f"sirva. Decide siempre con el campo {m('codigo')} del JSON, no con el estado HTTP. Los errores 4xx y 5xx "
           f"sí viajan con su mismo estado HTTP.", color=AMBAR, fondo=colors.HexColor("#FFF6E5"), titulo="Regla de oro")
st.append(H2("6.1 Documento procesado (trae datos)"))
st += tabla(["Código", "estado", "Significado", "Qué hacer"], [
    ("200", "PROCESADO", "Todo cuadró: hoja de datos, MRZ y CURP coinciden.", "<font color='#2E7D32'><b>Usar los datos directo.</b></font>"),
    ("211", "PROCESADO_CON_AVISOS", "Sin contradicciones, pero hay algo para revisar (ver avisos). Por ejemplo, la CURP "
                                    "se corrigió con la MRZ o la fecha del sello no se pudo leer.", "Usar los datos; revisión rápida de avisos."),
    ("212", "PROCESADO_INCOMPLETO", "Sin contradicciones, pero alguna comprobación no se pudo hacer (ver sin_verificar): "
                                    "falta un dato o el sello viene a medias.", "Usar los datos; revisar los campos de sin_verificar."),
    ("210", "PROCESADO_CON_DISCREPANCIAS", "Hay datos que se contradicen (ver discrepancias). Al menos un dato puede estar mal.",
     "<font color='#B3261E'><b>No usar sin revisión humana</b></font> de los campos indicados."),
], [1.4, 5.2, 6.0, 4.6], mono_cols=(0, 1))
st.append(H2("6.2 Documento evaluado pero no extraído (sin datos)"))
st += tabla(["Código", "estado", "Significado", "Qué hacer"], [
    ("225", "NO_ES_PASAPORTE", "El archivo no trae la página de datos de un pasaporte (tarjeta INM, INE, otro).", "Pedir el documento correcto."),
    ("221", "HOJA_EN_BLANCO", "No se leyó texto en el documento.", "Reescanear con mejor calidad."),
    ("222", "ARCHIVO_CORRUPTO", "El archivo llegó vacío, está dañado, incompleto o no es un PDF.", "Reenviar un archivo válido."),
    ("223", "PDF_PROTEGIDO", "El PDF tiene contraseña.", "Quitar la contraseña y reenviar."),
    ("224", "LIMITE_PAGINAS", "El PDF tiene más de 30 páginas.", "Enviar solo las páginas del pasaporte."),
], [1.4, 5.2, 6.0, 4.6], mono_cols=(0, 1))
st += caja("El código para «no es pasaporte» es <b>225</b>. El 220 no se usa en esta API: en la API de credenciales "
           "significa «no es INE». Así un mismo cliente distingue los dos casos.", titulo="225, no 220")
st.append(H2("6.3 Errores (sin datos, con su estado HTTP)"))
st += tabla(["Código / HTTP", "estado", "Causa", "Qué hacer", "¿Reintentar?"], [
    ("400", "ARCHIVO_NO_SOPORTADO", "Se envió una imagen u otro tipo: solo se aceptan PDF.", "Enviar el PDF.", "No"),
    ("401", "NO_AUTORIZADO", "Falta el header X-API-Key o la clave es incorrecta.", "Revisar configuración.", "No"),
    ("404", "NO_ENCONTRADO", "Ruta inexistente.", "Revisar la URL.", "No"),
    ("405", "METODO_NO_PERMITIDO", "Método HTTP incorrecto (p. ej. GET a /pasaporte).", "Usar POST.", "No"),
    ("413", "ARCHIVO_DEMASIADO_GRANDE", "Archivo mayor a 25 MB.", "Comprimir o enviar solo las páginas del pasaporte.", "No"),
    ("422", "PETICION_INVALIDA", "Falta el campo file o el multipart está mal formado. La lista errores dice qué falló.", "Corregir la petición.", "No"),
    ("500", "ERROR_INTERNO", "Error no controlado de la API.", "Reportar con hora y archivo.", "Una vez"),
    ("429 / 502 / 503", "CUOTA_EXCEDIDA / ERROR_DOCUMENT_AI / SIN_CREDENCIALES", "Reservados por homologación con la API de "
                        "referencia; este servicio no los emite.", "-", "Sí, con espera"),
], [1.9, 4.6, 4.3, 4.0, 2.4], mono_cols=(0, 1))
st += caja("Si el servidor está caído o no hay red, no llegará ningún JSON: el cliente verá un error de conexión o de "
           "timeout. Trátalo como un 500 (reintentar con espera).", titulo="Sin respuesta")

# ------------------------------------------------------------------ 7
st.append(H1("7. Integración recomendada"))
st.append(H2("7.1 Cómo decidir"))
st.append(P("Si integras el plan de atención, decide primero con <b>validacion_plan.cumple</b>: true significa que el "
            "documento pasó las 8 validaciones; false, que hay que revisar el documento con los motivos de rechazo. "
            "Usa <b>codigo</b> para los errores técnicos y para saber qué tan confiable es la extracción."))
st += code('''def decidir_plan(body: dict) -> str:
    plan = body.get("validacion_plan")
    if plan is None:                       # error técnico: no se evaluó el documento
        return decidir(body)
    if plan["cumple"]:
        return "APROBADO"
    return "REVISAR"                       # mostrar plan["motivos_rechazo"]''', "Decisión con el plan de atención (Python)")
st += code('''def decidir(body: dict) -> str:
    c = body["codigo"]
    if c == 200:
        return "ACEPTAR"                    # datos listos
    if c in (211, 212):
        return "ACEPTAR_CON_REVISION"       # revisar body["avisos"] / body["validacion"]["sin_verificar"]
    if c == 210:
        return "REVISION_OBLIGATORIA"       # revisar body["validacion"]["discrepancias"]
    if c in (221, 225):
        return "DOCUMENTO_INCORRECTO"       # pedir otro documento o reescaneo
    if c in (222, 223, 224, 400, 413, 422):
        return "ARCHIVO_INVALIDO"           # corregir el archivo o la petición; no reintentar igual
    if c == 401:
        return "ERROR_CONFIGURACION"        # API key
    return "REINTENTAR"                     # 500 o cualquier código desconocido''', "Lógica de decisión (Python)")
st.append(H2("7.2 Reintentos"))
st += LI(["<b>Reintentar solo 500 y errores de conexión o timeout</b> (y 502/503 si algún día aparecen), con espera "
          "creciente: 2 s, 4 s y 8 s (máximo 3 intentos).",
          "<b>No reintentar</b> 4xx ni los códigos 210 a 225: el resultado no cambiará enviando el mismo archivo."])
st += code('''import time, requests

def extraer_con_reintentos(ruta, intentos=3):
    for i in range(intentos):
        try:
            body = extraer_pasaporte(ruta)               # función de la sección 4.1
            if body["codigo"] not in (500, 502, 503):
                return body
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(2 ** (i + 1))                       # 2 s, 4 s, 8 s
    raise RuntimeError("OCR de pasaportes no disponible después de varios intentos")''', "Reintentos con espera (Python)")
st.append(H2("7.3 Concurrencia"))
st.append(P("La API procesa <b>hasta 2 expedientes a la vez</b> y comparte la GPU con la API de credenciales INE. "
            "Si llegan más, esperan su turno sin error y se atienden en cuanto se libera un lugar."))
st += tabla(["Peticiones enviadas a la vez", "Tiempo aproximado de la última respuesta"], [
    ("1 a 2", "15 a 25 segundos"), ("3 a 4", "30 a 50 segundos"), ("5 a 6", "45 a 75 segundos")], [7.0, 10.2])
st += LI(["<b>Recomendado:</b> en cargas masivas, que el cliente envíe como máximo 2 en paralelo; enviar más no acelera, solo hace esperar.",
          "Mantén el timeout de 120 segundos: cubre la espera de turno en cargas normales.",
          "El límite lo ajusta el responsable del servicio (MAX_CONCURRENT_JOBS)."])
st.append(H2("7.4 Buenas prácticas"))
st += LI(["Guarda el JSON completo junto al expediente: permite auditar qué devolvió la API y por qué.",
          f"Muestra en pantallas de revisión los textos de {m('discrepancias')}, {m('avisos')} y {m('sin_verificar')}, "
          f"y resalta los campos con confianza {m('media')} o {m('baja')}.",
          "Trata cualquier código desconocido como error y regístralo: permite agregar códigos nuevos sin romper la integración.",
          "No registres en logs el contenido de datos (nombres, número de pasaporte, CURP): son datos personales."])

# ------------------------------------------------------------------ 8
st.append(H1("8. Ejemplos de respuesta"))
st.append(P("Ejemplos generados por el código real de la API con <b>datos ficticios</b> "
            f"({m('scripts/generar_ejemplos.py')})."))
st.append(H2("8.1 Código 200: procesado"))
b200 = {k: v for k, v in EJ["200"].items() if k not in ("meta", "validacion_plan")}
b200["meta"] = "{ ... tiempos, páginas, motor ... }"
b200["validacion_plan"] = "{ ... ver 8.6 ... }"
st += code(js(b200), "200 PROCESADO (meta y validacion_plan resumidos)")


def parcial(c):
    b = EJ[c]
    return {k: b[k] for k in ("codigo", "estado", "mensaje")} | {"datos": "{ ... igual que en 200 ... }",
                                                                "validacion": b["validacion"], "avisos": b["avisos"]}


st.append(H2("8.2 Código 210: con discrepancias"))
st.append(P("La hoja de datos se leyó con un dígito distinto en el número de pasaporte. La MRZ, respaldada por su dígito "
            "de control, trae el número correcto: requiere revisión."))
st += code(js(parcial("210")), "210 PROCESADO_CON_DISCREPANCIAS (extracto)")
st.append(H2("8.3 Código 211: con avisos"))
st.append(P("La CURP se leyó con el dígito verificador equivocado; se corrigió con la fecha y el sexo de la MRZ y se avisa."))
st += code(js(parcial("211")), "211 PROCESADO_CON_AVISOS (extracto)")
st.append(H2("8.4 Código 212: incompleto"))
st.append(P("El sello trae fecha, pero en REVISÓ solo hay una firma y no viene la clave del revisor."))
b212 = EJ["212"]
st += code(js({k: b212[k] for k in ("codigo", "estado", "mensaje", "sello", "validacion")}), "212 PROCESADO_INCOMPLETO (extracto)")
st.append(H2("8.5 Código 225 y 221: sin datos"))
b225 = {k: v for k, v in EJ["225"].items() if k != "validacion_plan"}
b225["validacion_plan"] = {k: EJ["225"]["validacion_plan"][k] for k in ("cumple", "mensaje", "motivos_rechazo")}
st += code(js(b225), "225 NO_ES_PASAPORTE (validacion_plan resumido)")
b221 = {k: v for k, v in EJ["221"].items() if k != "validacion_plan"}
b221["validacion_plan"] = {k: EJ["221"]["validacion_plan"][k] for k in ("cumple", "mensaje", "motivos_rechazo")}
st += code(js(b221), "221 HOJA_EN_BLANCO (validacion_plan resumido)")
st.append(H2("8.6 validacion_plan: cumple"))
st += code(js(EJ["200"]["validacion_plan"]), "validacion_plan con la solicitud correcta")
st.append(H2("8.7 validacion_plan: no cumple"))
st.append(P("Solicitud con nombre incompleto, otra fecha de nacimiento y otra nacionalidad."))
bp = EJ["plan_rechazo"]
st += code(js({k: bp[k] for k in ("cumple", "mensaje", "motivos_rechazo")}), "validacion_plan con datos que no coinciden (extracto)")
st.append(H2("8.8 Errores"))
st += code("\n\n".join(f"// HTTP {c if int(c) >= 300 else 200}\n" + json.dumps(EJ[c], ensure_ascii=False)
                       for c in ("401", "400", "413", "422", "222")), "Errores (una línea por código)")

# ------------------------------------------------------------------ 9
st.append(H1("9. Health check"))
st.append(P(f"{m('GET /health')} no requiere API key. Úsalo para monitoreo o para verificar la conexión antes de integrar."))
st += code(f'''curl {URL}/health

{json.dumps(EJ["health"], ensure_ascii=False)}''', "Petición y respuesta")
st.append(P(f"{m('status')} vale {m('degradado')} si el modelo de visión no responde: el servicio está arriba pero "
            "la extracción saldría incompleta. La prueba completa es enviar un documento conocido."))

# ------------------------------------------------------------------ 10
st.append(H1("10. Seguridad"))
st += LI(["<b>API key:</b> trátala como contraseña. Guárdala en variables de entorno o un gestor de secretos; no la "
          "subas a repositorios ni la compartas por correo o chat. Si se filtra, el responsable del servicio la "
          "cambia y la anterior deja de funcionar al instante.",
          "<b>Red:</b> el servicio usa HTTP sin cifrado y está pensado para la red interna. No lo expongas a internet; "
          "si se necesita desde fuera, debe ir detrás de un proxy con HTTPS.",
          "<b>Datos personales:</b> todo se procesa en el servidor de la empresa con modelos locales; los documentos no "
          "se envían a ningún servicio externo. La API no guarda los archivos ni las respuestas.",
          "<b>Logs:</b> el servicio solo registra código, páginas y tiempo de cada petición. No registres datos de "
          "clientes en logs de aplicaciones cliente."])

# ------------------------------------------------------------------ 11
st.append(H1("11. Precisión y limitaciones"))
st.append(P("Medido el 27 de octubre de 2026 sobre el lote de Santander (503 PDFs escaneados, 481 con pasaporte): se "
            "tomaron <b>50 expedientes</b> elegidos para cubrir los casos difíciles (8 que la API había marcado para "
            "revisión, 10 mexicanos con CURP, 6 de un solo apellido, 6 con acentos o Ñ, 5 girados o sin ancla y 15 al "
            "azar; 19 países) y se capturó cada campo de la imagen con un modelo de visión independiente del pipeline, "
            "sin ver la respuesta de la API. Detalle en docs/EVALUACION.md del proyecto."))
st.append(P("Se midieron las dos salidas del mismo motor: <b>datos</b> del formato homologado (la lectura impresa, "
            "como pide la API de referencia) y el resultado interno, donde la MRZ manda cuando su dígito de control la "
            "respalda (MRZ_MANDA=true)."))
st += tabla(["Indicador", "Homologado", "Interno", "Base"], [
    ("Precisión por campo, 12 campos", "95.8 %", "<b>97.3 %</b>", "549 campos"),
    ("Precisión por campo sin autoridad (campo sin definición única)", "97.6 %", "<b>99.2 %</b>", "509 campos"),
    ("Número, fecha de nacimiento, fecha de vencimiento", "91.8 / 98.0 / 95.9 %", "<b>98.0 / 100 / 100 %</b>", "49 pasaportes"),
    ("Apellidos / nombres", "98.0 / 98.0 %", "<b>100 / 100 %</b>", "49 pasaportes"),
    ("País emisor, nacionalidad, sexo, fecha de expedición", "100 %", "100 %", "49 pasaportes"),
    ("CURP (pasaportes mexicanos)", "89.5 %", "89.5 %", "19 pasaportes"),
    ("Pasaportes con todos los campos correctos", "31 de 49", "<b>35 de 49 (71 %)</b>", ""),
    ("Campos con confianza «alta» correctos (interno)", "", "<b>100 %</b>", "348 de 348"),
    ("Documentos sin pasaporte rechazados (225)", "1 de 1", "1 de 1", "tarjeta INM + pasaporte ilegible"),
], [6.6, 2.6, 2.8, 5.2])
st += tabla(["Campo", "Exactitud (interno)", "Errores encontrados"], [
    ("pais_emisor, nacionalidad, sexo, nombres, apellidos, fecha_nacimiento, fecha_expedicion, fecha_vencimiento", "100 %", "Ninguno en 49"),
    ("numero_pasaporte", "98.0 %", "1: copia con la MRZ cortada; se entregó un número ilegible con confianza media y código 210"),
    ("lugar_nacimiento", "98.0 %", "1 parcial: el pasaporte repite el estado («SAN LUIS POTOSÍ, SAN LUIS POTOSÍ») y se entregó una vez"),
    ("curp", "89.5 %", "2: CURP tapada por el sello o por la foto fantasma, ilegible también para una persona; confianza baja"),
    ("autoridad_expedidora", "72.5 %", "11: en pasaportes mexicanos el campo trae funcionario y oficina y la API entrega uno u otro (5); "
                                      "lecturas parciales (3); copias tenues (3)"),
], [5.4, 2.2, 9.6], mono_cols=(0,))
st += caja("En la muestra, <b>todos los campos que la API marcó con confianza «alta» eran correctos</b> (348 de 348). "
           "Los errores de lectura salieron con confianza media o baja y, en el formato homologado, con código "
           "<b>210</b>: ninguno se entregó como 200. Por eso <b>codigo == 200 sirve para aprobar en automático</b> y la "
           "confianza por campo sirve para dirigir la revisión humana.", color=VERDE,
           fondo=colors.HexColor("#EAF4EA"), titulo="Lo que esto significa para la integración")
st.append(H2("11.1 Limitaciones"))
st += LI(["<b>Formato homologado:</b> datos entrega la lectura impresa aunque la MRZ, verificada por su dígito de control, "
          "diga otra cosa (regla de la API de referencia). En la muestra pasó en 8 campos de 549, siempre con código 210 y "
          "la discrepancia con ambos valores. Con MRZ_MANDA=true esos campos salen correctos.",
          "<b>autoridad_expedidora</b> no tiene una definición única entre países: en México el pasaporte imprime el "
          "nombre del funcionario y la oficina; en Bolivia y Costa Rica solo hay lugar de expedición. Conviene acordar "
          "con el consumidor qué se espera, o no usar el campo para decidir.",
          "<b>CURP tapada</b> por el sello de cotejo o por la foto fantasma: no se puede leer; sale con confianza baja.",
          "<b>Pasaportes girados en páginas posteriores</b> con alfabeto no latino y copia tenue pueden no leerse "
          "(1 caso de 50: respondió 225 en vez de los datos).",
          "<b>Muestra:</b> 50 expedientes dan intervalos anchos. 0 errores de 49 acota la exactitud real de un campo por "
          "arriba de ~94 %; 100 % en confianza alta sobre 348 campos acota el error por debajo de ~1 %.",
          "El modelo de visión no es totalmente determinista: el mismo archivo puede variar en campos sin dígito de "
          "control (autoridad, lugar de nacimiento).",
          "Procesa 2 expedientes a la vez; los demás esperan turno (sección 7.3)."])

# ------------------------------------------------------------------ 12
st.append(H1("12. Preguntas frecuentes"))
faqs = [
    ("Recibo HTTP 200 pero no hay datos.", f"Revisa {m('codigo')}: probablemente es 221, 222, 223, 224 o 225. Esos códigos viajan con HTTP 200."),
    ("¿Por qué falta una llave en datos?", "Porque ese dato no se pudo leer o no existe en el pasaporte (p. ej. apellido_materno con un solo apellido, o curp en pasaportes extranjeros). Usa acceso seguro (.get, ??, TryGetProperty)."),
    ("¿Por qué datos.sexo dice M y mrz.sexo dice F?", "datos.sexo es lo impreso: en pasaportes mexicanos «M» puede significar mujer. La MRZ usa la convención internacional (F = female). Es la misma persona."),
    ("El sello viene vacío ({}).", "El PDF no trae el sello de cotejo o no se pudo localizar. No es una falta: no cambia el código."),
    ("Recibo 212 por el sello.", "El sello se encontró pero le falta la fecha, el nombre de quien revisó o la clave. Los datos del pasaporte son válidos."),
    ("El expediente trae pasaporte y tarjeta INM.", "No pasa nada: la API toma la página del pasaporte y lo reporta en meta.otros_documentos."),
    ("El expediente solo trae la tarjeta INM.", "Responde 225: no hay pasaporte."),
    ("Me responde 401.", "Falta el header X-API-Key, tiene otro nombre o la clave es incorrecta. Las mayúsculas del nombre del header no importan; el valor sí."),
    ("Me responde 422.", "El archivo no viaja en el campo file o la petición no es multipart/form-data. La lista errores indica qué faltó."),
    ("¿Cuál uso, /pasaporte o /extract?", "/pasaporte. /extract es un alias para pruebas."),
    ("No envío datos de la solicitud y cumple sale false.", "Es lo esperado: sin esos datos no se pueden responder las validaciones de coincidencia (NO_VERIFICADO). La extracción en datos sigue siendo válida."),
    ("¿codigo 200 significa que cumple el plan?", "No necesariamente. codigo habla de la extracción; validacion_plan.cumple dice si coincide con la solicitud y está vigente."),
    ("Recibo 210 pero cumple sale true.", "Puede pasar: la hoja de datos se leyó distinto de la MRZ (210), pero la MRZ, verificada por sus dígitos de control, coincide con la solicitud. El detalle de la validación lo indica."),
    ("La CURP salió NO_APLICA.", "La solicitud no trae CURP o el pasaporte es extranjero y no tiene CURP. No bloquea el plan."),
]
for q, a in faqs:
    st.append(KeepTogether([P(f"<b>{q}</b>", "p"), P(a, "nota"), Spacer(1, 4)]))

# ------------------------------------------------------------------ 13
st.append(H1("13. Prompt para implementar con IA"))
st.append(P("Copia este prompt en un asistente de IA (Claude, ChatGPT, Copilot...) e indica el lenguaje o framework. "
            "Contiene el contrato completo para generar un cliente correcto. También está en el archivo "
            f"{m('docs/PROMPT_IA.md')} del proyecto, más fácil de copiar."))
st += code(PROMPT, "Prompt")

# ------------------------------------------------------------------ 14
st.append(KeepTogether([H1("14. Glosario")] + tabla(["Término", "Significado"], [
    ("Página de datos", "La página del pasaporte con la foto, los datos del titular y la MRZ."),
    ("MRZ", "Zona de lectura mecánica: las 2 líneas de 44 caracteres con «&lt;» al pie de la página de datos. Formato ICAO TD3."),
    ("ICAO 9303", "Estándar internacional de documentos de viaje que define la MRZ y sus códigos de país."),
    ("Dígito de control", "Número calculado a partir de un dato de la MRZ que permite detectar errores de lectura."),
    ("Número personal", "Campo opcional de la MRZ; en pasaportes mexicanos trae el inicio de la CURP."),
    ("CURP", "Clave Única de Registro de Población (18 caracteres), en pasaportes mexicanos."),
    ("Sello de cotejo", "Sello «COTEJADO CONTRA ORIGINAL» que el banco pone en la copia, con fecha, quién revisó y su clave."),
    ("PaddleOCR / Qwen3-VL", "Modelos open source que leen el texto y la imagen del pasaporte en el servidor de la empresa."),
], [3.6, 13.6])))

doc = Doc(str(SALIDA), pagesize=letter, title="API OCR de Pasaportes - Guía de integración",
          author="Alexis Eduardo Juárez Jaimes", subject="Documentación para desarrolladores", leftMargin=2.1 * cm,
          rightMargin=2.1 * cm, topMargin=2.0 * cm, bottomMargin=2.0 * cm)
doc.multiBuild(st)
print("ok", SALIDA)
