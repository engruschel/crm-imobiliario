"""Detecção do Kindle conectado por USB e cópia de livros para a pasta documents/."""

import glob
import os
import shutil
import string
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from kindle_livros.config import EXTENSOES_KINDLE, MARGEM_ESPACO_BYTES
from kindle_livros.erros import EspacoInsuficiente, FormatoNaoSuportado, KindleLivrosError, KindleNaoEncontrado
from kindle_livros.temporarios import caminho_temporario, remover_temporarios

NOME_VOLUME = "Kindle"


@dataclass(frozen=True)
class ResultadoEnvio:
    copiados: list[Path]
    ignorados: list[Path]  # já existiam no Kindle e não foram sobrescritos (ou já são o mesmo arquivo)
    pasta_documentos: Path


def padroes_de_montagem(plataforma: str) -> tuple[str, ...]:
    """Pontos de montagem onde procurar. O nome do volume não importa: a assinatura
    (pastas documents/ e system/) é que identifica um Kindle."""
    if plataforma == "darwin":
        return ("/Volumes/*",)
    return (
        "/media/*/*",
        "/run/media/*/*",
        "/mnt/*",
    )


def detectar_kindles(plataforma: str | None = None, padroes: Sequence[str] | None = None) -> list[Path]:
    """Retorna os pontos de montagem de Kindles encontrados.

    No Windows procura unidades com o rótulo de volume "Kindle".
    """
    plataforma = plataforma or sys.platform
    if plataforma == "win32":
        unidades = [Path(f"{letra}:\\") for letra in string.ascii_uppercase]
        return [u for u in unidades if u.exists() and _rotulo_windows(u) == NOME_VOLUME]
    candidatos = []
    for padrao in padroes if padroes is not None else padroes_de_montagem(plataforma):
        candidatos.extend(Path(c) for c in sorted(glob.glob(padrao)))
    return [c for c in dict.fromkeys(candidatos) if c.is_dir() and parece_kindle(c)]


def parece_kindle(raiz: Path) -> bool:
    """Assinatura de um Kindle: as pastas documents/ e system/ juntas."""
    return (raiz / "documents").is_dir() and (raiz / "system").is_dir()


def _rotulo_windows(raiz: Path) -> str:
    import ctypes

    buffer = ctypes.create_unicode_buffer(261)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(str(raiz), buffer, 261, None, None, None, None, 0)
    return buffer.value if ok else ""


def pasta_documentos(destino: Path) -> Path:
    """Aceita a raiz do Kindle ou a própria pasta documents/."""
    return destino if destino.name == "documents" else destino / "documents"


def validar_destino(destino: Path, confirmado: bool = False) -> None:
    """Exige que o destino pareça um Kindle, a menos que o usuário confirme explicitamente."""
    if not destino.is_dir():
        raise KindleNaoEncontrado(f"Destino não encontrado: {destino}")
    parece = parece_kindle(destino) or (destino.name == "documents" and parece_kindle(destino.parent))
    if not parece and not confirmado:
        raise KindleNaoEncontrado(
            f"A pasta {destino} não parece um Kindle (precisa ter documents/ e system/). "
            "Se tiver certeza, repita o comando com --confirmar-destino."
        )


def enviar_para_kindle(arquivos: Sequence[Path], destino: Path, forcar: bool = False,
                       confirmar_destino: bool = False) -> ResultadoEnvio:
    """Copia os arquivos para documents/ do Kindle.

    Arquivos já existentes só são substituídos com `forcar=True`. Verifica o espaço livre antes de copiar.
    A cópia vai para um temporário e só substitui o destino ao concluir.
    """
    for arquivo in arquivos:
        if arquivo.suffix.lower() not in EXTENSOES_KINDLE:
            raise FormatoNaoSuportado(
                f"Formato não aceito pelo Kindle: '{arquivo.name}'. "
                f"Use: {', '.join(sorted(EXTENSOES_KINDLE))}."
            )
        if not arquivo.is_file():
            raise KindleLivrosError(f"Arquivo não encontrado: {arquivo}")
    validar_destino(destino, confirmar_destino)
    pasta = pasta_documentos(destino)
    pasta.mkdir(exist_ok=True)
    remover_temporarios(pasta)  # restos de cópias interrompidas pelo próprio programa

    a_copiar: list[tuple[Path, Path]] = []
    ignorados: list[Path] = []
    for arquivo in arquivos:
        alvo = pasta / arquivo.name
        if alvo.exists() and (not forcar or alvo.resolve() == arquivo.resolve()):
            ignorados.append(alvo)  # já existe, ou é o próprio arquivo do Kindle: nada a copiar
        else:
            a_copiar.append((arquivo, alvo))

    necessario = sum(origem.stat().st_size for origem, _ in a_copiar)
    livre = shutil.disk_usage(pasta).free
    if necessario + MARGEM_ESPACO_BYTES > livre:
        raise EspacoInsuficiente(
            f"Espaço insuficiente no Kindle: necessário {necessario / 1e6:.1f} MB, "
            f"livre {livre / 1e6:.1f} MB."
        )
    for origem, alvo in a_copiar:
        _copiar_atomico(origem, alvo)
    return ResultadoEnvio(copiados=[alvo for _, alvo in a_copiar], ignorados=ignorados, pasta_documentos=pasta)


def _copiar_atomico(origem: Path, alvo: Path) -> None:
    temporario = caminho_temporario(alvo)
    try:
        shutil.copyfile(origem, temporario)
        os.replace(temporario, alvo)
    except OSError as exc:
        temporario.unlink(missing_ok=True)
        raise KindleLivrosError(f"Falha ao copiar '{origem.name}' para o Kindle: {exc}") from exc
