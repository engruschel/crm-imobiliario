"""Testes do aplicativo local (servidor, prévia, geração de formatos e detecção de idioma), sem rede."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from kindle_livros import aplicativo
from kindle_livros.formatos import salvar_formato
from kindle_livros.idioma import detectar_idioma
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.tradutor import Tradutor


class TradutorFalso(Tradutor):
    def traduzir(self, textos, destino):
        return [f"[{destino}] {t}" for t in textos]


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(aplicativo, "PASTA_TRABALHO", tmp_path)
    monkeypatch.setattr(aplicativo, "PASTA_ENTRADA", tmp_path / "entrada")
    monkeypatch.setattr(aplicativo, "PASTA_SAIDA", tmp_path / "saida")
    monkeypatch.setattr(aplicativo, "_tradutor", lambda: TradutorFalso())
    monkeypatch.setattr(aplicativo, "_fontes", {})
    srv = aplicativo.criar_servidor(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _pedir(url, dados=None, cabecalhos=None):
    req = urllib.request.Request(url, data=dados, headers=cabecalhos or {}, method="POST" if dados is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _enviar_txt(app, nome="livro.txt", texto=None):
    texto = texto or ("Capítulo 1\n" + "Era uma vez um livro com algumas palavras bonitas. " * 4 + "\n" * 2 + "Segundo parágrafo do texto. " * 3)
    dados = texto.encode("utf-8")
    status, corpo, _ = _pedir(app + "/fonte", dados, {"X-Nome-Arquivo": nome, "Content-Length": str(len(dados))})
    return status, json.loads(corpo)


def _json(app, caminho, corpo):
    dados = json.dumps(corpo).encode()
    status, resp, _ = _pedir(app + caminho, dados, {"Content-Type": "application/json", "Content-Length": str(len(dados))})
    return status, json.loads(resp)


def test_pagina_inicial_tem_convite_em_portugues(app):
    status, corpo, _ = _pedir(app + "/")
    assert status == 200
    assert "Arraste o livro aqui".encode() in corpo


def test_fluxo_completo_arrastar_previa_e_gerar_epub(app, tmp_path):
    status, fonte = _enviar_txt(app)
    assert status == 200
    assert fonte["id"] and fonte["titulo"]

    status, previa = _json(app, "/previa", {"id": fonte["id"]})
    assert status == 200
    assert previa["pares"][0]["original"] == fonte["titulo"]
    assert len(previa["pares"]) >= 1

    status, gerado = _json(app, "/gerar", {"id": fonte["id"], "formato": "epub"})
    assert status == 200
    assert gerado["arquivo"].endswith(".epub")
    assert (tmp_path / "saida" / gerado["arquivo"]).is_file()


def test_titulo_usa_nome_original_do_arquivo(app):
    _, fonte = _enviar_txt(app, nome="Dom Casmurro.txt")
    assert fonte["titulo"] == "Dom Casmurro"


def test_idioma_desconhecido_e_traduzido(app, tmp_path, monkeypatch):
    from kindle_livros import idioma as modulo_idioma

    monkeypatch.setattr(modulo_idioma, "detectar_idioma", lambda livro: None)  # simula langdetect ausente
    _, fonte = _enviar_txt(app, texto="Hello there, this is an English book with plenty of words in it.")
    assert fonte["precisa_traduzir"] is True
    _, previa = _json(app, "/previa", {"id": fonte["id"]})
    assert previa["pares"][1]["traducao"].startswith("[pt]")


def test_formato_desconhecido_e_recusado(app):
    _, fonte = _enviar_txt(app)
    status, corpo = _json(app, "/gerar", {"id": fonte["id"], "formato": "docx"})
    assert status == 400
    assert "Escolha um formato" in corpo["erro"]


def test_fonte_expirada_pede_novo_envio(app):
    status, corpo = _json(app, "/previa", {"id": "naoexiste"})
    assert status == 400
    assert "Arraste o arquivo de novo" in corpo["erro"]


def test_extensao_nao_aceita_e_recusada(app):
    status, corpo = _enviar_txt(app, nome="foto.png", texto="x")
    assert status == 400
    assert "PDF, EPUB ou TXT" in corpo["erro"]


def test_download_so_entrega_formatos_de_livro_da_pasta_de_saida(app, tmp_path):
    (tmp_path / "saida").mkdir()
    (tmp_path / "saida" / "ok.pdf").write_bytes(b"%PDF")
    (tmp_path / "segredo.txt").write_text("nao")
    assert _pedir(app + "/arquivos/ok.pdf")[0] == 200
    assert _pedir(app + "/arquivos/..%2Fsegredo.txt")[0] == 404
    assert _pedir(app + "/arquivos/nao-existe.epub")[0] == 404


def test_link_que_nao_e_youtube_e_recusado(app):
    status, corpo = _json(app, "/fonte-link", {"url": "https://exemplo.com/outro"})
    assert status == 400
    assert "vídeo do YouTube" in corpo["erro"]


def test_gera_pdf_e_texto(tmp_path):
    livro = Livro("Meu livro", "Autora", "pt", [Capitulo("Capítulo 1", ["Olá & bem-vindo <b>teste</b>."])])
    pdf = salvar_formato(livro, tmp_path, "meu", "pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    txt = salvar_formato(livro, tmp_path, "meu", "txt")
    assert "Olá & bem-vindo" in txt.read_text(encoding="utf-8")


def test_formato_desconhecido_no_modulo_levanta_erro(tmp_path):
    from kindle_livros.erros import FormatoNaoSuportado

    with pytest.raises(FormatoNaoSuportado):
        salvar_formato(Livro("T"), tmp_path, "t", "docx")


def test_detecta_ingles_quando_langdetect_disponivel():
    pytest.importorskip("langdetect")
    livro = Livro("T", capitulos=[Capitulo("C", ["The quick brown fox jumps over the lazy dog and runs away."] * 4)])
    assert detectar_idioma(livro) == "en"


def test_sem_langdetect_devolve_none(monkeypatch):
    import builtins

    real = builtins.__import__

    def sem_langdetect(nome, *args, **kwargs):
        if nome.startswith("langdetect"):
            raise ImportError(nome)
        return real(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sem_langdetect)
    livro = Livro("T", capitulos=[Capitulo("C", ["texto qualquer"])])
    assert detectar_idioma(livro) is None
