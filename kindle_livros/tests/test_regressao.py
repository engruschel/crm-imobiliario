"""Testes de regressão para os problemas apontados na revisão (itens 1 a 17). Todos offline."""

import http.client
import io
import json
import sys
import types
import urllib.error
import zipfile
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

import pytest

from kindle_livros import cli
from kindle_livros.busca import baixar, buscar_gutenberg, buscar_internet_archive
from kindle_livros.conversor import _converter_com_calibre, ler_epub, ler_pdf
from kindle_livros.epub import gerar_epub
from kindle_livros.erros import ErroBusca, ErroConversao, KindleLivrosError, KindleNaoEncontrado
from kindle_livros.kindle_usb import enviar_para_kindle
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.tradutor import TradutorComCache, Tradutor
from kindle_livros.transcricao import legendas_youtube, parse_vtt

CONTAINER = (
    '<?xml version="1.0"?><container version="1.0" '
    'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
    '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
    "</rootfiles></container>"
)


def _epub_manual(caminho: Path, href: str, xhtml: str, arquivo_interno: str) -> Path:
    """Monta um EPUB mínimo com um capítulo cujo href do manifesto pode conter codificação de URL."""
    opf = (
        '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>'
        "<dc:language>pt</dc:language></metadata>"
        f'<manifest><item id="c1" href="{href}" media-type="application/xhtml+xml"/></manifest>'
        '<spine><itemref idref="c1"/></spine></package>'
    )
    with zipfile.ZipFile(caminho, "w") as zf:
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr(f"OEBPS/{arquivo_interno}", xhtml)
    return caminho


def _xhtml(corpo: str) -> str:
    return f'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><body>{corpo}</body></html>'


# Item 1: a saída nunca pode ser o arquivo de entrada
def test_converter_recusa_sobrescrever_o_proprio_arquivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    entrada = gerar_epub(Livro("Livro", capitulos=[Capitulo("c", ["texto original"])]), tmp_path / "Livro.epub")
    conteudo_original = entrada.read_bytes()
    assert cli.main(["converter", "Livro.epub"]) == 1  # saída padrão seria Livro.epub, igual à entrada
    assert "entrada" in capsys.readouterr().err
    assert entrada.read_bytes() == conteudo_original
    assert cli.main(["converter", "Livro.epub", "-s", "./Livro.epub"]) == 1
    assert entrada.read_bytes() == conteudo_original


def test_pipeline_recusa_saida_igual_a_origem_local(tmp_path: Path) -> None:
    from kindle_livros.conversor import garantir_saida_distinta

    origem = tmp_path / "Obra.epub"
    origem.write_bytes(b"x")
    with pytest.raises(ErroConversao):
        garantir_saida_distinta(str(origem), tmp_path / "Obra.epub")
    garantir_saida_distinta(str(origem), tmp_path / "outra" / "Obra.epub")  # caminhos diferentes são aceitos


# Item 2: hrefs do manifesto são URLs (codificadas)
def test_epub_com_href_codificado_por_url(tmp_path: Path) -> None:
    epub = _epub_manual(tmp_path / "a.epub", "cap%201.xhtml", _xhtml("<p>conteúdo</p>"), "cap 1.xhtml")
    livro = ler_epub(epub)
    assert livro.capitulos[0].paragrafos == ["conteúdo"]


# Item 3: caracteres de controle proibidos pelo XML são removidos
def test_epub_remove_caracteres_de_controle(tmp_path: Path) -> None:
    livro = Livro("Título\x01 ruim", capitulos=[Capitulo("Cap\x0b", ["texto\x00 com\x1f controle"])])
    epub = gerar_epub(livro, tmp_path / "c.epub")
    with zipfile.ZipFile(epub) as zf:
        for nome in ("OEBPS/content.opf", "OEBPS/cap-001.xhtml"):
            raiz = ET.fromstring(zf.read(nome))  # falharia com caracteres de controle
            assert not any(ord(c) < 32 and c not in "\t\n\r" for c in "".join(raiz.itertext()))


