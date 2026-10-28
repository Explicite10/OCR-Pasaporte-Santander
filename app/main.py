"""
API FastAPI: recibe un PDF con un expediente y devuelve en JSON los datos de la página de datos del
pasaporte (cualquier país). La tarjeta de residente del INM, la credencial INE y cualquier otro
documento del PDF se ignoran.

Flujo por archivo:
  1. Renderizar las páginas.
  2. PaddleOCR ubica la MRZ del pasaporte (2 renglones "P<...") probando giros; si no la encuentra,
     el modelo de visión ubica el pasaporte y se repite el OCR en ese recorte.
  3. Qwen3-VL lee la página de datos; la MRZ se valida con sus dígitos de control.
  4. Fusión MRZ + lectura impresa, comprobaciones y, en modo homologado, el sello de cotejo.
  5. Responder en formato homologado (homologado.py) o propio (FORMATO_RESPUESTA).
  6. En formato homologado, agregar `validacion_plan` (plan.py): las 8 validaciones del plan de
     atención, sección Pasaporte, contra los datos de la solicitud enviados en el mismo formulario.

Rutas: POST /pasaporte (principal) y POST /extract (alias para pruebas).

Arranque local:
    uvicorn app.main:app --reload --port 8000
Prueba:
    curl -H "X-API-Key: <API_KEY del .env>" -F "file=@expediente.pdf" -F "nombre=Ana Lucia Torres Vega"          http://localhost:8000/pasaporte
"""
import asyncio
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Security, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import homologado, pipeline, plan, respuesta
from .config import get_settings
from .documents import PDF_MAGIC
from .ocr import engine
from .respuesta import http_status
from .vlm import VlmClient


def _homologado() -> bool:
    return get_settings().formato_respuesta == "homologado"


def sobre(codigo: int, mensaje: str | None = None, **extra) -> dict:
    """Sobre de la respuesta en el formato configurado (propio u homologado)."""
    if _homologado():
        return homologado.sobre(codigo, mensaje, **extra)
    return respuesta.sobre(codigo, mensaje, **extra)


def _mensaje(codigo: int) -> str:
    return (homologado.MENSAJES if _homologado() else respuesta.MENSAJES).get(codigo, "")


def _estados() -> dict[int, str]:
    return homologado.ESTADOS if _homologado() else respuesta.ESTADOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("passport-api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.vlm = VlmClient(s) if s.vlm_enabled else None
    app.state.sem = asyncio.Semaphore(s.max_concurrent_jobs)
    if s.ocr_enabled:
        log.info("Cargando PaddleOCR...")
        await asyncio.to_thread(engine.warmup)
    if app.state.vlm and not await app.state.vlm.health():
        log.warning("El VLM %s no responde en %s", s.vlm_model, s.vlm_base_url)
    yield
    if app.state.vlm:
        await app.state.vlm.aclose()


_TAGS = [
    {"name": "Pasaporte", "description": "Endpoint principal. Usar este en los sistemas que consumen la API."},
    {"name": "Pruebas", "description": "Endpoint alterno para pruebas. Responde igual que /pasaporte."},
    {"name": "Sistema", "description": "Estado del servicio."},
]

_s = get_settings()
app = FastAPI(
    title="OCR Pasaportes - Open Source",
    version="0.3.1",
    description="Extracción de la página de datos de pasaportes de cualquier país con PaddleOCR + Qwen3-VL, "
                "validación MRZ y validaciones del plan de atención.",
    openapi_tags=_TAGS,
    lifespan=lifespan,
    docs_url="/docs" if _s.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _s.enable_docs else None,
)

_api_key = APIKeyHeader(name="X-API-Key", auto_error=False, description="Valor de API_KEY del .env del servidor")
if not _s.api_key:
    log.warning("API_KEY vacia: el endpoint queda SIN proteccion")


def _error_doc(*codigos: int) -> dict:
    return {c: {"description": _estados().get(c, ""), "content": {"application/json": {"example": sobre(c)}}} for c in codigos}


def check_api_key(x_api_key: str | None = Security(_api_key)) -> None:
    esperada = get_settings().api_key
    if not esperada:
        return
    # compare_digest evita adivinar la clave midiendo tiempos de respuesta
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), esperada.encode()):
        raise HTTPException(status_code=401, detail=_mensaje(401))


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    mensaje = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Method Not Allowed") else None
    return JSONResponse(sobre(exc.status_code, mensaje), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    errores = [f"{'.'.join(str(x) for x in e.get('loc', []) if x != 'body')}: {e.get('msg')}" for e in exc.errors()]
    if _homologado():
        return JSONResponse(sobre(422, errores=errores), status_code=422)
    return JSONResponse(sobre(422, f"{_mensaje(422)} {'; '.join(errores)}"), status_code=422)


@app.exception_handler(Exception)
async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no controlado")
    return JSONResponse(sobre(500), status_code=500)


@app.get("/health", tags=["Sistema"], summary="Estado del servicio")
async def health():
    s = get_settings()
    vlm_ok = await app.state.vlm.health() if app.state.vlm else None
    return {"status": "ok" if vlm_ok is not False else "degradado", "vlm": vlm_ok,
            "modelo_vlm": s.vlm_model, "backend_vlm": s.vlm_backend,
            "formato_respuesta": s.formato_respuesta, "max_concurrent_jobs": s.max_concurrent_jobs}


_IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"II*\x00", b"MM\x00*", b"BM")


