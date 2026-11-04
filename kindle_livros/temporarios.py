"""Arquivos temporários exclusivos do programa, usados nas escritas atômicas.

Cada temporário recebe um nome aleatório com prefixo próprio, então nunca coincide com um arquivo do
usuário (mesmo que ele se chame "x.epub.parcial"). Só os arquivos com esse padrão são removidos.
"""

import uuid
from pathlib import Path

PREFIXO = ".kindle_livros-"
SUFIXO = ".tmp"


def caminho_temporario(alvo: Path) -> Path:
    """Caminho novo e exclusivo na mesma pasta de `alvo`, para ser renomeado depois."""
    return alvo.with_name(f"{PREFIXO}{uuid.uuid4().hex}{SUFIXO}")


def remover_temporarios(pasta: Path) -> None:
    """Remove restos de escritas interrompidas pelo próprio programa. Outros arquivos não são tocados."""
    for arquivo in pasta.glob(f"{PREFIXO}*{SUFIXO}"):
        arquivo.unlink(missing_ok=True)
