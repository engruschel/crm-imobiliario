from pathlib import Path
from unittest import mock

import pytest

from kindle_livros import cli
from kindle_livros.erros import KindleNaoEncontrado


def test_parser_tem_todos_os_subcomandos() -> None:
    parser = cli.construir_parser()
    subcomandos = parser._subparsers._group_actions[0].choices  # type: ignore[attr-defined]
    assert set(subcomandos) == {"detectar", "buscar", "converter", "traduzir", "enviar", "pipeline"}


def test_detectar_sem_kindle_informa_em_portugues(capsys: pytest.CaptureFixture[str]) -> None:
    with mock.patch("kindle_livros.cli.detectar_kindles", return_value=[]):
        assert cli.main(["detectar"]) == 0
    assert "Nenhum Kindle encontrado" in capsys.readouterr().out


def test_enviar_sem_kindle_e_sem_destino_retorna_erro(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    arquivo = tmp_path / "x.epub"
    arquivo.write_bytes(b"x")
    with mock.patch("kindle_livros.cli.detectar_kindles", return_value=[]):
        assert cli.main(["enviar", str(arquivo)]) == 1
    assert "Nenhum Kindle" in capsys.readouterr().err


def test_enviar_usa_destino_informado(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.epub"
    arquivo.write_bytes(b"x")
    destino = tmp_path / "kindle"
    (destino / "documents").mkdir(parents=True)
    (destino / "system").mkdir()
    assert cli.main(["enviar", str(arquivo), "--destino", str(destino)]) == 0
    assert (destino / "documents" / "x.epub").is_file()


def test_enviar_sem_kindle_levanta_erro_de_dominio(tmp_path: Path) -> None:
    with pytest.raises(KindleNaoEncontrado):
        cli._enviar([tmp_path / "x.epub"], None, False)
