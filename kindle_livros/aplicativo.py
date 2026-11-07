"""Aplicativo local e simples: arraste um livro (ou cole um link do YouTube), veja a tradução
lado a lado, escolha o formato (Kindle, PDF ou texto) e salve. Roda só neste Mac."""

import json
import re
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from kindle_livros.busca import nome_arquivo
from kindle_livros.conversor import carregar_livro
from kindle_livros.erros import KindleLivrosError
from kindle_livros.formatos import FORMATOS, salvar_formato
from kindle_livros.idioma import com_idioma_detectado
from kindle_livros.modelo import Capitulo, Livro
from kindle_livros.tradutor import ClaudeBackend, Tradutor, TradutorComCache, traduzir_livro

PASTA_TRABALHO = Path.home() / "Documents" / "Kindle Livros"
PASTA_ENTRADA = PASTA_TRABALHO / "entrada"
PASTA_SAIDA = PASTA_TRABALHO
CACHE_TRADUCAO = PASTA_TRABALHO / "cache_traducao_pt.json"
LIMITE_UPLOAD = 300 * 1024 * 1024
EXTENSOES_ACEITAS = {".pdf", ".epub", ".txt", ".mp3", ".m4a", ".wav", ".ogg"}
IDIOMA_DESTINO = "pt"
TRECHOS_PREVIA = 4
PAGINA = Path(__file__).with_name("pagina.html")

_fontes: dict[str, Livro] = {}
_trava = threading.Lock()


def _tradutor() -> Tradutor:
    return TradutorComCache(ClaudeBackend(), CACHE_TRADUCAO)


def _livro_original(origem: str, nome_original: str | None = None) -> Livro:
    """Carrega o livro, dá a ele o nome original do arquivo (se não tiver título) e detecta o idioma."""
    livro = carregar_livro(origem, IDIOMA_DESTINO)
    if nome_original and livro.titulo == Path(origem).stem:
        livro = replace(livro, titulo=Path(nome_original).stem)
    return com_idioma_detectado(livro)


def _traduzir(livro: Livro, tradutor: Tradutor) -> Livro:
    if livro.idioma == IDIOMA_DESTINO:  # só pula a tradução quando já está em português
        return livro
    return traduzir_livro(livro, tradutor, IDIOMA_DESTINO)


def _resumo(livro: Livro, fonte_id: str) -> dict[str, Any]:
    return {"id": fonte_id, "titulo": livro.titulo, "autor": livro.autor, "idioma": livro.idioma,
            "precisa_traduzir": livro.idioma != IDIOMA_DESTINO}


def registrar_fonte(origem: str, nome_original: str | None = None) -> dict[str, Any]:
    livro = _livro_original(origem, nome_original)
    fonte_id = uuid.uuid4().hex
    with _trava:
        _fontes[fonte_id] = livro
    return _resumo(livro, fonte_id)


def previa(fonte_id: str, tradutor: Tradutor | None = None) -> dict[str, Any]:
    """Traduz só o título e os primeiros trechos, para a pessoa ver como ficou antes do livro inteiro."""
    livro = _livro_de(fonte_id)
    originais = [livro.titulo]
    if livro.capitulos:
        primeiro = livro.capitulos[0]
        capitulo = [primeiro.titulo] if primeiro.titulo and primeiro.titulo != livro.titulo else []
        originais += capitulo + primeiro.paragrafos[:TRECHOS_PREVIA]
    amostra = Livro(livro.titulo, livro.autor, livro.idioma, [Capitulo("", originais[1:])])
    traduzido = _traduzir(amostra, tradutor or _tradutor())
    traducoes = [traduzido.titulo] + traduzido.capitulos[0].paragrafos
    pares = [{"original": o, "traducao": t} for o, t in zip(originais, traducoes)]
    return {"pares": pares, **_resumo(livro, fonte_id)}


def gerar(fonte_id: str, formato: str, tradutor: Tradutor | None = None, pasta: Path | None = None) -> dict[str, Any]:
    livro = _livro_de(fonte_id)
    traduzido = _traduzir(livro, tradutor or _tradutor())
    arquivo = salvar_formato(traduzido, pasta or PASTA_SAIDA, Path(nome_arquivo(traduzido.titulo, "txt")).stem, formato)
    return {"arquivo": arquivo.name, "formato": formato, "rotulo": FORMATOS[formato]["rotulo"]}


def _livro_de(fonte_id: str) -> Livro:
    with _trava:
        livro = _fontes.get(fonte_id)
    if livro is None:
        raise KindleLivrosError("Não encontrei mais este livro. Arraste o arquivo de novo.")
    return livro


