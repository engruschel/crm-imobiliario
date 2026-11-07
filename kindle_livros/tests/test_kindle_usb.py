from pathlib import Path
from types import SimpleNamespace

import pytest

from kindle_livros import kindle_usb
from kindle_livros.erros import EspacoInsuficiente, FormatoNaoSuportado, KindleNaoEncontrado
from kindle_livros.kindle_usb import detectar_kindles, enviar_para_kindle


def _kindle_falso(base: Path) -> Path:
    kindle = base / "media" / "usuario" / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    return kindle


def test_detecta_kindle_por_padrao_de_montagem(tmp_path: Path) -> None:
    kindle = _kindle_falso(tmp_path)
    (tmp_path / "media" / "usuario" / "PenDrive").mkdir()
    padroes = [str(tmp_path / "media" / "*" / "Kindle")]
    assert detectar_kindles(plataforma="linux", padroes=padroes) == [kindle]


def test_nao_detecta_pasta_que_nao_parece_kindle(tmp_path: Path) -> None:
    (tmp_path / "media" / "u" / "Kindle").mkdir(parents=True)
    assert detectar_kindles(plataforma="linux", padroes=[str(tmp_path / "media" / "*" / "Kindle")]) == []


def test_copia_arquivos_e_nao_sobrescreve_sem_forcar(tmp_path: Path) -> None:
    kindle = _kindle_falso(tmp_path)
    livro = tmp_path / "a.epub"
    livro.write_bytes(b"novo")
    (kindle / "documents" / "a.epub").write_bytes(b"antigo")

    resultado = enviar_para_kindle([livro], kindle)
    assert resultado.copiados == []
    assert resultado.ignorados == [kindle / "documents" / "a.epub"]
    assert (kindle / "documents" / "a.epub").read_bytes() == b"antigo"

    resultado = enviar_para_kindle([livro], kindle, forcar=True)
    assert resultado.copiados == [kindle / "documents" / "a.epub"]
    assert (kindle / "documents" / "a.epub").read_bytes() == b"novo"


def test_aceita_pasta_documents_como_destino(tmp_path: Path) -> None:
    kindle = _kindle_falso(tmp_path)
    livro = tmp_path / "b.pdf"
    livro.write_bytes(b"%PDF")
    resultado = enviar_para_kindle([livro], kindle / "documents")
    assert resultado.pasta_documentos == kindle / "documents"
    assert (kindle / "documents" / "b.pdf").is_file()


def test_recusa_formato_nao_aceito_antes_de_copiar(tmp_path: Path) -> None:
    kindle = _kindle_falso(tmp_path)
    arquivo = tmp_path / "foto.jpg"
    arquivo.write_bytes(b"x")
    with pytest.raises(FormatoNaoSuportado):
        enviar_para_kindle([arquivo], kindle)
    assert list((kindle / "documents").iterdir()) == []


def test_verifica_espaco_livre_antes_de_copiar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kindle = _kindle_falso(tmp_path)
    livro = tmp_path / "grande.epub"
    livro.write_bytes(b"x" * 100)
    monkeypatch.setattr(kindle_usb.shutil, "disk_usage", lambda _p: SimpleNamespace(free=0))
    with pytest.raises(EspacoInsuficiente):
        enviar_para_kindle([livro], kindle)
    assert not (kindle / "documents" / "grande.epub").exists()


def test_destino_inexistente_gera_erro(tmp_path: Path) -> None:
    livro = tmp_path / "c.txt"
    livro.write_text("oi", encoding="utf-8")
    with pytest.raises(KindleNaoEncontrado):
        enviar_para_kindle([livro], tmp_path / "nao_existe")


def test_detecta_kindle_com_nome_de_volume_diferente(tmp_path):
    from kindle_livros.kindle_usb import detectar_kindles, padroes_de_montagem

    volume = tmp_path / "Kindle Paperwhite"
    (volume / "documents").mkdir(parents=True)
    (volume / "system").mkdir()
    (tmp_path / "Outro disco").mkdir()  # sem assinatura de Kindle: deve ser ignorado
    assert detectar_kindles("darwin", padroes=[str(tmp_path / "*")]) == [volume]
    assert padroes_de_montagem("darwin") == ("/Volumes/*",)
