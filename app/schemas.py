"""Modelos de la respuesta JSON de la API."""

from typing import Literal

from pydantic import BaseModel, Field

Confianza = Literal["alta", "media", "baja"]
Resultado = Literal["ok", "falla", "no_aplica"]


class Mrz(BaseModel):
    lineas: list[str] = Field(default_factory=list)
    tipo_documento: str | None = None
    pais_emisor: str | None = None
    numero: str | None = None
    nacionalidad: str | None = None
    fecha_nacimiento: str | None = None
    sexo: str | None = None
    fecha_vencimiento: str | None = None
    apellidos: str | None = None
    nombres: str | None = None
    opcional: str | None = None
    digitos_control: dict[str, bool] = Field(default_factory=dict)
    integra: bool = False
    origen: str | None = Field(None, description="ocr | vlm")


class DatosPasaporte(BaseModel):
    tipo_documento: str | None = None
    pais_emisor: str | None = Field(None, description="Código ICAO de 3 letras")
    pais_emisor_nombre: str | None = None
    numero_pasaporte: str | None = None
    apellidos: str | None = None
    nombres: str | None = None
    nombre_completo: str | None = None
    nacionalidad: str | None = Field(None, description="Código ICAO de 3 letras (de la MRZ)")
    nacionalidad_impresa: str | None = None
    fecha_nacimiento: str | None = Field(None, description="AAAA-MM-DD")
    sexo: str | None = Field(None, description="M | F | X")
    lugar_nacimiento: str | None = None
    fecha_expedicion: str | None = Field(None, description="AAAA-MM-DD")
    fecha_vencimiento: str | None = Field(None, description="AAAA-MM-DD")
    vigente: bool | None = None
    autoridad: str | None = None
    curp: str | None = Field(None, description="Sólo pasaportes mexicanos")
    mrz: Mrz | None = None


class Validacion(BaseModel):
    regla: str
    resultado: Resultado
    detalle: str | None = None


class Meta(BaseModel):
    tiempo_total_ms: int
    tiempos_ms: dict[str, int] = Field(default_factory=dict)
    modelo_vlm: str | None = None
    paginas: int = 0
    pagina_pasaporte: int | None = None
    rotado: bool = False
    recorte: str | None = Field(None, description="ancla | localizador | pagina_completa")
    mrz_fuente: str | None = None
    otros_documentos: list[str] = Field(default_factory=list)
    caracteres_leidos: int = 0
    categoria: Literal["pasaporte", "otro", "hoja_en_blanco"] | None = None
    documento_detectado: str | None = Field(None, description="Si no es pasaporte: qué parece (tarjeta_residente_inm...)")


class ResultadoPasaporte(BaseModel):
    archivo: str | None = None
    estado: Literal["ok", "revisar", "error", "rechazado"]
    datos: DatosPasaporte = Field(default_factory=DatosPasaporte)
    confianza: dict[str, Confianza] = Field(default_factory=dict)
    campos_a_revisar: list[str] = Field(default_factory=list)
    validaciones: list[Validacion] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)
    error: str | None = None
    error_codigo: int | None = None
    meta: Meta | None = None
    recortes: dict[str, str] | None = Field(None, description="PNG en base64 (sólo si se pide)")
    # --- Internos (alimentan el formato homologado; el formato propio no los muestra) ---
    lectura_impresa: dict[str, str] = Field(default_factory=dict,
                                            description="Lo que el VLM leyó en la hoja de datos, ya normalizado")
    correcciones: list[dict[str, str]] = Field(default_factory=list,
                                               description="Datos que se corrigieron: campo, leido, quedo, fuente")
    sello_lectura: dict | None = Field(None, description="Lectura cruda del sello de cotejo (si se buscó)")
    pasaportes_detectados: int = 1
