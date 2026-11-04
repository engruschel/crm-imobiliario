import zipfile
from pathlib import Path

import pytest

from kindle_livros.epub import gerar_epub
from kindle_livros.erros import ErroConversao
from kindle_livros.modelo import Capitulo, Livro


def test_epub_tem_mimetype_primeiro_e_sem_compressao(tmp_path: Path) -> None:
    saida = gerar_epub(Livro("Título", "Autor", "pt", [Capitulo("Um", ["Texto"])]), tmp_path / "l.epub")
    with zipfile.ZipFile(saida) as zf:
        primeiro = zf.infolist()[0]
        assert primeiro.filename == "mimetype"
        assert primeiro.compress_type == zipfile.ZIP_STORED
        assert zf.read("mimetype") == b"application/epub+zip"


def test_epub_contem_estrutura_obrigatoria_e_escapa_texto(tmp_path: Path) -> None:
    livro = Livro("Tom & Jerry <teste>", "Autor", "pt", [Capitulo("Cap <1>", ["a < b & c"])])
    saida = gerar_epub(livro, tmp_path / "l.epub")
    with zipfile.ZipFile(saida) as zf:
        nomes = set(zf.namelist())
        assert {"META-INF/container.xml", "OEBPS/content.opf", "OEBPS/nav.xhtml", "OEBPS/cap-001.xhtml"} <= nomes
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        capitulo = zf.read("OEBPS/cap-001.xhtml").decode("utf-8")
    assert "<dc:title>Tom &amp; Jerry &lt;teste&gt;</dc:title>" in opf
    assert "a &lt; b &amp; c" in capitulo
    assert '<itemref idref="cap1"/>' in opf


def test_epub_ignora_capitulos_vazios_e_recusa_livro_sem_texto(tmp_path: Path) -> None:
    livro = Livro("T", capitulos=[Capitulo("Vazio", [])])
    with pytest.raises(ErroConversao):
        gerar_epub(livro, tmp_path / "x.epub")
