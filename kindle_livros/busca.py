"""Busca em fontes legais (Project Gutenberg, Internet Archive) e em pastas locais, e download."""

import http.client
import json
import re
import shutil
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from kindle_livros.config import (
    EXTENSOES_KINDLE,
    TIMEOUT_HTTP,
    URL_GUTENDEX,
    URL_IA_BUSCA,
    URL_IA_DOWNLOAD,
    URL_IA_METADADOS,
    USER_AGENT,
)
from kindle_livros.erros import ErroBusca
from kindle_livros.kindle_usb import parece_kindle
from kindle_livros.modelo import ResultadoBusca
from kindle_livros.temporarios import caminho_temporario

FORMATOS_GUTENBERG = {
    "application/epub+zip": "epub",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "application/x-mobipocket-ebook": "mobi",
}
ORDEM_CONVERSAO = ("epub", "pdf", "txt")


def buscar(termo: str, fontes: list[str], limite: int = 10,
           pasta_local: Path | None = None) -> tuple[list[ResultadoBusca], list[str]]:
    """Consulta as fontes pedidas. Devolve (resultados, avisos) — uma fonte com falha não interrompe as demais."""
    resultados: list[ResultadoBusca] = []
    avisos: list[str] = []
    for fonte in fontes:
        try:
            resultados.extend(_buscar_em(fonte, termo, limite, pasta_local))
        except ErroBusca as exc:
            avisos.append(f"{fonte}: {exc}")
    return resultados, avisos


def _buscar_em(fonte: str, termo: str, limite: int, pasta_local: Path | None) -> list[ResultadoBusca]:
    if fonte == "gutenberg":
        return buscar_gutenberg(termo, limite)
    if fonte == "internet_archive":
        return buscar_internet_archive(termo, limite)
    if fonte == "local":
        if pasta_local is None:
            raise ErroBusca("informe a pasta com --pasta-local.")
        return buscar_local(pasta_local, termo)
    raise ErroBusca(f"fonte desconhecida: {fonte}.")


def buscar_gutenberg(termo: str, limite: int = 10) -> list[ResultadoBusca]:
    dados = _obter_json(URL_GUTENDEX, [("search", termo)])
    resultados = []
    for livro in dados.get("results", [])[:limite]:
        links: dict[str, str] = {}
        for mime, url in (livro.get("formats") or {}).items():
            formato = FORMATOS_GUTENBERG.get(mime.split(";")[0].strip())
            if formato:
                links.setdefault(formato, url)
        if links:
            autores = [a.get("name", "") for a in livro.get("authors") or [] if a.get("name")]
            resultados.append(ResultadoBusca(
                titulo=livro.get("title") or "(sem título)",
                autor=", ".join(autores) or "Desconhecido",
                fonte="Project Gutenberg",
                links=links,
            ))
    return resultados


def buscar_internet_archive(termo: str, limite: int = 10) -> list[ResultadoBusca]:
    dados = _obter_json(URL_IA_BUSCA, [
        ("q", f"({termo}) AND mediatype:texts"),
        ("fl[]", "identifier"),
        ("fl[]", "title"),
        ("fl[]", "creator"),
        ("rows", str(limite)),
        ("page", "1"),
        ("output", "json"),
    ])
    resultados = []
    for documento in dados.get("response", {}).get("docs", []):
        identificador = documento.get("identifier")
        if not identificador:
            continue
        try:
            links = _links_internet_archive(identificador)
        except ErroBusca:
            continue  # um item com metadados indisponíveis não derruba a fonte inteira
        if links:
            resultados.append(ResultadoBusca(
                titulo=_como_texto(documento.get("title")) or "(sem título)",
                autor=_como_texto(documento.get("creator")) or "Desconhecido",
                fonte="Internet Archive",
                links=links,
            ))
    return resultados