# Item 4: <br/> vira espaço e texto solto depois de um bloco filho não é descartado
def test_xhtml_br_vira_espaco_e_texto_apos_filho_nao_se_perde(tmp_path: Path) -> None:
    epub = _epub_manual(tmp_path / "b.epub", "c.xhtml",
                        _xhtml("<div>Antes <p>filho</p> depois<br/>linha</div><p>a<br/>b</p>"), "c.xhtml")
    paragrafos = ler_epub(epub).capitulos[0].paragrafos
    assert paragrafos == ["Antes", "filho", "depois linha", "a b"]


# Item 5: erros do pypdf viram erro de domínio
def test_pdf_corrompido_vira_erro_de_conversao(tmp_path: Path) -> None:
    arquivo = tmp_path / "ruim.pdf"
    arquivo.write_bytes(b"isto nao e um pdf")
    with pytest.raises(ErroConversao, match="PDF"):
        ler_pdf(arquivo)


# Item 6: falha de cópia vira KindleLivrosError e não deixa temporário
def test_falha_na_copia_vira_erro_de_dominio_e_limpa_temporario(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kindle = tmp_path / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    livro = tmp_path / "novo.epub"
    livro.write_bytes(b"novo")
    (kindle / "documents" / "novo.epub").write_bytes(b"antigo")

    def falhar(origem: object, destino: object) -> None:
        Path(str(destino)).write_bytes(b"parcial")
        raise OSError("disco removido")

    monkeypatch.setattr("kindle_livros.kindle_usb.shutil.copyfile", falhar)
    with pytest.raises(KindleLivrosError, match="Falha ao copiar"):
        enviar_para_kindle([livro], kindle, forcar=True)
    assert (kindle / "documents" / "novo.epub").read_bytes() == b"antigo"
    assert not list((kindle / "documents").glob(".kindle_livros-*"))


# Item 7: não apagar arquivo pré-existente ao falhar o download
def test_download_falho_nao_apaga_arquivo_existente(tmp_path: Path) -> None:
    (tmp_path / "obra.epub").write_bytes(b"antigo")
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
        with pytest.raises(ErroBusca):
            baixar("https://exemplo.org/obra.epub", tmp_path, "obra.epub")
    assert (tmp_path / "obra.epub").read_bytes() == b"antigo"
    assert not list(tmp_path.glob(".kindle_livros-*"))


def test_download_bem_sucedido_substitui_pelo_novo(tmp_path: Path) -> None:
    (tmp_path / "obra.epub").write_bytes(b"antigo")
    resposta = io.BytesIO(b"novo conteudo")
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", return_value=resposta):
        destino = baixar("https://exemplo.org/obra.epub", tmp_path, "obra.epub")
    assert destino.read_bytes() == b"novo conteudo"


# Item 8: http.client.HTTPException vira ErroBusca (e leitura interrompida também)
def test_http_exception_vira_erro_de_busca() -> None:
    with mock.patch("kindle_livros.busca.urllib.request.urlopen",
                    side_effect=http.client.RemoteDisconnected("fechou")):
        with pytest.raises(ErroBusca):
            buscar_gutenberg("x")


class _RespostaInterrompida:
    def __enter__(self) -> "_RespostaInterrompida":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, _tamanho: int = -1) -> bytes:
        raise http.client.IncompleteRead(b"parcial")


def test_leitura_interrompida_no_download_vira_erro_de_busca(tmp_path: Path) -> None:
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", return_value=_RespostaInterrompida()):
        with pytest.raises(ErroBusca):
            baixar("https://exemplo.org/a.epub", tmp_path, "a.epub")
    assert not list(tmp_path.glob(".kindle_livros-*"))


