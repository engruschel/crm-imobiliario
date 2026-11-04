"""Modelo de dados comum às entradas e saídas do sistema."""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class Capitulo:
    titulo: str
    paragrafos: list[str] = field(default_factory=list)


@dataclass
class Livro:
    titulo: str
    autor: str = "Desconhecido"
    idioma: str = "pt"
    capitulos: list[Capitulo] = field(default_factory=list)


@dataclass(frozen=True)
class ResultadoBusca:
    titulo: str
    autor: str
    fonte: str
    links: dict[str, str]  # formato (ex.: "epub") -> URL de download ou caminho local


def agrupar_textos(textos: Sequence[str], limite: int) -> list[list[str]]:
    """Agrupa textos em listas cuja soma de caracteres não passa de `limite`.

    Um texto isolado maior que o limite forma um grupo sozinho; quem chama
    deve garantir que os textos já estejam fatiados.
    """
    grupos: list[list[str]] = []
    atual: list[str] = []
    tamanho = 0
    for texto in textos:
        if atual and tamanho + len(texto) > limite:
            grupos.append(atual)
            atual, tamanho = [], 0
        atual.append(texto)
        tamanho += len(texto)
    if atual:
        grupos.append(atual)
    return grupos


def dividir_em_capitulos(unidades: Sequence[Sequence[str]], por_capitulo: int) -> list[Capitulo]:
    """Cria capítulos "Parte n" agrupando `por_capitulo` unidades (páginas, trechos...)."""
    capitulos: list[Capitulo] = []
    for inicio in range(0, len(unidades), por_capitulo):
        paragrafos = [p for unidade in unidades[inicio:inicio + por_capitulo] for p in unidade if p]
        if paragrafos:
            capitulos.append(Capitulo(f"Parte {len(capitulos) + 1}", paragrafos))
    return capitulos
