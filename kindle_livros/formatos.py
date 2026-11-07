"""Formatos de saída do livro traduzido: EPUB (Kindle), PDF e texto."""

from pathlib import Path
from xml.sax.saxutils import escape

from kindle_livros.conversor import salvar_livro
from kindle_livros.erros import DependenciaAusente, FormatoNaoSuportado
from kindle_livros.modelo import Livro

FORMATOS: dict[str, dict[str, str]] = {
    "epub": {"extensao": "epub", "rotulo": "Kindle (EPUB)"},
    "pdf": {"extensao": "pdf", "rotulo": "PDF"},
    "txt": {"extensao": "txt", "rotulo": "Texto"},
}


def salvar_formato(livro: Livro, pasta: Path, nome_base: str, formato: str) -> Path:
    """Grava o livro no formato escolhido dentro da pasta e devolve o caminho do arquivo."""
    if formato not in FORMATOS:
        raise FormatoNaoSuportado(f"Formato desconhecido: {formato}.")
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{nome_base}.{FORMATOS[formato]['extensao']}"
    if formato == "epub":
        return salvar_livro(livro, destino)
    if formato == "txt":
        destino.write_text(_texto_puro(livro), encoding="utf-8")
        return destino
    return _salvar_pdf(livro, destino)


def _texto_puro(livro: Livro) -> str:
    partes = [livro.titulo, ""]
    for capitulo in livro.capitulos:
        partes += [capitulo.titulo, ""]
        partes += [paragrafo + "\n" for paragrafo in capitulo.paragrafos]
        partes.append("")
    return "\n".join(partes)


def _salvar_pdf(livro: Livro, destino: Path) -> Path:
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise DependenciaAusente("Para salvar em PDF instale: pip install reportlab") from exc
    estilos = getSampleStyleSheet()
    historia = [Paragraph(escape(livro.titulo), estilos["Title"]), Spacer(1, 24)]
    for capitulo in livro.capitulos:
        historia.append(PageBreak())
        historia.append(Paragraph(escape(capitulo.titulo), estilos["Heading1"]))
        historia += [Paragraph(escape(p), estilos["BodyText"]) for p in capitulo.paragrafos]
    SimpleDocTemplate(str(destino), pagesize=A5, title=livro.titulo, author=livro.autor).build(historia)
    return destino
