"""Transcrição de áudio (faster-whisper) e legendas de vídeos do YouTube (yt-dlp), ambas opcionais."""

import re
import tempfile
from pathlib import Path

from kindle_livros.config import MODELO_WHISPER, TAMANHO_PARAGRAFO_TRANSCRICAO
from kindle_livros.erros import DependenciaAusente, ErroConversao
from kindle_livros.modelo import agrupar_textos


def transcrever_audio(caminho: Path, idioma: str | None = None) -> list[str]:
    """Transcreve o áudio localmente e devolve parágrafos de texto."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise DependenciaAusente("Para transcrever áudio instale: pip install faster-whisper") from exc
    modelo = WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")
    segmentos, _info = modelo.transcribe(str(caminho), language=idioma)
    return _paragrafos([segmento.text for segmento in segmentos])


def legendas_youtube(url: str, idioma: str) -> tuple[str, str, list[str]]:
    """Baixa só as legendas de um vídeo do YouTube (sem o vídeo) e devolve (título, canal, parágrafos)."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise DependenciaAusente("Para usar links do YouTube instale: pip install yt-dlp") from exc
    with tempfile.TemporaryDirectory() as tmp:
        opcoes = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [idioma],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(tmp) / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(opcoes) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise ErroConversao(f"Não foi possível obter as legendas deste vídeo: {exc}") from exc
        arquivos = sorted(Path(tmp).glob("*.vtt"))
        if not arquivos:
            raise ErroConversao(f"O vídeo não tem legendas no idioma '{idioma}'.")
        paragrafos = parse_vtt(arquivos[0].read_text(encoding="utf-8", errors="replace"))
    return info.get("title") or "Vídeo", info.get("uploader") or "Desconhecido", paragrafos


def parse_vtt(texto: str) -> list[str]:
    """Converte WebVTT em parágrafos, removendo tempos, marcações e repetições das legendas automáticas.

    Legendas automáticas repetem trechos de forma progressiva. Quando uma linha começa com um trecho
    final da anterior, só a parte nova é acrescentada ("ola a todos" + "ola a todos bem vindos" resulta
    em "ola a todos bem vindos"). Quando a linha nova já está no início da anterior, é descartada.

    Consequência conhecida: linhas repetidas legítimas e consecutivas ("sim" e "sim") são fundidas em uma só.
    Sobreposição de uma palavra só é aceita quando é a linha anterior inteira, para não colar frases
    diferentes como "vamos lá" + "lá em casa".

    Risco conhecido: duas ou mais palavras coincidentes no fim de uma legenda e no início da seguinte
    fundem frases diferentes. Exemplo: "vou fazer isso" seguido de "fazer isso agora" vira
    "vou fazer isso agora". Não há como distinguir isso de uma repetição progressiva só pelo texto.
    """
    linhas: list[str] = []
    for bruta in texto.splitlines():
        linha = re.sub(r"<[^>]+>", "", bruta).strip()
        if not linha or linha == "WEBVTT" or "-->" in linha or linha.startswith(("NOTE", "Kind:", "Language:")):
            continue
        if not linhas:
            linhas.append(linha)
            continue
        anterior = linhas[-1]
        if anterior.split()[: len(linha.split())] == linha.split():
            continue
        combinado = _sobrepor(anterior, linha)
        if combinado is None:
            linhas.append(linha)
        else:
            linhas[-1] = combinado
    return _paragrafos(linhas)


def _sobrepor(anterior: str, nova: str) -> str | None:
    """Junta `nova` a `anterior` pelo maior trecho final de `anterior` que é início de `nova`.

    Devolve None quando não há sobreposição aceitável.
    """
    palavras_anterior = anterior.split()
    palavras_nova = nova.split()
    for tamanho in range(min(len(palavras_anterior), len(palavras_nova)), 0, -1):
        if tamanho == 1 and tamanho != len(palavras_anterior):
            break
        if palavras_anterior[-tamanho:] == palavras_nova[:tamanho]:
            return " ".join(palavras_anterior + palavras_nova[tamanho:])
    return None


def _paragrafos(trechos: list[str]) -> list[str]:
    return [" ".join(grupo) for grupo in agrupar_textos(
        [t.strip() for t in trechos if t.strip()], TAMANHO_PARAGRAFO_TRANSCRICAO)]
