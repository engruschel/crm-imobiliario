import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from kindle_livros.erros import DependenciaAusente, ErroTraducao
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.tradutor import (
    DeepTranslatorBackend,
    Tradutor,
    TradutorComCache,
    _partir,
    traduzir_livro,
)


class TradutorFalso(Tradutor):
    def __init__(self) -> None:
        self.chamadas: list[list[str]] = []

    def traduzir(self, textos: list[str], destino: str) -> list[str]:
        self.chamadas.append(list(textos))
        return [f"[{destino}] {t}" for t in textos]


def test_traduzir_livro_preserva_estrutura_e_respeita_limite() -> None:
    livro = Livro("Título", "Autor", "en", [
        Capitulo("Cap 1", ["alpha " * 50, "beta"]),
        Capitulo("Cap 2", ["gamma"]),
    ])
    tradutor = TradutorFalso()
    traduzido = traduzir_livro(livro, tradutor, "pt", limite=120)

    assert traduzido.idioma == "pt"
    assert traduzido.autor == "Autor"
    assert traduzido.titulo == "[pt] Título"
    assert [c.titulo for c in traduzido.capitulos] == ["[pt] Cap 1", "[pt] Cap 2"]
    assert len(traduzido.capitulos[0].paragrafos) == 2
    assert traduzido.capitulos[0].paragrafos[1] == "[pt] beta"
    assert all(len(texto) <= 120 for chamada in tradutor.chamadas for texto in chamada)


def test_partir_quebra_entre_palavras_e_corta_palavra_gigante() -> None:
    assert _partir("um dois tres", 7) == ["um dois", "tres"]
    assert _partir("abcdefghij", 4) == ["abcd", "efgh", "ij"]
    assert _partir("   ", 10) == []


def test_cache_evita_traduzir_o_mesmo_texto_duas_vezes(tmp_path: Path) -> None:
    base = TradutorFalso()
    cache = TradutorComCache(base, tmp_path / "cache.json")
    assert cache.traduzir(["oi", "tchau"], "pt") == ["[pt] oi", "[pt] tchau"]
    assert cache.traduzir(["oi"], "pt") == ["[pt] oi"]
    assert base.chamadas == [["oi", "tchau"]]
    assert (tmp_path / "cache.json").is_file()


def test_backend_repete_com_espera_exponencial_e_depois_desiste() -> None:
    tradutor_que_falha = mock.Mock()
    tradutor_que_falha.translate_batch.side_effect = RuntimeError("limite")
    esperas: list[float] = []
    backend = DeepTranslatorBackend(
        tentativas=3, espera=1.0, dormir=esperas.append, fabrica=lambda _destino: tradutor_que_falha,
    )
    with pytest.raises(ErroTraducao, match="3 tentativas"):
        backend.traduzir(["texto"], "pt")
    assert esperas == [1.0, 2.0]


def test_backend_recupera_apos_falha_transitoria() -> None:
    tradutor = mock.Mock()
    tradutor.translate_batch.side_effect = [RuntimeError("oscilou"), ["olá"]]
    backend = DeepTranslatorBackend(dormir=lambda _s: None, fabrica=lambda _d: tradutor)
    assert backend.traduzir(["hello"], "pt") == ["olá"]


def test_backend_sem_biblioteca_orienta_instalacao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "deep_translator", None)
    with pytest.raises(DependenciaAusente, match="deep-translator"):
        DeepTranslatorBackend()


def test_backend_com_lista_vazia_nao_chama_servico() -> None:
    fabrica: Any = mock.Mock()
    assert DeepTranslatorBackend(fabrica=fabrica).traduzir([], "pt") == []
    fabrica.assert_not_called()
