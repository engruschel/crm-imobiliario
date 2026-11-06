"""Testes do backend de tradução por IA (Claude), sem rede: o transporte é simulado."""

import json
from pathlib import Path

import pytest

from kindle_livros.erros import ErroTraducao
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.tradutor import ClaudeBackend, TradutorComCache, traduzir_livro


def resposta(texto: str) -> dict:
    return {"content": [{"type": "text", "text": texto}]}


class Transporte:
    """Registra os pedidos e devolve respostas da fila."""

    def __init__(self, *respostas):
        self.fila = list(respostas)
        self.pedidos: list[tuple[str, dict, dict]] = []

    def __call__(self, url, corpo, cabecalhos):
        self.pedidos.append((url, corpo, cabecalhos))
        item = self.fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def sem_espera(_segundos: float) -> None:
    return None


def backend(transporte, **kw):
    return ClaudeBackend(chave="sk-teste", transporte=transporte, dormir=sem_espera, **kw)


def test_envia_chave_modelo_e_textos_no_formato_esperado():
    t = Transporte(resposta('["Hello", "World"]'))
    saida = backend(t, modelo="claude-sonnet-5-5").traduzir(["Olá", "Mundo"], "en")
    assert saida == ["Hello", "World"]
    url, corpo, cab = t.pedidos[0]
    assert url.endswith("/v1/messages")
    assert cab["x-api-key"] == "sk-teste"
    assert cab["anthropic-version"] == "2023-06-01"
    assert corpo["model"] == "claude-sonnet-5-5"
    assert json.loads(corpo["messages"][0]["content"]) == ["Olá", "Mundo"]
    assert "en" in corpo["system"]


def test_aceita_array_dentro_de_bloco_de_codigo():
    t = Transporte(resposta('```json\n["Hi"]\n```'))
    assert backend(t).traduzir(["Oi"], "en") == ["Hi"]


def test_sem_chave_erro_claro(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ErroTraducao, match="ANTHROPIC_API_KEY"):
        ClaudeBackend()


def test_chave_recusada_nao_e_repetida():
    from kindle_livros.tradutor import _ErroFatal

    t = Transporte(_ErroFatal("A API recusou a chave (HTTP 401)"))
    with pytest.raises(ErroTraducao, match="recusou a chave"):
        backend(t).traduzir(["x"], "en")
    assert len(t.pedidos) == 1


def test_falha_temporaria_e_repetida_e_depois_funciona():
    t = Transporte(ErroTraducao("HTTP 429"), resposta('["ok"]'))
    assert backend(t).traduzir(["x"], "en") == ["ok"]
    assert len(t.pedidos) == 2


def test_resposta_com_numero_errado_de_itens_e_repetida_e_falha_no_fim():
    t = Transporte(resposta('["so um"]'), resposta('["so um"]'), resposta('["so um"]'))
    with pytest.raises(ErroTraducao, match="1 itens para 2 textos"):
        backend(t, tentativas=3).traduzir(["a", "b"], "en")
    assert len(t.pedidos) == 3


def test_resposta_sem_array_vira_erro():
    t = Transporte(resposta("Desculpe, não posso."), resposta('["ok"]'))
    assert backend(t).traduzir(["x"], "en") == ["ok"]


def test_cache_nao_chama_a_ia_de_novo(tmp_path: Path):
    t = Transporte(resposta('["Hello"]'))
    cache = TradutorComCache(backend(t), tmp_path / "cache.json")
    assert cache.traduzir(["Olá"], "en") == ["Hello"]
    assert cache.traduzir(["Olá"], "en") == ["Hello"]
    assert len(t.pedidos) == 1


def test_traduzir_livro_completo_com_ia_preserva_estrutura():
    livro = Livro("Título", "Autor", "pt", [Capitulo("Cap 1", ["Um.", "Dois."])])

    def tradutor_falso(url, corpo, cab):
        itens = json.loads(corpo["messages"][0]["content"])
        return resposta(json.dumps([f"EN:{i}" for i in itens], ensure_ascii=False))

    traduzido = traduzir_livro(livro, backend(tradutor_falso), "en")
    assert traduzido.idioma == "en"
    assert traduzido.capitulos[0].titulo == "EN:Cap 1"
    assert traduzido.capitulos[0].paragrafos == ["EN:Um.", "EN:Dois."]
