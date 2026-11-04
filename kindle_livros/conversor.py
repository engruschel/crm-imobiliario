"""Leitura de PDF, TXT, EPUB, áudio e YouTube para o modelo Livro, e gravação em formato Kindle."""

import posixpath
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from kindle_livros.config import (
    EXTENSOES_AUDIO,
    PAGINAS_POR_CAPITULO,
    PARAGRAFOS_POR_CAPITULO,
)
from kindle_livros.epub import gerar_epub
from kindle_livros.erros import DependenciaAusente, ErroConversao, FormatoNaoSuportado
from kindle_livros.modelo import Capitulo, Livro, dividir_em_capitulos

REGEX_CAPITULO = re.compile(r"^(cap[ií]tulo|chapter)\b", re.IGNORECASE)
NS_CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"
NS_OPF = "{http://www.idpf.org/2007/opf}"
NS_DC = "{http://purl.org/dc/elements/1.1/}"
BLOCOS_XHTML = frozenset({"p", "li", "blockquote", "div", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "dt", "dd"})
CABECALHOS_XHTML = frozenset({"h1", "h2", "h3"})
IGNORADAS_XHTML = frozenset({"script", "style", "head", "title"})
TIMEOUT_CALIBRE = 600


def carregar_livro(entrada: str, idioma_origem: str = "pt", paginas_por_capitulo: int = PAGINAS_POR_CAPITULO) -> Livro:
    """Lê um arquivo local (PDF, TXT, EPUB, áudio) ou uma URL do YouTube.

    Para EPUB, o idioma declarado nos metadados do próprio arquivo tem precedência sobre `idioma_origem`.
    """
    if entrada.startswith(("http://", "https://")):
        return _carregar_youtube(entrada, idioma_origem)
    caminho = Path(entrada)
    if not caminho.is_file():
        raise ErroConversao(f"Arquivo não encontrado: {caminho}")
    sufixo = caminho.suffix.lower()
    if sufixo == ".txt":
        return ler_txt(caminho, idioma_origem)
    if sufixo == ".pdf":
        return ler_pdf(caminho, idioma_origem, paginas_por_capitulo)
    if sufixo == ".epub":
        return ler_epub(caminho, idioma_origem)
    if sufixo in EXTENSOES_AUDIO:
        return _carregar_audio(caminho, idioma_origem)
    raise FormatoNaoSuportado(f"Formato de entrada não suportado: '{sufixo or 'sem extensão'}'.")


def garantir_saida_distinta(entrada: str, saida: Path) -> None:
    """Recusa gravar a saída sobre o próprio arquivo de entrada."""
    if entrada.startswith(("http://", "https://")):
        return
    if Path(entrada).resolve() == saida.resolve():
        raise ErroConversao(
            f"A saída seria o próprio arquivo de entrada ({saida.name}). Informe outro caminho com -s/--saida."
        )


def salvar_livro(livro: Livro, saida: Path) -> Path:
    """Grava o livro como EPUB, ou como MOBI/AZW3 se o Calibre (ebook-convert) estiver instalado."""
    sufixo = saida.suffix.lower()
    if sufixo == ".epub":
        return gerar_epub(livro, saida)
    if sufixo in {".mobi", ".azw3"}:
        with tempfile.TemporaryDirectory() as tmp:
            epub = gerar_epub(livro, Path(tmp) / "livro.epub")
            return _converter_com_calibre(epub, saida)
    raise FormatoNaoSuportado(f"Formato de saída não suportado: '{sufixo}'. Use .epub, .mobi ou .azw3.")