# Item 9: falha do yt-dlp vira ErroConversao em português
def test_falha_do_yt_dlp_vira_erro_de_conversao(monkeypatch: pytest.MonkeyPatch) -> None:
    class DownloadError(Exception):
        pass

    utils = types.ModuleType("yt_dlp.utils")
    utils.DownloadError = DownloadError  # type: ignore[attr-defined]

    class YoutubeDL:
        def __init__(self, _opcoes: dict) -> None:
            pass

        def __enter__(self) -> "YoutubeDL":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def extract_info(self, _url: str, download: bool) -> dict:
            raise DownloadError("vídeo privado")

    modulo = types.ModuleType("yt_dlp")
    modulo.YoutubeDL = YoutubeDL  # type: ignore[attr-defined]
    modulo.utils = utils  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "yt_dlp", modulo)
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", utils)
    with pytest.raises(ErroConversao, match="legendas"):
        legendas_youtube("https://youtu.be/abc", "en")


# Item 10: deduplicação progressiva de legendas automáticas
def test_vtt_deduplica_progressivamente() -> None:
    vtt = "WEBVTT\n\n00:00.000 --> 00:01.000\nolá\n\n00:01.000 --> 00:02.000\nolá mundo\n\n00:02.000 --> 00:03.000\nolá mundo tudo\n"
    assert parse_vtt(vtt) == ["olá mundo tudo"]


def test_vtt_descarta_linha_que_e_prefixo_da_anterior() -> None:
    vtt = "x y z\nx y\n"
    assert parse_vtt(vtt) == ["x y z"]


# Itens 11 e 12: atributos escapados e cache validado/atômico
def test_atributo_com_aspas_no_idioma_continua_xml_valido(tmp_path: Path) -> None:
    epub = gerar_epub(Livro("T", idioma='pt"x', capitulos=[Capitulo("c", ["t"])]), tmp_path / "q.epub")
    with zipfile.ZipFile(epub) as zf:
        ET.fromstring(zf.read("OEBPS/content.opf"))
        ET.fromstring(zf.read("OEBPS/cap-001.xhtml"))


def test_cache_corrompido_ou_com_formato_errado_e_ignorado(tmp_path: Path) -> None:
    arquivo = tmp_path / "cache.json"
    arquivo.write_text(json.dumps(["lista", "e nao dict"]), encoding="utf-8")

    class Base(Tradutor):
        def traduzir(self, textos: list[str], destino: str) -> list[str]:
            return [f"T:{t}" for t in textos]

    assert TradutorComCache(Base(), arquivo).traduzir(["a"], "pt") == ["T:a"]
    arquivo.write_text("{quebrado", encoding="utf-8")
    assert TradutorComCache(Base(), arquivo).traduzir(["b"], "pt") == ["T:b"]


# Item 13: origem igual ao destino vira mensagem amigável (já está no Kindle)
def test_enviar_arquivo_que_ja_esta_no_kindle_nao_falha(tmp_path: Path) -> None:
    kindle = tmp_path / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    no_kindle = kindle / "documents" / "livro.epub"
    no_kindle.write_bytes(b"x")
    resultado = enviar_para_kindle([no_kindle], kindle, forcar=True)
    assert resultado.copiados == []
    assert resultado.ignorados == [no_kindle]


# Item 14: falha nos metadados de um item do Internet Archive não aborta a fonte
def test_internet_archive_pula_item_com_falha_de_metadados() -> None:
    busca_dados = {"response": {"docs": [{"identifier": "ruim"}, {"identifier": "bom", "title": "Ok"}]}}
    metadados_bom = {"files": [{"name": "ok.epub"}]}

    def fake_urlopen(requisicao: object, timeout: float) -> io.BytesIO:
        url = getattr(requisicao, "full_url", str(requisicao))
        if "/metadata/ruim" in url:
            raise urllib.error.URLError("falhou")
        if "/metadata/bom" in url:
            return io.BytesIO(json.dumps(metadados_bom).encode())
        return io.BytesIO(json.dumps(busca_dados).encode())

    with mock.patch("kindle_livros.busca.urllib.request.urlopen", side_effect=fake_urlopen):
        resultados = buscar_internet_archive("x")
    assert [r.titulo for r in resultados] == ["Ok"]