def _tipo(data: bytes) -> str | None:
    if PDF_MAGIC in data[:1024]:
        return "pdf"
    if data.startswith(_IMAGE_MAGIC) or (data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
        return "imagen"
    return None


async def _read(f: UploadFile) -> bytes | JSONResponse:
    s = get_settings()
    limit = s.max_upload_mb * 1024 * 1024
    data = await f.read(limit + 1)
    if len(data) > limit:
        return JSONResponse(sobre(413, f"{_mensaje(413)} Máximo {s.max_upload_mb} MB."), status_code=413)
    tipo = _tipo(data)
    if tipo is None:
        return JSONResponse(sobre(222), status_code=200)
    if s.solo_pdf and tipo != "pdf":
        return JSONResponse(sobre(400, None if _homologado() else "Sólo se aceptan archivos PDF."), status_code=400)
    return data


_DOC = {200: {"description": "Desenlace en `codigo`: 200, 210-212 (procesado) o 221-225 (no se extrajo)"},
        **_error_doc(400, 401, 413, 422, 500)}
_D_FILE = "PDF escaneado con la página de datos del pasaporte (puede traer otros documentos)"
_D_NOMBRE = "Nombre completo capturado en la solicitud, en cualquier orden. Alternativa: apellido_paterno, apellido_materno y nombres."
_D_CURP = "CURP capturada en la solicitud (si existe)."
_D_FECHA = "Fecha de nacimiento capturada: AAAA-MM-DD (también acepta DD/MM/AAAA)."
_D_NAC = "Nacionalidad capturada: gentilicio (Colombiana), país (Colombia) o código ISO (COL)."


def _solicitud(nombre, apellido_paterno, apellido_materno, nombres, curp, fecha_nacimiento, nacionalidad) -> plan.Solicitud:
    return plan.Solicitud(nombre=nombre, apellido_paterno=apellido_paterno, apellido_materno=apellido_materno,
                          nombres=nombres, curp=curp, fecha_nacimiento=fecha_nacimiento, nacionalidad=nacionalidad)


@app.post("/pasaporte", dependencies=[Depends(check_api_key)], responses=_DOC, tags=["Pasaporte"],
          summary="Extrae los datos de un pasaporte y valida contra la solicitud")
async def extraer_pasaporte(file: UploadFile = File(..., description=_D_FILE),
                            nombre: str | None = Form(None, description=_D_NOMBRE),
                            apellido_paterno: str | None = Form(None), apellido_materno: str | None = Form(None),
                            nombres: str | None = Form(None), curp: str | None = Form(None, description=_D_CURP),
                            fecha_nacimiento: str | None = Form(None, description=_D_FECHA),
                            nacionalidad: str | None = Form(None, description=_D_NAC)):
    return await _atender(file, _solicitud(nombre, apellido_paterno, apellido_materno, nombres, curp,
                                           fecha_nacimiento, nacionalidad))


@app.post("/extract", dependencies=[Depends(check_api_key)], responses=_DOC, tags=["Pruebas"],
          summary="Pruebas: mismo resultado que /pasaporte")
async def extract(file: UploadFile = File(..., description=_D_FILE), nombre: str | None = Form(None),
                  apellido_paterno: str | None = Form(None), apellido_materno: str | None = Form(None),
                  nombres: str | None = Form(None), curp: str | None = Form(None),
                  fecha_nacimiento: str | None = Form(None), nacionalidad: str | None = Form(None)):
    return await _atender(file, _solicitud(nombre, apellido_paterno, apellido_materno, nombres, curp,
                                           fecha_nacimiento, nacionalidad))


async def _atender(file: UploadFile, solicitud: plan.Solicitud | None = None) -> JSONResponse:
    data = await _read(file)
    if isinstance(data, JSONResponse):
        return data
    async with app.state.sem:
        result = await pipeline.process([data], app.state.vlm, file.filename)
    body = homologado.construir(result) if _homologado() else respuesta.construir(result)
    # Validaciones del plan de atención (sección Pasaporte): siempre que se evaluó el documento
    categoria = (body.get("clasificacion") or {}).get("categoria") if _homologado() else None
    if categoria:
        body["validacion_plan"] = plan.evaluar(categoria, body.get("datos"), body.get("mrz"),
                                               solicitud or plan.Solicitud(), get_settings().regla_vigencia)
    log.info("archivo procesado codigo=%s cumple_plan=%s paginas=%s tiempo_ms=%s", body["codigo"],
             body.get("validacion_plan", {}).get("cumple"),
             result.meta.paginas if result.meta else "?", result.meta.tiempo_total_ms if result.meta else "?")
    return JSONResponse(body, status_code=http_status(body["codigo"]))
