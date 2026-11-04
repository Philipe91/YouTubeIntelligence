"""Roteiro do agente: JSON validado contra um catálogo fechado.

É daqui que o texto do agente entra no pipeline. Ele só pode virar dado de cena: nada aqui
produz código ou argumento de linha de comando.
"""
from __future__ import annotations

import re
import tomllib
import unicodedata
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from ..config import BACKEND_DIR
from .store import StudioError

CATALOG_PATH = BACKEND_DIR / "config" / "bq_catalogo.toml"
_ID = re.compile(r"^[a-z0-9_]{1,40}$")


@lru_cache(maxsize=1)
def catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("rb") as handle:
        return tomllib.load(handle)


def _clean(text: str) -> str:
    if any(unicodedata.category(ch) in {"Cc", "Cf", "Cs", "Co"} for ch in text):
        raise ValueError("texto com caracteres de controle ou invisíveis")
    return text.strip()


def _words(text: str) -> list[str]:
    return text.split()


class Placa(BaseModel):
    model_config = ConfigDict(extra="forbid")
    txt: str = Field(min_length=1, max_length=32)
    sub: str = Field(default="", max_length=32)
    em: str | None = Field(default=None, max_length=32)
    _limpo = field_validator("txt", "sub")(_clean)


class Cena(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str = Field(min_length=3, max_length=220)
    m: Literal["mundo", "quill", "numero", "documento", "relogio"]
    set: str | None = None
    quem: str | None = None
    fx: list[tuple[str, str]] = Field(default_factory=list, max_length=4)
    placa: Placa | None = None
    snap: str | None = None
    drama: bool = False
    enquadre: Literal["largo"] | None = None
    acao: str | None = None
    valor: str | None = Field(default=None, pattern=r"^[0-9]{1,3}$")
    rotulo: str | None = Field(default=None, max_length=28)
    titulo: str | None = Field(default=None, max_length=28)
    linhas: int | None = Field(default=None, ge=1, le=6)
    carimbo: str | None = Field(default=None, max_length=18)
    hora: str | None = Field(default=None, pattern=r"^[0-9]{1,2}:[0-9]{2}$")
    vira: str | None = Field(default=None, pattern=r"^[0-9]{1,2}:[0-9]{2}$")
    em: str | None = Field(default=None, max_length=32)

    _limpo = field_validator("texto", "rotulo", "titulo", "carimbo")(lambda text: _clean(text) if text is not None else text)

    @model_validator(mode="after")
    def _coerente(self) -> "Cena":
        cat = catalog()
        if self.m == "mundo":
            if self.set not in cat["mundo"]:
                raise ValueError(f"cenário não disponível: {self.set}")
            if self.quem not in cat["mundo"][self.set]["quem"]:
                raise ValueError(f"situação não disponível em {self.set}: {self.quem}")
        else:
            if self.set is not None or self.quem is not None:
                raise ValueError("set e quem só valem para m=mundo")
            if self.m == "quill" and self.acao not in cat["graficos"]["quill_acao"]:
                raise ValueError("acao inválida para quill")
            if self.m == "numero" and not self.valor:
                raise ValueError("numero exige valor")
            if self.m == "relogio" and not (self.hora and self.vira):
                raise ValueError("relogio exige hora e vira")
            if self.m == "documento" and not self.titulo:
                raise ValueError("documento exige titulo")
        for word, name in self.fx:
            if name not in cat["som"]["fx"]:
                raise ValueError(f"efeito não disponível: {name}")
            if word not in _words(self.texto):
                raise ValueError(f"palavra do efeito fora do texto: {word}")
        for word in (self.snap, self.em, self.placa.em if self.placa else None):
            if word is not None and word not in _words(self.texto):
                raise ValueError(f"palavra de gatilho fora do texto: {word}")
        return self


class Fonte(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=3, max_length=200)
    url: str | None = Field(default=None, pattern=r"^https?://")


class Roteiro(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resumo: str = Field(min_length=10, max_length=600)
    cenas: list[Cena] = Field(min_length=1)
    fontes: list[Fonte] = Field(min_length=1, max_length=10)
    fatos_a_conferir: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _limites(self) -> "Roteiro":
        limits = catalog()["limites"]
        if len(self.cenas) > limits["max_cenas"]:
            raise ValueError(f"no máximo {limits['max_cenas']} cenas")
        total = sum(len(_words(cena.texto)) for cena in self.cenas)
        if total > limits["max_palavras"]:
            raise ValueError(f"{total} palavras: o limite é {limits['max_palavras']}")
        return self


def validate_script(payload: Any) -> dict:
    try:
        return Roteiro.model_validate(payload).model_dump(exclude_none=True)
    except ValidationError as error:
        first = error.errors()[0]
        place = ".".join(str(part) for part in first["loc"])
        raise StudioError("invalid_script", f"Roteiro inválido em {place or 'raiz'}: {first['msg']}", 422) from error


def scene_for_pipeline(cena: dict) -> dict:
    """Só os campos que o motor entende, com placa normalizada."""
    data = {key: value for key, value in cena.items() if value not in (None, False, [])}
    if "fx" in data:
        data["fx"] = [list(item) for item in data["fx"]]
    if data.get("m") == "mundo" and data.get("set") == "campo":
        data.pop("quem", None)
        data["quem"] = "silencio"
    return data


def pipeline_id(job_id: str) -> str:
    identifier = "yti_" + job_id.removeprefix("job_")
    if not _ID.match(identifier):
        raise StudioError("invalid_job_id", "Identificador de tarefa inválido.", 422)
    return identifier