def _url_youtube_valida(url: str) -> bool:
    return bool(re.match(r"^https?://(www\.|m\.)?(youtube\.com/watch\?|youtu\.be/)", url.strip()))


class _Manipulador(BaseHTTPRequestHandler):
    def log_message(self, formato: str, *args: Any) -> None:  # o terminal fica limpo
        return

    def _enviar(self, codigo: int, corpo: bytes, tipo: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for nome, valor in (extra or {}).items():
            self.send_header(nome, valor)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, codigo: int, dados: dict[str, Any]) -> None:
        self._enviar(codigo, json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                     "application/json; charset=utf-8")

    def _corpo(self) -> bytes:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0:
            raise KindleLivrosError("Nada foi recebido. Tente de novo.")
        if tamanho > LIMITE_UPLOAD:
            raise KindleLivrosError("Arquivo grande demais (limite de 300 MB).")
        return self.rfile.read(tamanho)

    def do_GET(self) -> None:
        caminho = urlparse(self.path).path
        if caminho == "/":
            self._enviar(200, PAGINA.read_bytes(), "text/html; charset=utf-8")
        elif caminho.startswith("/arquivos/"):
            nome = Path(unquote(caminho[len("/arquivos/"):])).name  # só o nome, sem pastas
            arquivo = PASTA_SAIDA / nome
            if arquivo.suffix.lower() not in {".epub", ".pdf", ".txt"} or not arquivo.is_file():
                self._json(404, {"erro": "Arquivo não encontrado."})
                return
            tipos = {".epub": "application/epub+zip", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8"}
            self._enviar(200, arquivo.read_bytes(), tipos[arquivo.suffix.lower()],
                         {"Content-Disposition": f'attachment; filename="{nome}"'})
        else:
            self._json(404, {"erro": "Não encontrado."})

    def do_POST(self) -> None:
        caminho = urlparse(self.path).path
        try:
            if caminho == "/fonte":
                nome = unquote(self.headers.get("X-Nome-Arquivo", "livro"))
                extensao = Path(nome).suffix.lower()
                if extensao not in EXTENSOES_ACEITAS:
                    raise KindleLivrosError("Este tipo de arquivo não funciona aqui. Use um livro em PDF, EPUB ou TXT.")
                pasta = PASTA_ENTRADA / uuid.uuid4().hex  # pasta própria; o arquivo mantém o nome original
                pasta.mkdir(parents=True, exist_ok=True)
                destino = pasta / nome_arquivo(Path(nome).stem, extensao.lstrip("."))
                destino.write_bytes(self._corpo())
                self._json(200, registrar_fonte(str(destino), nome))
            elif caminho == "/fonte-link":
                url = str(json.loads(self._corpo().decode("utf-8")).get("url", "")).strip()
                if not _url_youtube_valida(url):
                    raise KindleLivrosError("Este endereço não é de um vídeo do YouTube. Copie o endereço da barra do navegador, com o vídeo aberto.")
                self._json(200, registrar_fonte(url))
            elif caminho == "/previa":
                dados = json.loads(self._corpo().decode("utf-8"))
                self._json(200, previa(str(dados.get("id", ""))))
            elif caminho == "/gerar":
                dados = json.loads(self._corpo().decode("utf-8"))
                formato = str(dados.get("formato", "epub"))
                if formato not in FORMATOS:
                    raise KindleLivrosError("Escolha um formato: Kindle, PDF ou texto.")
                self._json(200, gerar(str(dados.get("id", "")), formato))
            else:
                self._json(404, {"erro": "Não encontrado."})
        except KindleLivrosError as exc:
            self._json(400, {"erro": str(exc)})
        except Exception:  # o servidor continua de pé; a página mostra a mensagem
            self._json(500, {"erro": "Algo não deu certo. Tente de novo. Se acontecer outra vez, feche o app e abra de novo."})


def criar_servidor(porta: int = 8765) -> ThreadingHTTPServer:
    """Só 127.0.0.1: nada fica acessível fora deste Mac."""
    return ThreadingHTTPServer(("127.0.0.1", porta), _Manipulador)


def iniciar(abrir_navegador: bool = True, porta: int = 8765) -> None:
    servidor = criar_servidor(porta)
    endereco = f"http://127.0.0.1:{servidor.server_address[1]}/"
    print(f"Kindle Livros aberto em {endereco}")
    print("Para fechar o app, pressione Control + C.")
    if abrir_navegador:
        threading.Timer(0.5, webbrowser.open, args=(endereco,)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
