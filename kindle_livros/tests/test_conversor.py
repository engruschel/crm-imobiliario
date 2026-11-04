from pathlib import Path

import pytest

from kindle_livros.conversor import carregar_livro, ler_epub, ler_txt, salvar_livro
from kindle_livros.epub import gerar_epub
from kindle_livros.erros import ErroConversao, FormatoNaoSuportado
from kindle_livros.modelo import Capitulo, Livro, dividir_em_capitulos


def test_txt_separa_capitulos_por_cabecalho(tmp_path: Path) -> None:
    arquivo = tmp_path / "obra.txt"
    arquivo.write_text(
        "Prólogo curto.\n\nCapítulo I\n\nPrimeira\nlinha do texto.\n\nCHAPTER II\n\nSegundo.",
        encoding="utf-8",
    )
    livro = ler_txt(arquivo)
    assert livro.titulo == "obra"
    assert [c.titulo for c in livro.capitulos] == ["obra", "Capítulo I", "CHAPTER II"]
    assert livro.capitulos[1].paragrafos == ["Primeira linha do texto."]


def test_epub_roundtrip_preserva_titulos_e_paragrafos(tmp_path: Path) -> None:
    original = Livro("Livro Teste", "Fulano", "pt", [
        Capitulo("Cap A", ["Primeiro parágrafo.", "Segundo & último."]),
        Capitulo("Cap B", ["Outro texto."]),
    ])
    epub = gerar_epub(original, tmp_path / "t.epub")
    lido = ler_epub(epub)
    assert lido.titulo == "Livro Teste"
    assert lido.autor == "Fulano"
    assert [c.titulo for c in lido.capitulos] == ["Cap A", "Cap B"]
    assert lido.capitulos[0].paragrafos == ["Primeiro parágrafo.", "Segundo & último."]


def test_dividir_em_capitulos_agrupa_unidades() -> None:
    capitulos = dividir_em_capitulos([["p1"], ["p2"], ["p3"]], 2)
    assert [c.titulo for c in capitulos] == ["Parte 1", "Parte 2"]
    assert capitulos[0].paragrafos == ["p1", "p2"]


def test_formato_de_entrada_desconhecido_e_erro_claro(tmp_path: Path) -> None:
    arquivo = tmp_path / "imagem.png"
    arquivo.write_bytes(b"x")
    with pytest.raises(FormatoNaoSuportado):
        carregar_livro(str(arquivo))


def test_arquivo_inexistente_gera_erro(tmp_path: Path) -> None:
    with pytest.raises(ErroConversao):
        carregar_livro(str(tmp_path / "nao_existe.txt"))


def test_saida_mobi_sem_calibre_avisa_dependencia(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from kindle_livros.erros import DependenciaAusente

    monkeypatch.setattr("kindle_livros.conversor.shutil.which", lambda _nome: None)
    with pytest.raises(DependenciaAusente, match="Calibre"):
        salvar_livro(Livro("T", capitulos=[Capitulo("c", ["x"])]), tmp_path / "x.mobi")
