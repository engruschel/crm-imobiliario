"""Tradução de livros por backends plugáveis, com blocos, retry e cache em disco opcional."""

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kindle_livros.config import (
    ESPERA_BASE_TRADUCAO,
    LIMITE_BLOCO_TRADUCAO,
    MAX_TOKENS_TRADUCAO,
    MODELO_TRADUCAO_PADRAO,
    TENTATIVAS_TRADUCAO,
    TIMEOUT_TRADUCAO,
    URL_ANTHROPIC_PADRAO,
    VERSAO_API_ANTHROPIC,
)
from kindle_livros.erros import DependenciaAusente, ErroTraducao
from kindle_livros.modelo import Capitulo, Livro, agrupar_textos
from kindle_livros.temporarios import caminho_temporario


class Tradutor(ABC):
    """Contrato de um backend de tradução."""

    @abstractmethod
    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        """Devolve uma tradução para cada texto, na mesma ordem."""


class DeepTranslatorBackend(Tradutor):
    """Opção alternativa: Google Tradutor pela biblioteca deep-translator (sem IA, menor qualidade)."""

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


INSTRUCAO_TRADUCAO = (
    "Você é um tradutor literário profissional. Traduza cada item do array JSON recebido "
    "para o idioma de código '{destino}'. Mantenha o sentido, o tom e a estrutura de cada item; "
    "preserve nomes próprios e termos técnicos quando for o usual; não resuma, não explique e "
    "não acrescente comentários. Responda somente com um array JSON de strings, na mesma ordem "
    "e com exatamente o mesmo número de itens."
)


class ClaudeBackend(Tradutor):
    """Tradução por IA (Claude), pela API oficial da Anthropic.

    Usa a variável ANTHROPIC_API_KEY. Envia um bloco de textos por vez como array JSON e
    espera de volta um array JSON do mesmo tamanho. Erros de chave e de modelo não são
    repetidos; limite de uso, falhas de rede e respostas malformadas são repetidos.
    """

    def __init__(
        self,
        modelo: str = MODELO_TRADUCAO_PADRAO,
        chave: str | None = None,
        url_base: str | None = None,
        tentativas: int = TENTATIVAS_TRADUCAO,
        espera: float = ESPERA_BASE_TRADUCAO,
        dormir: Callable[[float], None] = time.sleep,
        transporte: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self._chave = chave if chave is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        if not self._chave.strip():
            raise ErroTraducao(
                "Tradução por IA precisa da chave da API. Defina a variável ANTHROPIC_API_KEY "
                "(ou use --tradutor google)."
            )
        self._modelo = modelo
        self._url = (url_base or os.environ.get("ANTHROPIC_BASE_URL") or URL_ANTHROPIC_PADRAO).rstrip("/")
        self._tentativas = tentativas
        self._espera = espera
        self._dormir = dormir
        self._transporte = transporte or _enviar_http

    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        if not textos:
            return []
        ultimo_erro: Exception | None = None
        for tentativa in range(self._tentativas):
            try:
                return self._pedir(textos, destino)
            except _ErroFatal as exc:
                raise ErroTraducao(str(exc)) from exc
            except (ErroTraducao, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
                ultimo_erro = exc
                if tentativa < self._tentativas - 1:
                    self._dormir(self._espera * 2**tentativa)
        raise ErroTraducao(f"Falha na tradução por IA após {self._tentativas} tentativas: {ultimo_erro}") from ultimo_erro

    def _pedir(self, textos: list[str], destino: str) -> list[str]:
        corpo = {
            "model": self._modelo,
            "max_tokens": MAX_TOKENS_TRADUCAO,
            "system": INSTRUCAO_TRADUCAO.format(destino=destino),
            "messages": [{"role": "user", "content": json.dumps(list(textos), ensure_ascii=False)}],
        }
        cabecalhos = {
            "x-api-key": self._chave,
            "anthropic-version": VERSAO_API_ANTHROPIC,
            "content-type": "application/json",
        }
        resposta = self._transporte(f"{self._url}/v1/messages", corpo, cabecalhos)
        texto = "".join(bloco.get("text", "") for bloco in resposta.get("content", []) if bloco.get("type") == "text")
        lista = _ler_array_json(texto)
        if len(lista) != len(textos) or not all(isinstance(item, str) for item in lista):
            raise ErroTraducao(f"A IA devolveu {len(lista)} itens para {len(textos)} textos.")
        return lista


class _ErroFatal(Exception):
    """Erro que não deve ser repetido (chave recusada, modelo inexistente)."""


def _enviar_http(url: str, corpo: dict[str, Any], cabecalhos: dict[str, str]) -> dict[str, Any]:
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    pedido = urllib.request.Request(url, data=dados, headers=cabecalhos, method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT_TRADUCAO) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", "replace")[:300]
        if exc.code in (401, 403):
            raise _ErroFatal(f"A API recusou a chave (HTTP {exc.code}). Confira ANTHROPIC_API_KEY.") from exc
        if exc.code == 404 or exc.code == 400:
            raise _ErroFatal(f"A API recusou o pedido (HTTP {exc.code}): {detalhe}") from exc
        raise ErroTraducao(f"HTTP {exc.code}: {detalhe}") from exc


def _ler_array_json(texto: str) -> list[Any]:
    limpo = texto.strip()
    if limpo.startswith("```"):
        limpo = limpo.strip("`")
        if limpo.lower().startswith("json"):
            limpo = limpo[4:]
    inicio, fim = limpo.find("["), limpo.rfind("]")
    if inicio < 0 or fim < inicio:
        raise ErroTraducao("A IA não devolveu um array JSON.")
    dados = json.loads(limpo[inicio:fim + 1])
    if not isinstance(dados, list):
        raise ErroTraducao("A IA não devolveu um array JSON.")
    return dados


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
