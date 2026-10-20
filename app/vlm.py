"""Cliente del modelo de visión (VLM) con salida JSON estructurada.

Dos backends con la misma interfaz:
* ollama: API nativa (/api/chat).
* openai: API compatible con OpenAI (/v1/chat/completions) — vLLM, LM Studio, etc.

Dos formas de pedir el JSON (`vlm_formato`):
* schema: `format` (Ollama) / `response_format` (OpenAI) con el JSON Schema: la salida siempre valida.
* plantilla: la plantilla JSON va dentro del prompt (modelos de OCR especializados como GLM-OCR,
  que no soportan salida restringida).
"""

import asyncio
import base64
import json
import logging
import time
from typing import Any

import cv2
import httpx
import numpy as np

from .config import Settings, get_settings
from .documents import encode_png

log = logging.getLogger(__name__)


class VlmError(RuntimeError):
    pass


VIZ_FIELDS = [
    "tipo_documento", "pais_emisor", "numero_pasaporte", "apellidos", "nombres", "nacionalidad",
    "fecha_nacimiento", "sexo", "lugar_nacimiento", "fecha_expedicion", "fecha_vencimiento",
    "autoridad", "curp", "mrz_linea1", "mrz_linea2",
]

VIZ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {**{f: {"type": "string"} for f in VIZ_FIELDS},
                   "campos_ilegibles": {"type": "array", "items": {"type": "string"}}},
    "required": VIZ_FIELDS + ["campos_ilegibles"],
}

VIZ_PROMPT = """Eres un sistema de captura de datos. La imagen es la PÁGINA DE DATOS de un pasaporte (de cualquier país), fotocopiada en blanco y negro; puede tener sellos, firmas o texto del banco encima, y a veces otros documentos alrededor. Sólo importa el pasaporte.

Transcribe EXACTAMENTE lo impreso en cada campo, carácter por carácter, en MAYÚSCULAS:
- tipo_documento: código del campo "Tipo / Type" (normalmente "P").
- pais_emisor: código de 3 letras del campo "País emisor / Code" (MEX, COL, VEN, USA...).
- numero_pasaporte: el número de pasaporte tal cual (letras y dígitos, sin espacios).
- apellidos: todos los apellidos tal como aparecen en el pasaporte (conserva Ñ y acentos).
- nombres: todos los nombres de pila.
- nacionalidad: tal cual está impresa (p. ej. "MEXICANA", "COLOMBIANA", "UNITED STATES OF AMERICA").
- fecha_nacimiento, fecha_expedicion, fecha_vencimiento: en formato AAAA-MM-DD (el pasaporte puede traerlas como "12 ENE/JAN 1985", "12/01/1985", "1985.01.12"...).
- sexo: M o F (en pasaportes mexicanos puede estar impreso como H / M: H = M, M = F; si dice "F" o "FEMENINO" es F).
- lugar_nacimiento: tal cual (ciudad, estado, país; p. ej. "JALISCO, MEX").
- autoridad: la autoridad expedidora (p. ej. "SRE", "PASSPORT AGENCY").
- curp: sólo pasaportes mexicanos, 18 caracteres; en otros países deja "".
- mrz_linea1, mrz_linea2: los 2 renglones tipo máquina de la parte inferior (44 caracteres cada uno, empiezan con "P<"). Transcríbelos EXACTAMENTE incluyendo cada "<". Si no se ven, deja "".

Reglas:
- NO inventes ni completes datos. Si un campo no se puede leer con certeza, deja "" y agrega su nombre a campos_ilegibles.
- Ignora sellos, firmas y textos que no sean del pasaporte (p. ej. "cotejado contra original").
- Si en la imagen hay otro documento (tarjeta de residente, credencial), NO tomes datos de él.
- Distingue 0/O, 1/I, 5/S, 8/B, 2/Z en el número de pasaporte y la CURP."""

MRZ_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"mrz_linea1": {"type": "string"}, "mrz_linea2": {"type": "string"}},
    "required": ["mrz_linea1", "mrz_linea2"],
}

MRZ_PROMPT = """La imagen es la página de datos de un pasaporte fotocopiada en blanco y negro.
En la parte inferior hay 2 renglones de texto tipo máquina (MRZ) de 44 caracteres cada uno; el primero empieza con "P<".
Transcribe los 2 renglones EXACTAMENTE, carácter por carácter, incluyendo cada símbolo "<". No agregues espacios.
Si un carácter no se distingue, escribe tu mejor lectura; no omitas caracteres."""

LOCATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pasaportes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bbox_2d": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4},
                    "rotacion": {"type": "integer", "enum": [0, 90, 180, 270]},
                },
                "required": ["bbox_2d", "rotacion"],
            },
        },
    },
    "required": ["pasaportes"],
}

