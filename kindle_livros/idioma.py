"""Detecção automática do idioma do livro (opcional: requer a biblioteca langdetect)."""

from dataclasses import replace

from kindle_livros.modelo import Livro

AMOSTRA_CARACTERES = 4000


def detectar_idioma(livro: Livro) -> str | None:
    """Devolve o código do idioma (ex.: 'en', 'es', 'pt'), ou None se não for possível detectar."""
    try:
        from langdetect import DetectorFactory, detect
    except ImportError:
        return None
    DetectorFactory.seed = 0  # resultado estável entre execuções
    trechos = [p for capitulo in livro.capitulos for p in capitulo.paragrafos[:5]]
    amostra = " ".join(trechos)[:AMOSTRA_CARACTERES].strip()
    if not amostra:
        return None
    try:
        return detect(amostra)
    except Exception:  # langdetect levanta erro quando não há letras suficientes
        return None


IDIOMA_DESCONHECIDO = "desconhecido"


def com_idioma_detectado(livro: Livro) -> Livro:
    """Cópia do livro com o idioma detectado. Sem detecção, marca como desconhecido,
    para que o livro seja traduzido mesmo assim (a IA identifica o idioma sozinha)."""
    codigo = detectar_idioma(livro)
    return replace(livro, idioma=codigo or IDIOMA_DESCONHECIDO)
