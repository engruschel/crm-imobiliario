"""Tradução de livros por backends plugáveis, com blocos, retry e cache em disco opcional."""

import hashlib
import json
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kindle_livros.config import ESPERA_BASE_TRADUCAO, LIMITE_BLOCO_TRADUCAO, TENTATIVAS_TRADUCAO
from kindle_livros.erros import DependenciaAusente, ErroTraducao
from kindle_livros.modelo import Capitulo, Livro, agrupar_textos
from kindle_livros.temporarios import caminho_temporario


class Tradutor(ABC):
    """Contrato de um backend de tradução."""

    @abstractmethod
    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        """Devolve uma tradução para cada texto, na mesma ordem."""


class DeepTranslatorBackend(Tradutor):
    """Usa o GoogleTranslator da biblioteca deep-translator, com novas tentativas e espera exponencial."""

    def __init__(
        self,
        tentativas: int = TENTATIVAS_TRADUCAO,
        espera: float = ESPERA_BASE_TRADUCAO,
        dormir: Callable[[float], None] = time.sleep,
        fabrica: Callable[[str], Any] | None = None,
    ) -> None:
        self._tentativas = tentativas
        self._espera = espera
        self._dormir = dormir
        self._fabrica = fabrica or _fabrica_google()

    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        if not textos:
            return []
        ultimo_erro: Exception | None = None
        for tentativa in range(self._tentativas):
            try:
                saida = self._fabrica(destino).translate_batch(list(textos))
                return [trecho or "" for trecho in saida]
            except Exception as exc:  # a biblioteca levanta erros de rede, de limite e de idioma
                ultimo_erro = exc
                if tentativa < self._tentativas - 1:
                    self._dormir(self._espera * 2**tentativa)
        raise ErroTraducao(f"Falha ao traduzir após {self._tentativas} tentativas: {ultimo_erro}") from ultimo_erro


def _fabrica_google() -> Callable[[str], Any]:
    try:
        from deep_translator import GoogleTranslator
    except ImportError as exc:
        raise DependenciaAusente("Para traduzir instale: pip install deep-translator") from exc
    return lambda destino: GoogleTranslator(source="auto", target=destino)


class TradutorComCache(Tradutor):
    """Guarda as traduções em um arquivo JSON para não traduzir o mesmo texto duas vezes."""

    def __init__(self, base: Tradutor, arquivo: Path) -> None:
        self._base = base
        self._arquivo = arquivo

    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        cache = self._ler()
        faltantes = list(dict.fromkeys(t for t in textos if _chave(t, destino) not in cache))
        if faltantes:
            for original, traducao in zip(faltantes, _verificar(faltantes, self._base.traduzir(faltantes, destino))):
                cache[_chave(original, destino)] = traducao
            self._gravar(cache)
        return [cache[_chave(t, destino)] for t in textos]

    def _ler(self) -> dict[str, str]:
        if not self._arquivo.is_file():
            return {}
        try:
            dados = json.loads(self._arquivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(dados, dict):
            return {}
        return {str(k): str(v) for k, v in dados.items()}

    def _gravar(self, cache: dict[str, str]) -> None:
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        temporario = caminho_temporario(self._arquivo)
        temporario.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        temporario.replace(self._arquivo)


def traduzir_livro(livro: Livro, tradutor: Tradutor, destino: str,
                   limite: int = LIMITE_BLOCO_TRADUCAO) -> Livro:
    """Devolve uma cópia do livro traduzida, preservando títulos e a divisão em capítulos."""
    textos = [livro.titulo]
    for capitulo in livro.capitulos:
        textos.append(capitulo.titulo)
        textos.extend(capitulo.paragrafos)
    traduzidos = iter(_traduzir_textos(textos, tradutor, destino, limite))
    titulo = next(traduzidos)
    capitulos = [
        Capitulo(next(traduzidos), [next(traduzidos) for _ in capitulo.paragrafos])
        for capitulo in livro.capitulos
    ]
    return Livro(titulo, livro.autor, destino, capitulos)


def _traduzir_textos(textos: Sequence[str], tradutor: Tradutor, destino: str, limite: int) -> list[str]:
    """Fatia textos longos, traduz em blocos de até `limite` caracteres e junta os pedaços de volta."""
    pedacos: list[str] = []
    origem: list[int] = []
    for indice, texto in enumerate(textos):
        for pedaco in _partir(texto, limite):
            pedacos.append(pedaco)
            origem.append(indice)
    saidas: list[str] = []
    for bloco in agrupar_textos(pedacos, limite):
        saidas.extend(_verificar(bloco, tradutor.traduzir(bloco, destino)))
    resultado = [""] * len(textos)
    for indice, trecho in zip(origem, saidas):
        resultado[indice] = f"{resultado[indice]} {trecho}".strip()
    return resultado


def _partir(texto: str, limite: int) -> list[str]:
    """Quebra o texto em pedaços de até `limite` caracteres, preferindo quebrar entre palavras."""
    pedacos: list[str] = []
    atual = ""
    for palavra in texto.split():
        if len(palavra) > limite:
            if atual:
                pedacos.append(atual)
                atual = ""
            pedacos.extend(palavra[i:i + limite] for i in range(0, len(palavra), limite))
            continue
        candidato = f"{atual} {palavra}".strip()
        if len(candidato) > limite:
            pedacos.append(atual)
            atual = palavra
        else:
            atual = candidato
    if atual:
        pedacos.append(atual)
    return pedacos


def _verificar(entrada: Sequence[str], saida: list[str]) -> list[str]:
    if len(saida) != len(entrada):
        raise ErroTraducao(f"O backend devolveu {len(saida)} traduções para {len(entrada)} textos.")
    return saida


def _chave(texto: str, destino: str) -> str:
    return hashlib.sha256(f"{destino}\n{texto}".encode("utf-8")).hexdigest()
