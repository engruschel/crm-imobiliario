import sys
from pathlib import Path

import pytest

from kindle_livros.erros import DependenciaAusente
from kindle_livros.transcricao import parse_vtt, transcrever_audio


def test_parse_vtt_remove_tempos_tags_e_repeticoes() -> None:
    vtt = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:02.000
<c>Olá</c> mundo

00:00:02.000 --> 00:00:04.000
Olá mundo

00:00:04.000 --> 00:00:06.000
segunda frase
"""
    paragrafos = parse_vtt(vtt)
    assert paragrafos == ["Olá mundo segunda frase"]


def test_transcricao_sem_faster_whisper_orienta_instalacao(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(DependenciaAusente, match="faster-whisper"):
        transcrever_audio(tmp_path / "a.mp3")