LOCATE_PROMPT = """La imagen es una página escaneada de {w}x{h} píxeles. Puede contener la PÁGINA DE DATOS de un pasaporte (foto, nombre, número de pasaporte y 2 renglones tipo máquina con "<<<" al pie), quizá girada, inclinada o pequeña, junto con otros documentos o sellos.

Devuelve en "pasaportes" cada página de datos de pasaporte que veas:
- bbox_2d: [x1, y1, x2, y2] en píxeles de esta imagen, el rectángulo completo de la página de datos (ligeramente holgado).
- rotacion: grados en sentido horario (0, 90, 180 o 270) que hay que girar el recorte para que el texto quede derecho.
Si no hay ningún pasaporte, devuelve una lista vacía. No incluyas tarjetas de residente, credenciales ni sellos."""


def _plantilla(schema: dict[str, Any]) -> str:
    """Plantilla JSON (valores vacíos) a partir del schema, para modelos sin salida restringida."""
    obj = {}
    for k, v in schema["properties"].items():
        obj[k] = [] if v.get("type") == "array" else ""
    return json.dumps(obj, ensure_ascii=False, indent=2)


class VlmClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._client = httpx.AsyncClient(timeout=self.s.vlm_timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def locate(self, img: np.ndarray) -> tuple[list[dict], float]:
        h, w = img.shape[:2]
        scale = min(1.0, self.s.vlm_locate_max_side / max(h, w))
        small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
        sh, sw = small.shape[:2]
        data, secs = await self.extract(small, LOCATE_PROMPT.format(w=sw, h=sh), LOCATE_SCHEMA, max_side=None)
        cards = []
        for c in data.get("pasaportes") or []:
            try:
                x1, y1, x2, y2 = (float(v) for v in c["bbox_2d"])
            except (KeyError, TypeError, ValueError):
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            cards.append({"bbox_2d": [int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)],
                          "rotacion": c.get("rotacion") if c.get("rotacion") in (0, 90, 180, 270) else 0})
        return cards, secs

    async def extract(self, img: np.ndarray, prompt: str, schema: dict[str, Any],
                      max_side: int | None = -1) -> tuple[dict, float]:
        """Devuelve (json, segundos). `max_side=-1` usa vlm_max_side; None manda la imagen tal cual."""
        if img is None or img.size == 0:
            raise VlmError("Imagen vacía")
        if max_side == -1:
            max_side = self.s.vlm_max_side
        b64 = base64.b64encode(encode_png(img, max_side)).decode()
        if self.s.vlm_formato == "plantilla":
            prompt = prompt + "\n\nResponde ÚNICAMENTE con este JSON, llenando los valores:\n" + _plantilla(schema)
        last: Exception | None = None
        for attempt in range(self.s.vlm_max_retries + 1):
            t0 = time.perf_counter()
            try:
                if self.s.vlm_backend == "ollama":
                    text = await self._ollama(b64, prompt, schema)
                else:
                    text = await self._openai(b64, prompt, schema)
                return _parse_json(text), time.perf_counter() - t0
            except (httpx.HTTPError, ValueError, KeyError) as e:
                last = e
                log.warning("VLM intento %d falló: %s", attempt + 1, e)
                await asyncio.sleep(1.5 * (attempt + 1))
        raise VlmError(f"El VLM no respondió correctamente: {last}")

    async def _ollama(self, b64: str, prompt: str, schema: dict) -> str:
        payload = {
            "model": self.s.vlm_model,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_ctx": self.s.vlm_num_ctx, "num_predict": 1000},
            "messages": [{"role": "user", "content": prompt, "images": [b64]}],
        }
        if self.s.vlm_formato == "schema":
            payload["format"] = schema
        if self.s.vlm_think is not None:
            payload["think"] = self.s.vlm_think
        r = await self._client.post(f"{self.s.vlm_base_url.rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()["message"]["content"]

    async def _openai(self, b64: str, prompt: str, schema: dict) -> str:
        payload = {
            "model": self.s.vlm_model,
            "temperature": 0,
            "max_tokens": 1000,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        }
        if self.s.vlm_formato == "schema":
            payload["response_format"] = {"type": "json_schema",
                                          "json_schema": {"name": "pasaporte", "schema": schema, "strict": True}}
        base = self.s.vlm_base_url.rstrip("/")
        url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
        r = await self._client.post(url, json=payload, headers={"Authorization": f"Bearer {self.s.vlm_api_key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    async def health(self) -> bool:
        base = self.s.vlm_base_url.rstrip("/")
        try:
            if self.s.vlm_backend == "ollama":
                r = await self._client.get(f"{base}/api/tags", timeout=5)
                names = {m["name"] for m in r.json().get("models", [])}
                return self.s.vlm_model in names or f"{self.s.vlm_model}:latest" in names
            r = await self._client.get(f"{base if base.endswith('/v1') else base + '/v1'}/models", timeout=5)
            return r.status_code == 200
        except httpx.HTTPError:
            return False


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"Respuesta sin JSON: {text[:200]}")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("La respuesta no es un objeto JSON")
    return data
