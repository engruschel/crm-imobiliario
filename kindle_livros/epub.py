"""Gerador de EPUB 3 usando apenas a biblioteca padrão."""

import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from kindle_livros.erros import ErroConversao
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.temporarios import caminho_temporario

# Caracteres de controle e não-caracteres que o XML 1.0 não aceita, mesmo escapados.
CARACTERES_PROIBIDOS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")

ESTILO_CSS = """body { font-family: serif; line-height: 1.5; margin: 5%; }
h1 { text-align: center; margin-bottom: 1.5em; }
p { text-indent: 1.2em; margin: 0 0 0.6em 0; text-align: justify; }
"""

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def gerar_epub(livro: Livro, caminho: Path) -> Path:
    """Grava `livro` em `caminho` como EPUB 3 válido e retorna o caminho.

    A escrita vai para um arquivo temporário que só substitui `caminho` ao final com sucesso.
    """
    if not any(cap.paragrafos for cap in livro.capitulos):
        raise ErroConversao("O livro não tem texto para gerar o EPUB.")
    capitulos = [cap for cap in livro.capitulos if cap.paragrafos]
    nomes = [f"cap-{i:03d}.xhtml" for i in range(1, len(capitulos) + 1)]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho_temporario(caminho)
    try:
        with zipfile.ZipFile(temporario, "w") as zf:
            # O EPUB exige que "mimetype" seja o primeiro item e não comprimido.
            zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
            zf.writestr("META-INF/container.xml", CONTAINER_XML)
            zf.writestr("OEBPS/content.opf", _opf(livro, capitulos, nomes))
            zf.writestr("OEBPS/nav.xhtml", _nav(livro, capitulos, nomes))
            zf.writestr("OEBPS/estilo.css", ESTILO_CSS)
            for capitulo, nome in zip(capitulos, nomes):
                zf.writestr(f"OEBPS/{nome}", _xhtml_capitulo(livro, capitulo))
        os.replace(temporario, caminho)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    return caminho


def _texto(valor: str) -> str:
    """Escapa texto de elemento XML, removendo caracteres de controle proibidos."""
    return escape(CARACTERES_PROIBIDOS.sub("", valor))


def _atributo(valor: str) -> str:
    """Escapa valor de atributo XML entre aspas duplas."""
    return escape(CARACTERES_PROIBIDOS.sub("", valor), {'"': "&quot;"})


def _opf(livro: Livro, capitulos: list[Capitulo], nomes: list[str]) -> str:
    identificador = uuid.uuid5(uuid.NAMESPACE_URL, f"{livro.titulo}|{livro.autor}|{livro.idioma}")
    agora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    itens = "\n".join(
        f'    <item id="cap{i}" href="{_atributo(nome)}" media-type="application/xhtml+xml"/>'
        for i, nome in enumerate(nomes, start=1)
    )
    refs = "\n".join(f'    <itemref idref="cap{i}"/>' for i in range(1, len(nomes) + 1))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id-livro" xml:lang="{_atributo(livro.idioma)}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="id-livro">urn:uuid:{identificador}</dc:identifier>
    <dc:title>{_texto(livro.titulo)}</dc:title>
    <dc:creator>{_texto(livro.autor)}</dc:creator>
    <dc:language>{_texto(livro.idioma)}</dc:language>
    <meta property="dcterms:modified">{agora}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="estilo.css" media-type="text/css"/>
{itens}
  </manifest>
  <spine>
{refs}
  </spine>
</package>
"""


def _nav(livro: Livro, capitulos: list[Capitulo], nomes: list[str]) -> str:
    entradas = "\n".join(
        f'      <li><a href="{_atributo(nome)}">{_texto(cap.titulo)}</a></li>'
        for cap, nome in zip(capitulos, nomes)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{_atributo(livro.idioma)}" lang="{_atributo(livro.idioma)}">
<head><meta charset="UTF-8"/><title>Sumário</title></head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Sumário</h1>
    <ol>
{entradas}
    </ol>
  </nav>
</body>
</html>
"""


def _xhtml_capitulo(livro: Livro, capitulo: Capitulo) -> str:
    paragrafos = "\n".join(f"  <p>{_texto(p)}</p>" for p in capitulo.paragrafos)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{_atributo(livro.idioma)}" lang="{_atributo(livro.idioma)}">
<head>
  <meta charset="UTF-8"/>
  <title>{_texto(capitulo.titulo)}</title>
  <link rel="stylesheet" type="text/css" href="estilo.css"/>
</head>
<body>
  <h1>{_texto(capitulo.titulo)}</h1>
{paragrafos}
</body>
</html>
"""