def _converter_com_calibre(epub: Path, saida: Path) -> Path:
    executavel = shutil.which("ebook-convert")
    if executavel is None:
        raise DependenciaAusente("Para gerar MOBI/AZW3 é preciso instalar o Calibre (comando 'ebook-convert').")
    saida.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([executavel, str(epub), str(saida)], check=True, capture_output=True,
                       text=True, timeout=TIMEOUT_CALIBRE)
    except subprocess.CalledProcessError as exc:
        raise ErroConversao(f"O Calibre falhou ao converter o livro: {exc.stderr.strip()[-300:]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ErroConversao(f"O Calibre excedeu {TIMEOUT_CALIBRE} s ao converter o livro.") from exc
    return saida


def ler_txt(caminho: Path, idioma: str = "pt") -> Livro:
    paragrafos = _paragrafos(_ler_texto(caminho))
    return Livro(titulo=caminho.stem, idioma=idioma, capitulos=_capitulos_txt(paragrafos, caminho.stem))


def ler_pdf(caminho: Path, idioma: str = "pt", paginas_por_capitulo: int = PAGINAS_POR_CAPITULO) -> Livro:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise DependenciaAusente("Para ler PDF instale: pip install pypdf") from exc
    try:
        leitor = PdfReader(str(caminho))
        paginas = [_paragrafos(pagina.extract_text() or "") for pagina in leitor.pages]
        meta = leitor.metadata
        titulo_meta = meta.title if meta else None
    except Exception as exc:  # pypdf levanta exceções variadas para PDFs corrompidos ou criptografados
        raise ErroConversao(f"Não foi possível ler o PDF {caminho.name}: {exc}") from exc
    if not any(paginas):
        raise ErroConversao("O PDF não tem texto extraível (pode ser digitalizado; OCR não é suportado).")
    return Livro(titulo_meta or caminho.stem, idioma=idioma,
                 capitulos=dividir_em_capitulos(paginas, paginas_por_capitulo))


def ler_epub(caminho: Path, idioma: str = "pt") -> Livro:
    try:
        with zipfile.ZipFile(caminho) as zf:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(f".//{NS_CONTAINER}rootfile")
            if rootfile is None or not rootfile.get("full-path"):
                raise ErroConversao("EPUB inválido: container.xml sem rootfile.")
            opf_path = rootfile.get("full-path")
            opf = ET.fromstring(zf.read(opf_path))
            base = posixpath.dirname(opf_path)
            manifesto = {item.get("id"): item.get("href") for item in opf.iter(f"{NS_OPF}item")}
            ordem = [manifesto[ref.get("idref")] for ref in opf.iter(f"{NS_OPF}itemref")
                     if ref.get("idref") in manifesto]
            capitulos = []
            for href in ordem:
                # Hrefs do manifesto são URLs relativas: "cap%201.xhtml" corresponde ao arquivo "cap 1.xhtml".
                caminho_interno = posixpath.normpath(posixpath.join(base, urllib.parse.unquote(href)))
                html = zf.read(caminho_interno).decode("utf-8", errors="replace")
                extrator = _ExtratorXhtml()
                extrator.feed(html)
                extrator.close()
                if extrator.paragrafos:
                    titulo = extrator.titulo or f"Capítulo {len(capitulos) + 1}"
                    capitulos.append(Capitulo(titulo, extrator.paragrafos))
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ErroConversao(f"EPUB inválido ou incompleto: {caminho.name}") from exc
    titulo = _texto_metadado(opf, "title") or caminho.stem
    autor = _texto_metadado(opf, "creator") or "Desconhecido"
    return Livro(titulo, autor, _texto_metadado(opf, "language") or idioma, capitulos)


def _texto_metadado(opf: ET.Element, nome: str) -> str | None:
    elemento = opf.find(f".//{NS_DC}{nome}")
    if elemento is None or not elemento.text:
        return None
    return elemento.text.strip() or None


def _carregar_audio(caminho: Path, idioma: str) -> Livro:
    from kindle_livros.transcricao import transcrever_audio

    paragrafos = transcrever_audio(caminho, idioma)
    unidades = [[p] for p in paragrafos]
    return Livro(caminho.stem, idioma=idioma, capitulos=dividir_em_capitulos(unidades, PARAGRAFOS_POR_CAPITULO))


def _carregar_youtube(url: str, idioma: str) -> Livro:
    from kindle_livros.transcricao import legendas_youtube

    titulo, autor, paragrafos = legendas_youtube(url, idioma)
    unidades = [[p] for p in paragrafos]
    return Livro(titulo, autor, idioma, dividir_em_capitulos(unidades, PARAGRAFOS_POR_CAPITULO))


def _ler_texto(caminho: Path) -> str:
    dados = caminho.read_bytes()
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("latin-1")


def _paragrafos(texto: str) -> list[str]:
    """Separa por linhas em branco e junta as quebras de linha internas de cada parágrafo."""
    return [" ".join(bloco.split()) for bloco in re.split(r"\n\s*\n", texto) if bloco.strip()]


def _capitulos_txt(paragrafos: list[str], titulo_padrao: str) -> list[Capitulo]:
    """Inicia um novo capítulo a cada linha curta que começa com 'Capítulo' ou 'Chapter'."""
    capitulos: list[Capitulo] = []
    atual = Capitulo(titulo_padrao)
    for paragrafo in paragrafos:
        if len(paragrafo) <= 80 and REGEX_CAPITULO.match(paragrafo):
            if atual.paragrafos:
                capitulos.append(atual)
            atual = Capitulo(paragrafo)
        else:
            atual.paragrafos.append(paragrafo)
    if atual.paragrafos or not capitulos:
        capitulos.append(atual)
    return capitulos


class _ExtratorXhtml(HTMLParser):
    """Extrai o texto dos blocos de um capítulo XHTML, na ordem do documento.

    Pilha de blocos abertos. Ao abrir um bloco filho, o texto pendente do pai é emitido antes,
    e ao fechá-lo o pai volta a acumular texto. Assim o texto solto entre filhos não se mistura
    nem muda de lugar. <br> vira espaço, e o primeiro cabeçalho vira o título do capítulo.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.paragrafos: list[str] = []
        self.titulo: str | None = None
        self._pilha: list[tuple[str, list[str]]] = [("", [])]  # raiz sem tag, para texto solto
        self._ignorando = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in IGNORADAS_XHTML:
            self._ignorando += 1
        elif tag == "br":
            self._pilha[-1][1].append(" ")
        elif tag in BLOCOS_XHTML:
            self._emitir_pendente()
            self._pilha.append((tag, []))

    def handle_endtag(self, tag: str) -> None:
        if tag in IGNORADAS_XHTML:
            self._ignorando = max(0, self._ignorando - 1)
            return
        indice = next((i for i in range(len(self._pilha) - 1, 0, -1) if self._pilha[i][0] == tag), None)
        if indice is None:
            return
        while len(self._pilha) > indice:
            self._fechar_topo()

    def handle_data(self, data: str) -> None:
        if not self._ignorando:
            self._pilha[-1][1].append(data)

    def close(self) -> None:
        super().close()
        # Emite de baixo para cima: é a ordem do documento.
        while len(self._pilha) > 1:
            self._fechar_topo()
        self._emitir_pendente()

    def _emitir_pendente(self) -> None:
        tag, buffer = self._pilha[-1]
        self._emitir(tag, buffer)
        self._pilha[-1] = (tag, [])

    def _fechar_topo(self) -> None:
        tag, buffer = self._pilha.pop()
        self._emitir(tag, buffer)

    def _emitir(self, tag: str, buffer: list[str]) -> None:
        texto = " ".join("".join(buffer).split())
        if not texto:
            return
        if tag in CABECALHOS_XHTML and self.titulo is None:
            self.titulo = texto
        else:
            self.paragrafos.append(texto)