def _links_internet_archive(identificador: str) -> dict[str, str]:
    """Lista os arquivos do item que estão em formatos aceitos pelo Kindle."""
    item = urllib.parse.quote(identificador)
    metadados = _obter_json(f"{URL_IA_METADADOS}/{item}")
    links: dict[str, str] = {}
    for arquivo in metadados.get("files", []):
        nome = arquivo.get("name", "")
        formato = Path(nome).suffix.lower().lstrip(".")
        if f".{formato}" in EXTENSOES_KINDLE:
            links.setdefault(formato, f"{URL_IA_DOWNLOAD}/{item}/{urllib.parse.quote(nome)}")
    return links


def buscar_local(pasta: Path, termo: str) -> list[ResultadoBusca]:
    """Procura, recursivamente, arquivos de livros cujo nome contenha o termo (sem acentos nem maiúsculas)."""
    if not pasta.is_dir():
        raise ErroBusca(f"pasta não encontrada: {pasta}.")
    alvo = _normalizar(termo)
    por_nome: dict[str, dict[str, str]] = {}
    for arquivo in sorted(pasta.rglob("*")):
        sufixo = arquivo.suffix.lower()
        if arquivo.is_file() and sufixo in EXTENSOES_KINDLE and alvo in _normalizar(arquivo.stem) \
                and not _dentro_de_kindle(arquivo, pasta):
            por_nome.setdefault(arquivo.stem, {}).setdefault(sufixo.lstrip("."), str(arquivo))
    return [
        ResultadoBusca(titulo=nome, autor="Desconhecido", fonte="Arquivos locais", links=links)
        for nome, links in por_nome.items()
    ]


def _dentro_de_kindle(arquivo: Path, pasta: Path) -> bool:
    """Indica se há um Kindle entre o arquivo e a pasta pesquisada.

    Só considera ancestrais estritamente abaixo de `pasta`: a própria pasta pesquisada nunca conta,
    para que uma biblioteca com uma subpasta qualquer não oculte seus livros.
    """
    for ancestral in arquivo.parents:
        if ancestral == pasta:
            break
        if parece_kindle(ancestral):
            return True
    return False


def melhor_formato_para_conversao(links: dict[str, str]) -> tuple[str, str] | None:
    """Escolhe o formato que o conversor sabe ler (EPUB, PDF ou TXT). Devolve (formato, link)."""
    for formato in ORDEM_CONVERSAO:
        if formato in links:
            return formato, links[formato]
    return None


def obter_arquivo(link: str, pasta: Path, nome: str) -> Path:
    """Devolve o arquivo local indicado ou baixa a URL para `pasta`."""
    if link.startswith(("http://", "https://")):
        return baixar(link, pasta, nome)
    caminho = Path(link)
    if not caminho.is_file():
        raise ErroBusca(f"arquivo não encontrado: {caminho}.")
    return caminho


def baixar(url: str, pasta: Path, nome: str) -> Path:
    """Baixa para um arquivo temporário e só o renomeia para o nome final em caso de sucesso."""
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / nome
    temporario = caminho_temporario(destino)
    requisicao = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_HTTP) as resposta, temporario.open("wb") as arquivo:
            shutil.copyfileobj(resposta, arquivo)
        temporario.replace(destino)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        temporario.unlink(missing_ok=True)
        raise ErroBusca(f"falha ao baixar {url}: {exc}") from exc
    return destino


def nome_arquivo(titulo: str, extensao: str) -> str:
    """Nome de arquivo seguro para o sistema de arquivos, a partir do título."""
    limpo = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", titulo).strip()[:120] or "livro"
    return f"{limpo}.{extensao}"


def _obter_json(url: str, parametros: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    alvo = url + ("?" + urllib.parse.urlencode(parametros) if parametros else "")
    requisicao = urllib.request.Request(alvo, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(requisicao, timeout=TIMEOUT_HTTP) as resposta:
            return json.loads(resposta.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise ErroBusca(f"falha ao consultar {url}: {exc}") from exc


def _como_texto(valor: Any) -> str:
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor)
    return str(valor or "").strip()


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()