# Item 15: falha durante a geração não deixa EPUB parcial nem substitui o anterior
def test_falha_na_geracao_preserva_epub_anterior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destino = tmp_path / "l.epub"
    destino.write_bytes(b"anterior")
    livro = Livro("T", capitulos=[Capitulo("c", ["t"])])

    def falhar(*args: object, **kwargs: object) -> None:
        raise OSError("sem espaço")

    monkeypatch.setattr("kindle_livros.epub.zipfile.ZipFile.writestr", falhar)
    with pytest.raises(OSError):
        gerar_epub(livro, destino)
    assert destino.read_bytes() == b"anterior"
    assert not list(tmp_path.glob(".kindle_livros-*"))


# Item 16: Calibre com timeout
def test_calibre_com_timeout_vira_erro_de_conversao(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setattr("kindle_livros.conversor.shutil.which", lambda _n: "/usr/bin/ebook-convert")

    def expirar(*args: object, **kwargs: object) -> None:
        assert kwargs.get("timeout") is not None
        raise subprocess.TimeoutExpired(cmd="ebook-convert", timeout=1)

    monkeypatch.setattr("kindle_livros.conversor.subprocess.run", expirar)
    with pytest.raises(ErroConversao, match="excedeu"):
        _converter_com_calibre(tmp_path / "a.epub", tmp_path / "a.mobi")


# Item 17: destino que não parece Kindle exige confirmação explícita
def test_destino_que_nao_parece_kindle_exige_confirmacao(tmp_path: Path) -> None:
    pasta_comum = tmp_path / "pasta_qualquer"
    pasta_comum.mkdir()
    livro = tmp_path / "x.epub"
    livro.write_bytes(b"x")
    with pytest.raises(KindleNaoEncontrado, match="confirmar-destino"):
        enviar_para_kindle([livro], pasta_comum)
    resultado = enviar_para_kindle([livro], pasta_comum, confirmar_destino=True)
    assert resultado.copiados == [pasta_comum / "documents" / "x.epub"]


def test_cli_enviar_aceita_confirmar_destino(tmp_path: Path) -> None:
    pasta_comum = tmp_path / "pasta"
    pasta_comum.mkdir()
    livro = tmp_path / "x.epub"
    livro.write_bytes(b"x")
    assert cli.main(["enviar", str(livro), "--destino", str(pasta_comum)]) == 1
    assert cli.main(["enviar", str(livro), "--destino", str(pasta_comum), "--confirmar-destino"]) == 0


# Risco informativo: busca local não devolve cópias que já estão dentro de um Kindle
def test_busca_local_ignora_arquivos_dentro_de_kindle(tmp_path: Path) -> None:
    from kindle_livros.busca import buscar_local

    (tmp_path / "Obra.epub").write_bytes(b"x")
    kindle = tmp_path / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    (kindle / "documents" / "Obra.epub").write_bytes(b"x")
    resultados = buscar_local(tmp_path, "obra")
    assert len(resultados) == 1
    assert resultados[0].links == {"epub": str(tmp_path / "Obra.epub")}


# Rodada 2, N1: ordem do documento e separação de palavras no extrator XHTML
@pytest.mark.parametrize("entrada, esperado", [
    ("<div>Antes <p>filho</p> depois</div>", ["Antes", "filho", "depois"]),
    ("<div>Texto um<h2>Sub</h2>Texto dois</div>", ["Texto um", "Texto dois"]),
    ("<body>Titulo solto<p>A</p>Fim</body>", ["Titulo solto", "A", "Fim"]),
    ("<p>a<p>b<p>c</body>", ["a", "b", "c"]),
])
def test_extrator_xhtml_mantem_ordem_e_separa_palavras(entrada: str, esperado: list[str]) -> None:
    from kindle_livros.conversor import _ExtratorXhtml

    extrator = _ExtratorXhtml()
    extrator.feed(entrada)
    extrator.close()
    assert extrator.paragrafos == esperado


def test_extrator_xhtml_usa_primeiro_cabecalho_como_titulo() -> None:
    from kindle_livros.conversor import _ExtratorXhtml

    extrator = _ExtratorXhtml()
    extrator.feed("<div>Texto um<h2>Sub</h2>Texto dois</div>")
    extrator.close()
    assert extrator.titulo == "Sub"


# Rodada 2, N2: a própria pasta pesquisada nunca oculta os livros que contém
def test_busca_local_nao_oculta_livros_quando_a_biblioteca_tem_documents(tmp_path: Path) -> None:
    from kindle_livros.busca import buscar_local

    biblioteca = tmp_path / "Biblioteca"
    (biblioteca / "documents").mkdir(parents=True)
    (biblioteca / "Dom Casmurro.epub").write_bytes(b"x")
    assert [r.titulo for r in buscar_local(biblioteca, "dom")] == ["Dom Casmurro"]


def test_busca_local_nao_oculta_livros_quando_a_biblioteca_tem_documents_e_system(tmp_path: Path) -> None:
    from kindle_livros.busca import buscar_local

    biblioteca = tmp_path / "Biblioteca"
    (biblioteca / "documents").mkdir(parents=True)
    (biblioteca / "system").mkdir()
    (biblioteca / "Dom Casmurro.epub").write_bytes(b"x")
    assert [r.titulo for r in buscar_local(biblioteca, "dom")] == ["Dom Casmurro"]


# Rodada 2, N3: assinatura de Kindle exige documents/ e system/ juntos
def test_pasta_so_com_documents_nao_e_aceita_como_destino(tmp_path: Path) -> None:
    pasta = tmp_path / "Quase"
    (pasta / "documents").mkdir(parents=True)
    livro = tmp_path / "x.epub"
    livro.write_bytes(b"x")
    with pytest.raises(KindleNaoEncontrado, match="confirmar-destino"):
        enviar_para_kindle([livro], pasta)
    assert not (pasta / "documents" / "x.epub").exists()


# Rodada 2, N4: restos de cópias interrompidas pelo próprio programa são removidos antes de copiar
def test_remove_temporarios_do_programa_antes_de_copiar(tmp_path: Path) -> None:
    kindle = tmp_path / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    sobra = kindle / "documents" / ".kindle_livros-0123abcd.tmp"
    sobra.write_bytes(b"lixo")
    livro = tmp_path / "novo.epub"
    livro.write_bytes(b"x")
    enviar_para_kindle([livro], kindle)
    assert not sobra.exists()
    assert (kindle / "documents" / "novo.epub").is_file()


# N7: arquivos do próprio usuário em documents/ nunca são apagados, mesmo com nome parecido
def test_parcial_do_usuario_em_documents_sobrevive_ao_envio(tmp_path: Path) -> None:
    kindle = tmp_path / "Kindle"
    (kindle / "documents").mkdir(parents=True)
    (kindle / "system").mkdir()
    do_usuario = kindle / "documents" / "meu.parcial"
    do_usuario.write_bytes(b"anotacoes do usuario")
    do_usuario_tmp = kindle / "documents" / "outro.tmp"
    do_usuario_tmp.write_bytes(b"outro")
    livro = tmp_path / "novo.epub"
    livro.write_bytes(b"x")
    enviar_para_kindle([livro], kindle)
    assert do_usuario.read_bytes() == b"anotacoes do usuario"
    assert do_usuario_tmp.read_bytes() == b"outro"


# N8: o temporário do programa não pode sobrescrever um arquivo do usuário com nome ".parcial"
def test_epub_gerado_nao_toca_parcial_do_usuario(tmp_path: Path) -> None:
    do_usuario = tmp_path / "x.epub.parcial"
    do_usuario.write_bytes(b"do usuario")
    gerar_epub(Livro("T", capitulos=[Capitulo("c", ["t"])]), tmp_path / "x.epub")
    assert do_usuario.read_bytes() == b"do usuario"
    assert (tmp_path / "x.epub").is_file()


def test_download_nao_toca_parcial_do_usuario(tmp_path: Path) -> None:
    do_usuario = tmp_path / "x.epub.parcial"
    do_usuario.write_bytes(b"do usuario")
    with mock.patch("kindle_livros.busca.urllib.request.urlopen", return_value=io.BytesIO(b"novo")):
        baixar("https://exemplo.org/x.epub", tmp_path, "x.epub")
    assert do_usuario.read_bytes() == b"do usuario"


def test_cache_nao_toca_parcial_do_usuario(tmp_path: Path) -> None:
    do_usuario = tmp_path / "cache.json.parcial"
    do_usuario.write_bytes(b"do usuario")

    class Base(Tradutor):
        def traduzir(self, textos: list[str], destino: str) -> list[str]:
            return [f"T:{t}" for t in textos]

    TradutorComCache(Base(), tmp_path / "cache.json").traduzir(["a"], "pt")
    assert do_usuario.read_bytes() == b"do usuario"
    assert (tmp_path / "cache.json").is_file()


def test_temporarios_do_programa_sao_exclusivos() -> None:
    from kindle_livros.temporarios import caminho_temporario

    alvo = Path("/x/y/livro.epub")
    primeiro, segundo = caminho_temporario(alvo), caminho_temporario(alvo)
    assert primeiro != segundo
    assert primeiro.parent == alvo.parent
    assert primeiro.name.startswith(".kindle_livros-") and primeiro.name.endswith(".tmp")


# Rodada 2, N5: a guarda de saída roda antes da tradução
def test_traduzir_recusa_saida_igual_antes_de_traduzir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    entrada = gerar_epub(Livro("Obra", capitulos=[Capitulo("c", ["texto"])]), tmp_path / "Obra.epub")
    original = entrada.read_bytes()

    def nao_deve_traduzir(*args: object, **kwargs: object) -> None:
        raise AssertionError("a tradução não deveria ser chamada")

    monkeypatch.setattr("kindle_livros.cli.traduzir_livro", nao_deve_traduzir)
    assert cli.main(["traduzir", str(entrada), "--idioma", "en", "-s", str(entrada)]) == 1
    assert "próprio arquivo" in capsys.readouterr().err
    assert entrada.read_bytes() == original


def test_pipeline_recusa_saida_igual_antes_de_traduzir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    biblioteca = tmp_path / "biblioteca"
    biblioteca.mkdir()
    gerar_epub(Livro("Obra", capitulos=[Capitulo("c", ["texto"])]), biblioteca / "Obra.epub")

    def nao_deve_traduzir(*args: object, **kwargs: object) -> None:
        raise AssertionError("a tradução não deveria ser chamada")

    monkeypatch.setattr("kindle_livros.cli.traduzir_livro", nao_deve_traduzir)
    rc = cli.main(["pipeline", "Obra", "--fonte", "local", "--pasta-local", str(biblioteca),
                   "--saida", str(biblioteca), "--idioma", "en"])
    assert rc == 1
    assert "próprio arquivo" in capsys.readouterr().err


# Rodada 2, I10: sobreposição no meio da legenda não duplica texto
def test_vtt_sobreposicao_no_meio_nao_duplica_texto() -> None:
    vtt = (
        "WEBVTT\n\n"
        "00:00.000 --> 00:01.000\nola a todos\n\n"
        "00:01.000 --> 00:02.000\nola a todos bem vindos\n\n"
        "00:02.000 --> 00:03.000\nbem vindos ao curso\n"
    )
    assert parse_vtt(vtt) == ["ola a todos bem vindos ao curso"]
