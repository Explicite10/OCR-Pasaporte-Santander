import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Query, Request, Security, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import pipeline
from .config import get_settings
from .documents import PDF_MAGIC
from .ocr import engine
from .respuesta import ESTADOS, MENSAJES, construir, http_status, sobre
from .vlm import VlmClient

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


_s = get_settings()
app = FastAPI(
    title="Passport OCR API",
    version="0.1.0",
    description="Extracción estructurada de la página de datos de pasaportes (cualquier país) a partir de PDF.",
    lifespan=lifespan,
    docs_url="/docs" if _s.enable_docs else None,
    redoc_url=None,
    openapi_url="/openapi.json" if _s.enable_docs else None,
)

_api_key = APIKeyHeader(name="X-API-Key", auto_error=False,
                        description="El valor de API_KEY del .env del servidor (si no está definida, no se pide)")


def _error_doc(*codigos: int) -> dict:
    return {c: {"description": ESTADOS[c], "content": {"application/json": {"example": sobre(c)}}} for c in codigos}


def check_api_key(x_api_key: str | None = Security(_api_key)) -> None:
    expected = get_settings().api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail=MENSAJES[401])


@app.exception_handler(StarletteHTTPException)
async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    mensaje = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Method Not Allowed") else None
    return JSONResponse(sobre(exc.status_code, mensaje), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    errores = [f"{'.'.join(str(x) for x in e.get('loc', []) if x != 'body')}: {e.get('msg')}" for e in exc.errors()]
    return JSONResponse(sobre(422, f"{MENSAJES[422]} {'; '.join(errores)}"), status_code=422)


@app.exception_handler(Exception)
async def _internal_error(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Error no controlado")
    return JSONResponse(sobre(500), status_code=500)


@app.get("/health")
async def health():
    s = get_settings()
    vlm_ok = await app.state.vlm.health() if app.state.vlm else None
    return {"status": "ok" if vlm_ok is not False else "degradado", "vlm": vlm_ok,
            "modelo_vlm": s.vlm_model, "backend_vlm": s.vlm_backend}


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
        return JSONResponse(sobre(413, f"{MENSAJES[413]} Máximo {s.max_upload_mb} MB."), status_code=413)
    tipo = _tipo(data)
    if tipo is None:
        return JSONResponse(sobre(222), status_code=200)
    if s.solo_pdf and tipo != "pdf":
        return JSONResponse(sobre(400, "Sólo se aceptan archivos PDF."), status_code=400)
    return data


@app.post("/pasaporte", responses=_error_doc(400, 401, 413, 422, 500),
          summary="Extrae los datos de la página de datos de un pasaporte (PDF)")
async def extraer_pasaporte(
    file: UploadFile = File(..., description="PDF escaneado que contiene el pasaporte (puede traer otros documentos)"),
    incluir_recortes: bool = Query(False, description="Devolver el recorte del pasaporte en base64"),
    _: None = Security(check_api_key),
):
    data = await _read(file)
    if isinstance(data, JSONResponse):
        return data
    async with app.state.sem:
        result = await pipeline.process([data], app.state.vlm, file.filename, include_crops=incluir_recortes)
    body = construir(result)
    log.info("%s -> %s (%s) en %s ms", file.filename, body["codigo"], body["estado"],
             result.meta.tiempo_total_ms if result.meta else "?")
    return JSONResponse(body, status_code=http_status(body["codigo"]))
