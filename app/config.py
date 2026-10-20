from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración vía variables de entorno o archivo .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- VLM (modelo de visión) ---
    # "ollama" usa la API nativa de Ollama; "openai" cualquier servidor compatible (vLLM, LM Studio...).
    vlm_backend: Literal["ollama", "openai"] = "ollama"
    vlm_base_url: str = "http://localhost:11434"
    vlm_model: str = "qwen3-vl:8b-instruct"
    vlm_api_key: str = "EMPTY"
    vlm_timeout_s: float = 180.0
    vlm_max_side: int = 1600  # lado mayor (px) del recorte que se manda al VLM
    vlm_max_retries: int = 2
    vlm_num_ctx: int = 8192
    vlm_think: bool | None = None  # Ollama: False apaga el "razonamiento" en modelos que lo traen
    vlm_enabled: bool = True
    # Sin MRZ en ninguna página (pasaporte inclinado, chico o copia tenue), el VLM ubica el pasaporte
    # y se repite el OCR en ese recorte.
    vlm_localizador: bool = True
    vlm_locate_max_side: int = 1000
    # Formato de salida que entiende el modelo: "schema" (format JSON schema de Ollama / json_schema de
    # OpenAI) o "plantilla" (se manda la plantilla JSON en el prompt; para modelos tipo GLM-OCR).
    vlm_formato: Literal["schema", "plantilla"] = "schema"

    # --- OCR ---
    ocr_det_model: str = "PP-OCRv5_mobile_det"
    ocr_rec_model: str = "PP-OCRv6_medium_rec"
    ocr_enabled: bool = True
    # Seguir leyendo con el OCR las páginas siguientes aunque ya se haya encontrado el pasaporte
    # (sirve para reportar otros documentos del PDF, p. ej. la tarjeta del INM; cuesta tiempo).
    ocr_todas_las_paginas: bool = False

    # --- Documento ---
    render_dpi: int = 250
    max_pages: int = 4  # páginas que se analizan (el pasaporte viene al principio)
    max_paginas_documento: int = 30  # un PDF con más páginas se rechaza (código 224)
    max_upload_mb: int = 25
    solo_pdf: bool = True

    # Rechazar lo que no parece un pasaporte (estado "rechazado" con el motivo en "error")
    rechazar_no_pasaporte: bool = True

    # --- API ---
    max_concurrent_jobs: int = 2
    api_key: str | None = None
    enable_docs: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
