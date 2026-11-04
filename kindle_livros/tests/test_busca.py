import io
import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest import mock

from kindle_livros.busca import (
    buscar,
    buscar_gutenberg,
    buscar_internet_archive,
    buscar_local,
    melhor_formato_para_conversao,
    nome_arquivo,
)


def _resposta(dados: Any) -> io.BytesIO:
    conteudo = io.BytesIO(json.dumps(dados).encode("utf-8"))
    return conteudo


def _urlopen_com(respostas: list[Any]) -> mock.Mock:
    return mock.Mock(side_effect=[_resposta(r) for r in respostas])


def test_gutenberg_mapeia_formatos_e_autores() -> None:
    dados = {"results": [{
        "title": "Emma",
        "authors": [{"name": "Austen, Jane"}],
        "formats": {
            "application/epub+zip": "https://g/emma.epub",
            "text/plain; charset=utf-8": "https://g/emma.txt",
            "text/html": "https://g/emma.html",
        },
    }]}
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", _urlopen_com([dados])) as abrir:
        resultados = buscar_gutenberg("emma")
    assert len(resultados) == 1
    assert resultados[0].autor == "Austen, Jane"
    assert resultados[0].links == {"epub": "https://g/emma.epub", "txt": "https://g/emma.txt"}
    requisicao = abrir.call_args[0][0]
    assert "search=emma" in requisicao.full_url


def test_internet_archive_lista_arquivos_aceitos() -> None:
    busca_dados = {"response": {"docs": [{"identifier": "item1", "title": "Obra", "creator": ["A", "B"]}]}}
    metadados = {"files": [{"name": "obra.epub"}, {"name": "capa.jpg"}, {"name": "obra.pdf"}]}
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", _urlopen_com([busca_dados, metadados])):
        resultados = buscar_internet_archive("obra")
    assert resultados[0].autor == "A, B"
    assert set(resultados[0].links) == {"epub", "pdf"}
    assert resultados[0].links["epub"] == "https://archive.org/download/item1/obra.epub"


def test_falha_de_rede_vira_erro_de_busca() -> None:
    erro = urllib.error.URLError("sem conexão")
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", side_effect=erro):
        resultados, avisos = buscar("x", ["gutenberg"])
    assert resultados == []
    assert len(avisos) == 1 and "gutenberg" in avisos[0]


def test_buscar_local_ignora_acentos_e_agrupa_formatos(tmp_path: Path) -> None:
    (tmp_path / "Dom Casmurro.epub").write_bytes(b"x")
    (tmp_path / "Dom Casmurro.pdf").write_bytes(b"x")
    (tmp_path / "outro.txt").write_bytes(b"x")
    resultados = buscar_local(tmp_path, "dóm")
    assert len(resultados) == 1
    assert resultados[0].titulo == "Dom Casmurro"
    assert set(resultados[0].links) == {"epub", "pdf"}


def test_melhor_formato_prefere_epub_e_ignora_mobi() -> None:
    assert melhor_formato_para_conversao({"mobi": "m", "pdf": "p"}) == ("pdf", "p")
    assert melhor_formato_para_conversao({"epub": "e", "pdf": "p"}) == ("epub", "e")
    assert melhor_formato_para_conversao({"mobi": "m"}) is None


def test_nome_arquivo_remove_caracteres_proibidos() -> None:
    assert nome_arquivo('Título: "ruim"/x', "epub") == "Título ruimx.epub"


def test_pasta_local_obrigatoria_para_fonte_local() -> None:
    resultados, avisos = buscar("x", ["local"])
    assert resultados == []
    assert "--pasta-local" in avisos[0]
